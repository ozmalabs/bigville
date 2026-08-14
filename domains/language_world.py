"""LanguageWorld — a babble-loop world adapter that teaches the
substrate language-as-a-class across MULTIPLE natural languages
(English, Spanish, Mandarin, Japanese, ...).

Adapted from StructuredDataWorld: a bank of (text, language,
expected_meaning) tasks; a TEACHER callable (Claude CLI or a
heuristic stub); the substrate observes each sentence, identifies
its language + abstract shape (via the enriched TextShape primitive),
looks up a grounded (Grammar, Lexicon) for that language. On a
cache miss it asks the teacher; the teacher's response is grounded
as Language / Grammar / Lexicon / LexEntry / Production / SemanticFrame
nodes; subsequent sentences in the same language use the grounded
grammar without further teacher calls.

The cross-linguistic point: English is NOT special. The same
machinery (identify language → look up grammar → parse) runs for
en / es / zh / ja. Same-meaning sentences across languages produce
EQUIVALENT semantic-frame dicts ({event, agent, patient, ...}) —
meaning is language-independent.

Per CLAUDE.md this is a world-adapter file: mechanical text-to-graph
translation. No agent-side reasoning here; the strategy table in
graph form IS the agent's learned knowledge.
"""
from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Callable

import substrate_rs as srs

from domains import phase_composer_language_rules as pclr
from domains import dictionary_lexicon as dlex
from domains import morphology_reference as morph
from domains import wiktionary_reference as wikt
from domains import function_word_reference as fwref
from domains import interrogative_reference as ireg
from domains import comparative_reference as cmpref


# ---------------------------------------------------------------------------
# Language identification — cheap I/O-boundary heuristic. Decides which
# graph-resident Language/Grammar to dispatch on. Pure script-distribution
# probe — no language-specific lexicon, no English-bias rules. New
# languages slot in by adding a script-range entry; the same dispatch
# logic carries them.
# ---------------------------------------------------------------------------


def _script_ratios(text: str) -> dict[str, float]:
    """Fraction of non-whitespace chars in each Unicode script range we
    care about. Returns latin / cjk_hira / cjk_kata / cjk_han / other.
    No probabilistic mixing — the dispatcher reads these directly."""
    if not text:
        return {"latin": 0.0, "hira": 0.0, "kata": 0.0, "han": 0.0, "other": 0.0}
    counts = {"latin": 0, "hira": 0, "kata": 0, "han": 0, "other": 0}
    total = 0
    for ch in text:
        if ch.isspace():
            continue
        total += 1
        cp = ord(ch)
        if 0x0041 <= cp <= 0x024F:  # Latin (basic + extended-A/B partial)
            counts["latin"] += 1
        elif 0x3040 <= cp <= 0x309F:  # Hiragana
            counts["hira"] += 1
        elif 0x30A0 <= cp <= 0x30FF:  # Katakana
            counts["kata"] += 1
        elif 0x4E00 <= cp <= 0x9FFF:  # CJK Unified Ideographs
            counts["han"] += 1
        else:
            counts["other"] += 1
    if total == 0:
        return {k: 0.0 for k in counts}
    return {k: v / total for k, v in counts.items()}


def _detect_language(text: str) -> str:
    """Identify language from script-distribution + cheap diacritic
    probe. Returns one of: en / es / zh / ja / unknown. Used only to
    dispatch the cached (Grammar, Lexicon); the teacher overrides this
    on cache miss with its declared language.

    The latin/es split is the only "content-aware" decision: ñ, ¿, ¡,
    + accented vowels (á, é, í, ó, ú) tip the balance toward Spanish.
    Everything else is pure script range. No English-specific rules."""
    r = _script_ratios(text)
    if r["hira"] + r["kata"] > 0.02:  # any kana → Japanese
        return "ja"
    if r["han"] > 0.5 and (r["hira"] + r["kata"]) < 0.02:
        return "zh"
    if r["latin"] > 0.5:
        # latin script: probe for Spanish diacritics / inverted punct.
        spanish_markers = ("ñ", "¿", "¡", "á", "é", "í", "ó", "ú", "Ñ")
        if any(m in text for m in spanish_markers):
            return "es"
        return "en"
    return "unknown"


# ---------------------------------------------------------------------------
# Shape key — language-aware bucketing of the TextShape Dict. Same idea as
# StructuredDataWorld: collapse content-dependent fields into buckets so
# different surface inputs in the same language with the same speech-act
# shape land on the same key.
# ---------------------------------------------------------------------------


def _bucket_token_count(n: int) -> str:
    if n <= 2:
        return "tiny"
    if n <= 5:
        return "short"
    if n <= 10:
        return "medium"
    return "long"


def _language_shape_key(language: str, shape: dict[str, Any]) -> str:
    """Compose a (language, shape) cache key.

    Includes:
      * language (so en/es/zh/ja don't share grammars)
      * terminator (period / question / exclamation / none) — speech-act
      * token_count bucket (sentence length class)
      * has_question_word / connective_kind (cross-lingual question /
        connective signals from TextShape)
      * starts_capital / has_uppercase (writing-system signals)

    DOES NOT include the raw text or per-token features — those are
    what the LEXICON resolves, not what the GRAMMAR dispatches on."""
    terminator = shape.get("terminator", "none")
    has_q_word = bool(shape.get("has_question_word", False))
    connective = shape.get("connective_kind", "none")
    tok_count = int(shape.get("token_count", 0) or 0)
    tok_bucket = _bucket_token_count(tok_count)
    starts_cap = bool(shape.get("starts_capital", False))
    return (f"lang={language}_term={terminator}_qw={'Y' if has_q_word else 'N'}"
            f"_conn={connective}_tok={tok_bucket}_cap={'Y' if starts_cap else 'N'}")


# ---------------------------------------------------------------------------
# Teacher — Claude CLI (real LLM) + a heuristic stub for offline runs.
# ---------------------------------------------------------------------------


_CLAUDE_CLI = "/home/matt/.local/bin/claude"

_TEACHER_PROMPT_TEMPLATE = """For this {language} sentence, identify its meaning as a semantic frame, and the basic grammar productions needed to parse this and similar sentences in {language}.

Sentence: {text}

Return ONLY a JSON object with these fields:
  language: ISO code (en/es/zh/ja/...)
  meaning: a semantic-frame dict with these keys (omit any that don't apply):
    event: the main predicate (use a canonical English concept name like "sit", "love", "break", "chase")
    agent: the doer (a canonical concept name, or "?WHO" / "?WHAT" for wh-questions)
    patient: the affected entity (canonical concept name)
    location: where (canonical concept name)
    tense: "past" / "present" / "future" (omit if unmarked)
    speech_act: "assertion" / "question" / "command" (omit for plain assertion)
  grammar_summary: one sentence describing the language's basic clause structure
  productions: list of basic productions (strings), e.g. ["S -> NP VP", "VP -> V NP", "VP -> V PP"]
  lexicon: list of [surface_word, concept] pairs for the words in THIS sentence,
           mapping each content word to its canonical concept (e.g. ["cat", "cat"], ["gato", "cat"]).
           Use the SAME canonical concept names across languages so meaning is language-independent.

Return ONLY the JSON, no prose, no code fences.
"""


def _extract_json_payload(raw: str) -> str:
    """Pull the first balanced JSON object out of the CLI response,
    stripping any ```json fences or prose around it."""
    s = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", s, re.DOTALL)
    if m:
        s = m.group(1).strip()
    start = s.find("{")
    if start < 0:
        return s
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if esc:
            esc = False
            continue
        if c == "\\":
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return s[start:]


def teacher_via_claude(gap_description: str, text: str,
                       language_hint: str | None = None) -> dict[str, Any]:
    """Shell out to `claude --print` for a structured (meaning, grammar,
    lexicon) spec. Same spec shape as teacher_stub. Returns a safe
    default on any failure (timeout / non-zero exit / malformed JSON)
    so the substrate grounds it as an empty parse and the test scores
    it as a miss; no crash."""
    from domains.no_llm import assert_llm_allowed
    assert_llm_allowed("language_world.teacher_via_claude "
                       "(`claude --print` shell-out)")   # OZMA_NO_LLM hard switch
    language_label = language_hint or "the"
    prompt = _TEACHER_PROMPT_TEMPLATE.format(language=language_label, text=text)
    default = {
        "language": language_hint or "unknown",
        "meaning": {},
        "grammar_summary": "teacher_via_claude default — no response",
        "productions": [],
        "lexicon": [],
        "reasoning": "teacher_via_claude: default (no usable response)",
    }
    try:
        result = subprocess.run(
            [_CLAUDE_CLI, "--print", prompt],
            capture_output=True, text=True, timeout=90,
        )
    except subprocess.TimeoutExpired:
        default["reasoning"] = "teacher_via_claude: subprocess timeout"
        return default
    except Exception as e:  # noqa: BLE001 — CLI invocation failures
        default["reasoning"] = f"teacher_via_claude: invocation failed: {e}"
        return default

    if result.returncode != 0:
        default["reasoning"] = (
            f"teacher_via_claude: nonzero exit {result.returncode}: "
            f"{(result.stderr or '').strip()[:120]}"
        )
        return default

    payload = _extract_json_payload(result.stdout or "")
    try:
        spec = json.loads(payload)
    except (json.JSONDecodeError, ValueError) as e:
        default["reasoning"] = (
            f"teacher_via_claude: malformed JSON ({e}): "
            f"{(result.stdout or '').strip()[:120]}"
        )
        return default

    if not isinstance(spec, dict):
        default["reasoning"] = "teacher_via_claude: response not an object"
        return default

    meaning = spec.get("meaning") or {}
    if not isinstance(meaning, dict):
        meaning = {}
    productions = spec.get("productions") or []
    if not isinstance(productions, list):
        productions = []
    lexicon = spec.get("lexicon") or []
    if not isinstance(lexicon, list):
        lexicon = []

    return {
        "language": spec.get("language") or language_hint or "unknown",
        "meaning": meaning,
        "grammar_summary": (
            spec.get("grammar_summary") or "teacher_via_claude: (no summary)"
        ),
        "productions": [str(p) for p in productions if p],
        "lexicon": [
            (str(pair[0]), str(pair[1]))
            for pair in lexicon
            if isinstance(pair, (list, tuple)) and len(pair) >= 2
        ],
        "reasoning": spec.get("reasoning") or "teacher_via_claude: OK",
    }


# Per-language minimal lexicon + speech-act + tense heuristics for the 16
# test-bank sentences. Surface word → canonical concept (a bare concept, or a
# (concept, tense) tuple for inflected verbs). Module-level so an extended
# teacher (make_stub_teacher) can merge extra vocabulary on top without
# re-declaring the bank. CRITICAL for production: the surface KEY is the
# INFLECTED form ("loves", "sat"), and grounding stores that surface against
# the concept — so production's lexicon-in-reverse emits the inflected form.
_STUB_LEXICA: dict[str, dict[str, Any]] = {
    "en": {
        "cat": "cat", "sat": ("sit", "past"), "mat": "mat",
        "mary": "Mary", "loves": ("love", "present"), "john": "John",
        "who": "?WHO", "broke": ("break", "past"), "vase": "vase",
        "dog": "dog", "chased": ("chase", "past"), "ball": "ball",
        # Extra closed-class / bare forms for the object-wh probes
        # (object_wh_test.py): "what" wh-word + the bare verb stems the
        # do-support questions use ("...does Mary love?", "...did the cat
        # break?"). Stub-only smoke vocab; the bank parses are unchanged.
        "what": "?WHAT", "love": ("love", "present"),
        "break": ("break", "present"),
        # Multi-hop demo vocab (scripts/multihop_question_test.py). The
        # oblique interrogative proforms (where/when/why/how) come from
        # interrogative_reference (closed-class wh->role); listed here so
        # the stub grounds their surface->placeholder lex entries. live/
        # lives = the location predicate; bigger = the comparative relation;
        # Paris/Rome/mouse = the demo entities.
        "where": "?WHERE", "when": "?WHEN", "why": "?WHY", "how": "?HOW",
        "live": ("live", "present"), "lives": ("live", "present"),
        "lived": ("live", "past"),
        "paris": "Paris", "rome": "Rome",
        "mouse": "mouse", "bigger": "bigger",
    },
    "es": {
        "gato": "cat", "sentó": ("sit", "past"), "alfombra": "mat",
        "maría": "Mary", "ama": ("love", "present"), "juan": "John",
        "quién": "?WHO", "rompió": ("break", "past"), "jarrón": "vase",
        "perro": "dog", "persiguió": ("chase", "past"), "pelota": "ball",
    },
    "zh": {
        "猫": "cat", "坐": ("sit", None), "垫子": "mat",
        "玛丽": "Mary", "爱": ("love", None), "约翰": "John",
        "谁": "?WHO", "打破": ("break", None), "花瓶": "vase",
        "狗": "dog", "追": ("chase", None), "球": "ball",
    },
    "ja": {
        "猫": "cat", "座った": ("sit", "past"), "マット": "mat",
        "メアリー": "Mary", "愛している": ("love", "present"), "ジョン": "John",
        "誰": "?WHO", "割った": ("break", "past"), "花瓶": "vase",
        "犬": "dog", "追いかけた": ("chase", "past"), "ボール": "ball",
    },
}


def teacher_stub(gap_description: str, text: str,
                 language_hint: str | None = None,
                 extra_lexicon: dict[str, dict[str, Any]] | None = None
                 ) -> dict[str, Any]:
    """Offline heuristic teacher — minimal hand-rolled per-language
    lexicon for the 16 test-bank sentences so the world adapter can be
    smoke-tested without spawning a Claude subprocess. Real runs use
    `teacher_via_claude`. The substrate sees the SAME spec shape from
    either; its grounding logic is teacher-agnostic.

    ``extra_lexicon`` (used by make_stub_teacher) merges additional
    {lang: {surface: concept|(concept,tense)}} vocabulary on top of the bank,
    so a domain corpus (e.g. the self-account verbs) can ground its INFLECTED
    surfaces the same way the bank grounds "loves"/"sat" — which is what lets
    production emit the inflected form (modifies, holds) rather than the bare
    lemma."""
    lang = language_hint or _detect_language(text)
    lex = dict(_STUB_LEXICA.get(lang, {}))
    if extra_lexicon:
        lex.update(extra_lexicon.get(lang, {}))
    meaning: dict[str, Any] = {}
    found_lex: list[tuple[str, str]] = []
    # Tokenize. For CJK we greedy-walk left-to-right against lexicon
    # surfaces (sorted longest-first within the scan, so 垫子 wins over
    # 垫). For latin we split on word chars and lowercase. Position
    # order matters — the stub uses surface order to assign roles, so
    # iterating lex.keys() is wrong.
    if lang in ("zh", "ja"):
        surfaces = sorted(lex.keys(), key=len, reverse=True)
        i = 0
        while i < len(text):
            if text[i].isspace():
                i += 1
                continue
            matched = False
            for surface in surfaces:
                if text.startswith(surface, i):
                    val = lex[surface]
                    concept = val[0] if isinstance(val, tuple) else val
                    if isinstance(val, tuple) and val[0] not in ("?WHO", "?WHAT"):
                        meaning.setdefault("event", val[0])
                        if val[1]:
                            meaning.setdefault("tense", val[1])
                    elif concept in ("?WHO", "?WHAT"):
                        meaning["agent"] = concept
                    found_lex.append((surface, concept))
                    i += len(surface)
                    matched = True
                    break
            if not matched:
                i += 1
    else:
        tokens = re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]+", text)
        for tok in tokens:
            key = tok.lower()
            if key in lex:
                val = lex[key]
                concept = val[0] if isinstance(val, tuple) else val
                found_lex.append((key, concept))
                if isinstance(val, tuple) and val[0] not in ("?WHO", "?WHAT"):
                    meaning.setdefault("event", val[0])
                    if val[1]:
                        meaning.setdefault("tense", val[1])
                elif concept in ("?WHO", "?WHAT"):
                    meaning["agent"] = concept

    # Assign roles: first non-event content concept = agent (unless
    # already a wh-word), next = patient or location depending on the
    # presence of a locative cue. Latin markers need word boundaries
    # — bare "en" inside "Quién" must not count; CJK markers are
    # ideographs, no boundary issue.
    is_locative = _has_locative_marker(text, lang)

    content = [c for _, c in found_lex if c not in ("?WHO", "?WHAT")
               and c != meaning.get("event")]
    # Drop duplicates while preserving order.
    seen = set()
    content = [c for c in content if not (c in seen or seen.add(c))]
    if "agent" not in meaning and content:
        meaning["agent"] = content.pop(0)
    if content:
        # If locative cue present, last content concept becomes location.
        if is_locative:
            meaning["location"] = content[-1]
            for c in content[:-1]:
                meaning.setdefault("patient", c)
        else:
            meaning["patient"] = content[0]

    # Speech act from terminator + question word.
    if text.strip().endswith(("?", "？")) or "?" in text:
        meaning["speech_act"] = "question"

    # Build basic productions (a constant skeleton per language).
    PRODUCTIONS = {
        "en": ["S -> NP VP", "VP -> V NP", "VP -> V PP", "PP -> P NP", "NP -> Det N | N | PN"],
        "es": ["S -> NP VP", "VP -> V (se)? NP", "VP -> V PP", "PP -> P NP", "NP -> Det N | N | PN"],
        "zh": ["S -> NP VP", "VP -> V PP", "PP -> NP LOC", "NP -> N | PN"],
        "ja": ["S -> NP-ga (NP-o)? (NP-ni)? V", "NP -> N | PN", "Particles: が(NOM) を(ACC) に(DAT/LOC)"],
    }
    return {
        "language": lang,
        "meaning": meaning,
        "grammar_summary": f"stub heuristic for {lang}",
        "productions": PRODUCTIONS.get(lang, []),
        "lexicon": found_lex,
        "reasoning": f"teacher_stub: {lang} heuristic parse",
    }


def make_stub_teacher(extra_lexicon: dict[str, dict[str, Any]]):
    """Return a teacher_stub variant (NO LLM) that also knows ``extra_lexicon``
    — a {lang: {inflected_surface: concept|(concept,tense)}} table. Use it to
    ground a domain corpus's inflected forms so the production faculty emits
    them in reverse. The closure has the teacher(gap, text, hint) signature
    LanguageWorld expects."""
    def _teacher(gap_description: str, text: str,
                 language_hint: str | None = None) -> dict[str, Any]:
        return teacher_stub(gap_description, text, language_hint,
                            extra_lexicon=extra_lexicon)
    return _teacher


# ---------------------------------------------------------------------------
# Node + edge types the world adapter installs productions for. Per
# CLAUDE.md the productions are opened in __init__ so the Rust grammar
# admits the edges.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Slot-hint computation — a SURFACE classifier, the kind CLAUDE.md
# explicitly allows: "A thin I/O-boundary classifier is permitted (e.g.
# `if text.endswith('?') return 'question'`) when it is genuinely
# converting an opaque external form into the smallest graph token, AND
# there's no Rust primitive that can do the job."
#
# This helper takes a token position + the per-language particles /
# morphology and returns a slot string ("agent" / "patient" /
# "location" / "event") which is then STORED as an attr on the
# UnknownToken graph node. The agent's Rules consume it as a match
# condition — Python doesn't decide WHICH concept, only WHICH SLOT
# (a surface positional probe).
# ---------------------------------------------------------------------------


def _slot_hint_from_surface(pos: int, surface: str, tokens: list[str],
                            language: str,
                            slot_taken: set[str]) -> str | None:
    """Pure surface heuristic — no graph reads. Per-language morphology
    for the event slot; positional cues for agent/patient from
    particles / aspect markers; default left-to-right SVO fill of
    leftover slots."""
    # Event probe: shared with the parser's tense-detection.
    if _event_tense_probe(language, surface, surface) is not None:
        return "event" if "event" not in slot_taken else None
    # Per-language particle / aspect probes.
    if language == "ja":
        if pos + 1 < len(tokens):
            nxt = tokens[pos + 1]
            if nxt == "が":
                return "agent" if "agent" not in slot_taken else None
            if nxt == "を":
                return "patient" if "patient" not in slot_taken else None
    if language == "zh":
        if pos + 1 < len(tokens):
            nxt = tokens[pos + 1]
            if nxt == "了" and "event" not in slot_taken:
                return "event"
        # Bracketed-by-content: a content token with at least one
        # other content token on each side is most likely the verb.
        has_left = any(
            t not in _CJK_PARTICLES.get("zh", set())
            and t != surface
            and tokens.index(t) < pos
            for t in tokens
        )
        has_right = any(
            t not in _CJK_PARTICLES.get("zh", set())
            and t != surface
            and (pos < len(tokens) - 1 and tokens[pos + 1:].count(t) > 0)
            for t in tokens
        )
        if has_left and has_right and "event" not in slot_taken:
            return "event"
    # Default SVO heuristic — left-to-right, first unfilled role.
    # Order is SVO-positional: subject (agent) → verb (event) → object
    # (patient) → oblique (location). Crucially `event` is in the
    # default, not only behind the morphology probe — so an unseen
    # IRREGULAR verb (said/told/made/went…) that the surface-marker
    # probe can't catch still lands in the verb slot by POSITION (the
    # token after the subject), instead of falling through to patient.
    # Structural cue, no per-verb data. Language-specific particle/
    # aspect probes above still take precedence (SOV verbs are placed
    # by their particles / final position before this default runs).
    for role in ("agent", "event", "patient", "location"):
        if role not in slot_taken:
            return role
    return None


# Per-language determiner sets — boundary data for the `has_determiner`
# orthographic cue. A token immediately preceded by one of these is a
# common noun (the/a dog); a capitalized token with NO determiner is a
# proper noun (John). CJK has no articles, so the set is empty there and
# the proper-noun refinement falls back to the generic slot prior.
_DETERMINERS = {
    "en": {"a", "an", "the"},
    "es": {"el", "la", "los", "las", "un", "una", "unos", "unas"},
    "zh": set(),
    "ja": set(),
}


def _orthographic_cues(pos: int, surface_lower: str,
                       orig_tokens: list[str], tokens: list[str],
                       language: str) -> dict[str, Any]:
    """Mechanical surface/morphology cues for an UnknownToken.

    Pure string + immediate-context computation, no graph reads — the
    thin I/O-boundary classifier CLAUDE.md permits. Returns:
      is_capitalized: first char of the ORIGINAL-case surface is upper
      has_determiner: the immediately-preceding token is an article
      lemma:          surface with simple en inflection stripped
                      (-ed → base, -s → base); lowercased; non-en just
                      lowercased
      suffix_ed / suffix_s: raw morphological flags
    None of these are decisions about WHICH concept — only surface facts
    the rules read."""
    orig = orig_tokens[pos] if pos < len(orig_tokens) else surface_lower
    is_capitalized = bool(orig[:1].isupper())
    dets = _DETERMINERS.get(language, set())
    prev = tokens[pos - 1] if pos > 0 else ""
    has_determiner = prev in dets
    suffix_ed = bool(surface_lower.endswith("ed"))
    suffix_s = bool(surface_lower.endswith("s")
                    and not surface_lower.endswith("ss"))
    lemma = _lemmatize(surface_lower, language)
    return {
        "is_capitalized": is_capitalized,
        "has_determiner": has_determiner,
        "suffix_ed": suffix_ed,
        "suffix_s": suffix_s,
        "lemma": lemma,
    }


def _lemmatize(surface_lower: str, language: str) -> str:
    """Strip simple English inflection so the grounded concept gets a
    canonical name (chased → chase, dogs → dog). en-focused; other
    languages just lowercase (cross-lingual lemmatization needs data,
    documented as a boundary). Keep it deliberately small."""
    if language != "en":
        return surface_lower
    s = surface_lower
    # -ed past tense. English regular past is genuinely ambiguous between
    # "Xe"+d (chase→chased) and "X"+ed (walk→walked) without a lexicon;
    # we restore a final "e" when stripping "ed" would leave a stem
    # ending in a consonant that English rarely ends a bare verb on
    # (chas→chase). This is a heuristic; cross-checking against a real
    # lexicon is the documented data boundary.
    if s.endswith("ied") and len(s) > 4:
        return s[:-3] + "y"
    if s.endswith("ed") and len(s) > 3:
        stem = s[:-2]
        # Doubled final consonant (chatted→chat): drop one.
        if len(stem) >= 2 and stem[-1] == stem[-2] and stem[-1] not in "aeiou":
            return stem[:-1]
        # Silent-e elision: a stem ending in a single consonant preceded
        # by a vowel usually dropped a final "e" (chas→chase, lik→like,
        # mov→move). A consonant preceded by another consonant did not
        # (walk→walk, jump→jump). 'w'/'x'/'y' never take the restored e.
        if (len(stem) >= 2 and stem[-1] not in "aeiouwxy"
                and stem[-2] in "aeiou"):
            return stem + "e"
        return stem
    # -s plural / 3sg: dogs→dog, loves→love (keep e), kisses→kiss.
    if s.endswith("ies") and len(s) > 4:
        return s[:-3] + "y"
    if s.endswith("es") and len(s) > 3 and s[-3] in "sxzo":
        return s[:-2]
    if s.endswith("s") and not s.endswith("ss") and len(s) > 2:
        return s[:-1]
    return s


_NODE_TYPES = (
    "Language", "Grammar", "Production", "Lexicon", "LexEntry",
    "SemanticFrame", "LanguageObservation", "LanguageShape", "Concept",
    "UnknownToken", "Microtheory", "RolePrior", "SelectionalRestriction",
    "FunctionWord",
)
_EDGE_TYPES = (
    "has_grammar", "has_lexicon", "has_production", "has_entry",
    "entry_concept", "of_language", "has_shape", "of_frame",
    "frame_event", "frame_role", "observed_in",
    "has_unknown", "has_lex", "is_a", "has_function_word",
)


# ---------------------------------------------------------------------------
# The world adapter.
# ---------------------------------------------------------------------------


class LanguageWorld:
    """Bank of (text, language, expected_meaning) tasks across multiple
    languages. The substrate observes each sentence, identifies its
    language + abstract shape via TextShape, looks up its grounded
    (Grammar, Lexicon) for the language. On miss → teacher → ground →
    parse. Subsequent same-language sentences re-use the grounded
    grammar without further teacher calls.

    Public surface mirrors StructuredDataWorld: __init__, run, summary.
    """

    def __init__(self, substrate, tasks: list[dict],
                 teacher: Callable[..., dict],
                 teacher_disabled: bool = False):
        self.s = substrate
        self.tasks = list(tasks)
        self.teacher = teacher
        self.teacher_disabled = teacher_disabled
        # NodeID caches: language_code -> Language node, language_code ->
        # Grammar node, language_code -> Lexicon node.
        self._language_nodes: dict[str, Any] = {}
        self._grammar_nodes: dict[str, Any] = {}
        self._lexicon_nodes: dict[str, Any] = {}
        self._concept_nodes: dict[str, Any] = {}
        # language_code -> { surface_word: FunctionWord NodeID } — mirror of
        # grounded FunctionWord nodes (the substrate is the source of truth).
        self._function_word_cache: dict[str, dict[str, Any]] = {}
        # language_code -> { surface_word: concept_name } — the
        # in-memory mirror of grounded LexEntries. The substrate is
        # the source of truth; this is a query cache.
        self._lexicon_cache: dict[str, dict[str, str]] = {}
        # language_code -> list of production strings (mirror of
        # grounded Production nodes).
        self._production_cache: dict[str, list[str]] = {}
        # shape_key -> { 'language': str, 'last_frame': dict } so
        # cumulative same-shape sentences can hit a tighter cache.
        self._shape_cache: dict[str, dict[str, Any]] = {}
        # shape_key -> LanguageShape node ID
        self._shape_nodes: dict[str, Any] = {}
        self._teacher_call_count = 0
        # Per-parse scratchpad of inferred (position, surface, candidate,
        # weight) tuples — populated by _parse_with_grounded so run()
        # can surface inference examples in the per-task log.
        self._last_inferred: list[tuple[int, str, str, float]] = []
        # surface -> slot the substrate typed an inferred concept into,
        # rebuilt each parse from the emitted LexEntry attrs.
        self._last_inferred_slots: dict[str, str] = {}
        # token_position -> grounded FunctionWord node for the last parse —
        # the role assignment reads grammatical_role off these.
        self._last_function_words: dict[int, Any] = {}

        # Open productions so the Rust grammar admits the edges. Same
        # idiom as StructuredDataWorld: best-effort, swallow re-add.
        for nt_a in _NODE_TYPES:
            for nt_b in _NODE_TYPES:
                for et in _EDGE_TYPES:
                    try:
                        self.s.add_production({
                            "src": {"type": nt_a, "var": "a"},
                            "edge_type": et,
                            "tgt": {"type": nt_b, "var": "b"},
                            "where": None,
                            "weight": {"type": "Lit", "value": 1.0},
                            "provenance": "language_world",
                        })
                    except Exception:
                        pass

        self._reload_cache_from_graph()

        # Install the phase-composer language rules + seed conceptual
        # categories. Idempotent — if another adapter already installed
        # them, the rule-add / production-open are best-effort no-ops.
        try:
            pclr.install_phase_composer_language_rules(self.s)
        except Exception:
            pass

    # ----- graph-resident lookup ------------------------------------------

    def _reload_cache_from_graph(self) -> None:
        """Walk grounded Language / Lexicon / Production nodes and
        rebuild the in-memory caches. Lets a fresh world adapter
        attach to an already-trained substrate and pick up where
        the previous run left off (cold-load held-out evaluation)."""
        for lid in self.s.nodes("Language"):
            attrs = self.s.node(lid)["attrs"]
            code = attrs.get("code")
            if not code:
                continue
            self._language_nodes[code] = lid
            self._lexicon_cache.setdefault(code, {})
            self._production_cache.setdefault(code, [])
        for gid in self.s.nodes("Grammar"):
            attrs = self.s.node(gid)["attrs"]
            code = attrs.get("language")
            if code:
                self._grammar_nodes[code] = gid
        for lxid in self.s.nodes("Lexicon"):
            attrs = self.s.node(lxid)["attrs"]
            code = attrs.get("language")
            if code:
                self._lexicon_nodes[code] = lxid
        for eid in self.s.nodes("LexEntry"):
            attrs = self.s.node(eid)["attrs"]
            code = attrs.get("language")
            surface = attrs.get("surface")
            concept = attrs.get("concept")
            if code and surface and concept:
                self._lexicon_cache.setdefault(code, {})[surface] = concept
        for pid in self.s.nodes("Production"):
            attrs = self.s.node(pid)["attrs"]
            code = attrs.get("language")
            rule = attrs.get("rule")
            if code and rule:
                self._production_cache.setdefault(code, []).append(rule)
        for cid in self.s.nodes("Concept"):
            attrs = self.s.node(cid)["attrs"]
            name = attrs.get("name")
            if name and name not in self._concept_nodes:
                self._concept_nodes[name] = cid
        for sid in self.s.nodes("LanguageShape"):
            attrs = self.s.node(sid)["attrs"]
            key = attrs.get("name")
            if key:
                self._shape_nodes[key] = sid
        for fid in self.s.nodes("FunctionWord"):
            attrs = self.s.node(fid)["attrs"]
            code = attrs.get("language")
            surface = attrs.get("surface")
            if code and surface:
                self._function_word_cache.setdefault(code, {})[surface] = fid

    def _get_or_create_language(self, code: str, family: str | None = None):
        if code in self._language_nodes:
            return self._language_nodes[code]
        attrs = {"code": code, "language_name": _LANG_NAMES.get(code, code)}
        if family:
            attrs["family"] = family
        else:
            attrs["family"] = _LANG_FAMILIES.get(code, "unknown")
        nid = self.s.add_node("Language", attrs)
        self._language_nodes[code] = nid
        return nid

    def _get_or_create_grammar(self, code: str, summary: str = ""):
        if code in self._grammar_nodes:
            return self._grammar_nodes[code]
        nid = self.s.add_node("Grammar", {
            "language": code,
            "summary": summary,
        })
        self._grammar_nodes[code] = nid
        lang_nid = self._get_or_create_language(code)
        try:
            self.s.add_edge(lang_nid, "has_grammar", nid, None)
        except Exception:
            pass
        return nid

    def _get_or_create_lexicon(self, code: str):
        if code in self._lexicon_nodes:
            return self._lexicon_nodes[code]
        nid = self.s.add_node("Lexicon", {"language": code})
        self._lexicon_nodes[code] = nid
        lang_nid = self._get_or_create_language(code)
        try:
            self.s.add_edge(lang_nid, "has_lexicon", nid, None)
        except Exception:
            pass
        return nid

    def _get_or_create_concept(self, name: str):
        if name in self._concept_nodes:
            return self._concept_nodes[name]
        # Look up by name on the existing graph first — the substrate
        # may already hold this concept from another seed.
        for cid in self.s.nodes("Concept"):
            attrs = self.s.node(cid)["attrs"]
            if attrs.get("name") == name:
                self._concept_nodes[name] = cid
                return cid
        nid = self.s.add_node("Concept", {"name": name})
        self._concept_nodes[name] = nid
        return nid

    def _ground_function_words_in_text(self, text: str,
                                       language: str) -> None:
        """Ground every function-word token in ``text`` as a FunctionWord
        node (reference + grammar derived). Called on BOTH the teacher
        grounding path and the parse path, so production (which reads the
        grounded FunctionWord nodes back in reverse) has them available even
        when comprehension only ran the teacher pass. Mechanical: tokenize,
        try to ground each token, skip content words."""
        if language in ("zh", "ja"):
            # Single-grapheme particle scan: each known particle char grounds.
            for ch in text:
                try:
                    fwref.ground_function_word(self, ch, language)
                except Exception:
                    pass
        else:
            toks = [t.lower() for t in re.findall(
                r"[A-Za-zÁÉÍÓÚáéíóúÑñ]+", text)]
            for i, tok in enumerate(toks):
                nxt = toks[i + 1] if i + 1 < len(toks) else None
                try:
                    fwref.ground_function_word(self, tok, language, nxt)
                except Exception:
                    pass

    def _function_word_node(self, surface: str, language: str):
        """Look up a grounded FunctionWord node by (surface, language).
        Checks the cache, then the graph (source of truth). None if absent."""
        cached = self._function_word_cache.get(language, {}).get(surface)
        if cached is not None:
            return cached
        for fid in self.s.nodes("FunctionWord"):
            attrs = self.s.node(fid)["attrs"]
            if (attrs.get("language") == language
                    and attrs.get("surface") == surface):
                self._function_word_cache.setdefault(
                    language, {})[surface] = fid
                return fid
        return None

    def _grounded_voice_feature(self, surface: str, language: str) -> str | None:
        """The `voice_feature` tag (past / plural / comparative / ...) on the
        grounded LexEntry for (surface, language), or None if none carries
        one. A mechanical read of graph data a voice-curriculum morphology
        lesson grounded (see `_add_lex_entry`'s voice_feature param). Reads
        the substrate directly (source of truth); the O(N) scan is fine at
        the modest lexicon sizes this runs at."""
        for eid in self.s.nodes("LexEntry"):
            a = self.s.node(eid)["attrs"]
            if (a.get("language") == language and a.get("surface") == surface
                    and a.get("voice_feature")):
                return a.get("voice_feature")
        return None

    def _get_or_create_shape(self, shape_key: str, shape_dict: dict[str, Any]):
        if shape_key in self._shape_nodes:
            return self._shape_nodes[shape_key]
        attrs = {"name": shape_key}
        for k, v in shape_dict.items():
            if isinstance(v, (str, int, float, bool)):
                attrs[k] = v
        nid = self.s.add_node("LanguageShape", attrs)
        self._shape_nodes[shape_key] = nid
        return nid

    def _add_lex_entry(self, code: str, surface: str, concept: str,
                       tentative: bool = False, weight: float = 1.0,
                       source: str = "teacher",
                       voice_feature: str | None = None):
        if self._lexicon_cache.get(code, {}).get(surface) == concept:
            return
        lex_nid = self._get_or_create_lexicon(code)
        concept_nid = self._get_or_create_concept(concept)
        attrs = {
            "language": code,
            "surface": surface,
            "concept": concept,
            "status": "tentative" if tentative else "confirmed",
            "weight": float(weight),
            "source": "context_inferred" if tentative else source,
        }
        # VOICE-EXPANSION: an OPTIONAL morphological feature tag on the entry
        # (past / past_participle / plural / comparative / superlative), from
        # the UniMorph feature column when a voice-curriculum morphology
        # lesson grounds an inflected surface. It is the reference's own
        # feature datum, not a decision -- production reads it to select the
        # inflected surface by the goal's requested feature, and comprehension
        # reads it to recover tense from an irregular past whose SURFACE the
        # morphology probe can't classify. Absent on every non-morphology
        # entry, so all existing behaviour is byte-identical.
        if voice_feature:
            attrs["voice_feature"] = voice_feature
        entry_nid = self.s.add_node("LexEntry", attrs)
        try:
            self.s.add_edge(lex_nid, "has_entry", entry_nid, None)
        except Exception:
            pass
        try:
            self.s.add_edge(entry_nid, "entry_concept", concept_nid, None)
        except Exception:
            pass
        self._lexicon_cache.setdefault(code, {})[surface] = concept

    def _add_production(self, code: str, rule: str):
        if rule in self._production_cache.get(code, []):
            return
        grammar_nid = self._get_or_create_grammar(code)
        prod_nid = self.s.add_node("Production", {
            "language": code,
            "rule": rule,
        })
        try:
            self.s.add_edge(grammar_nid, "has_production", prod_nid, None)
        except Exception:
            pass
        self._production_cache.setdefault(code, []).append(rule)

    # ----- shape + identification ----------------------------------------

    def _compute_shape(self, text: str) -> dict[str, Any]:
        """Evaluate the enriched TextShape primitive on the input."""
        term = srs.TextShape(srs.Lit(text))
        return self.s.evaluate(term._json, None)

    def _identify(self, text: str,
                  hint: str | None = None) -> tuple[str, str, dict[str, Any]]:
        """Identify (language, shape_key, shape_dict) for a text.
        Language hint (from the task bank) is used if supplied; else
        detected from script-distribution. Shape is from TextShape."""
        shape = self._compute_shape(text)
        language = hint or _detect_language(text)
        shape_key = _language_shape_key(language, shape)
        return language, shape_key, shape

    # ----- parse-from-grounded-grammar -----------------------------------

    def _parse_with_grounded(self, text: str, language: str,
                             shape: dict[str, Any]) -> dict[str, Any]:
        """Parse `text` using the grounded Lexicon + speech-act / tense
        cues from TextShape. Returns a semantic-frame dict.

        World-adapter I/O only: walks the in-memory lexicon mirror (which
        is the cache of LexEntry nodes); composes the frame. Unknown
        content words are NOT inferred here — they're handed to the
        substrate as UnknownToken nodes wired to the
        phase_composer_language_trigger Microtheory; the graph-resident
        Rules in domains/phase_composer_language_rules.py fire on tick()
        and emit LexEntry nodes carrying the inferred concept. The world
        adapter then reads the LexEntries back out.

        Per CLAUDE.md: NO Python decisions about candidate concepts /
        slot scoring / animacy bonuses live in this file. The slot-hint
        the world adapter passes to each UnknownToken is the only
        adapter-side classification — and it's purely a surface-position
        / surface-morphology computation (no graph reads), the kind
        CLAUDE.md allows as a thin I/O-boundary helper."""
        lex = self._lexicon_cache.setdefault(language, {})
        # NOTE: an empty grounded lexicon is NO LONGER a hard stop. The
        # WordNet dictionary layer (see _infer_unknowns_via_substrate) can
        # supply vocabulary for content words even on a cold substrate, so
        # we proceed and let the dictionary / context-typing fill the slots.
        # Tokenize per writing system.
        tokens: list[str] = []
        # Original-case surfaces, parallel to `tokens` for latin scripts
        # (CJK has no case). Used to compute the orthographic
        # `is_capitalized` cue at the I/O boundary without polluting the
        # lowercased lexicon lookups.
        orig_tokens: list[str] = []
        if language in ("zh", "ja"):
            # Greedy longest-match against the grounded lexicon. For
            # un-matched contiguous runs of CJK chars we accumulate
            # them into a single "chunk" token so the inferer sees one
            # candidate-surface per word-shape rather than one per char.
            # Particles (single hiragana like が / を / に / は / で /
            # の) are emitted as their own single-char tokens so they
            # don't get absorbed into a content chunk and so the slot-
            # guess can read the next particle.
            cjk_particles = _CJK_PARTICLES.get(language, set())
            surfaces = sorted(lex.keys(), key=len, reverse=True)
            i = 0
            chunk: list[str] = []
            while i < len(text):
                if text[i].isspace():
                    if chunk:
                        tokens.append("".join(chunk))
                        chunk = []
                    i += 1
                    continue
                matched = False
                for surf in surfaces:
                    if text.startswith(surf, i):
                        if chunk:
                            tokens.append("".join(chunk))
                            chunk = []
                        tokens.append(surf)
                        i += len(surf)
                        matched = True
                        break
                if matched:
                    continue
                ch = text[i]
                cp = ord(ch)
                is_cjk = (0x4E00 <= cp <= 0x9FFF
                          or 0x3040 <= cp <= 0x309F
                          or 0x30A0 <= cp <= 0x30FF
                          or ch == "ー")
                is_punct = (0x3000 <= cp <= 0x303F) or ch in ("。", "？", "、")
                if is_punct:
                    if chunk:
                        tokens.append("".join(chunk))
                        chunk = []
                    i += 1
                    continue
                if ch in cjk_particles:
                    if chunk:
                        tokens.append("".join(chunk))
                        chunk = []
                    tokens.append(ch)
                    i += 1
                    continue
                if is_cjk:
                    chunk.append(ch)
                i += 1
            if chunk:
                tokens.append("".join(chunk))

            # For zh (no word boundary markers, no compulsory particles
            # between every word), an unknown multi-char chunk could be
            # any combination of {1-char word, 2-char word}. We don't
            # have a segmenter; split unknown chunks into single-char
            # tokens so each char gets its own inference candidate.
            # ja relies on particles for segmentation so multi-char
            # chunks there are genuinely one word — leave them whole.
            if language == "zh":
                expanded: list[str] = []
                for tok in tokens:
                    if tok in lex or tok in cjk_particles:
                        expanded.append(tok)
                    elif len(tok) > 1 and all(
                            0x4E00 <= ord(c) <= 0x9FFF for c in tok):
                        # Unknown multi-han chunk → one token per char.
                        expanded.extend(list(tok))
                    else:
                        expanded.append(tok)
                tokens = expanded
        else:
            raw = re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]+", text)
            # MULTI-WORD lexicon match (latin). A grounded LexEntry whose SURFACE
            # contains a space (e.g. a named entity re-exposed by a reader bridge,
            # "justice department") is a single lexical item, so it must tokenize
            # as ONE token to resolve to its concept — the same greedy longest-
            # match the CJK path above already does, applied here over whitespace
            # words. GATED on the existence of spaced grounded surfaces: when the
            # lexicon has none (every existing en/es world), `phrases` is empty and
            # this loop is byte-identical to the previous per-word regex split.
            phrases = sorted(
                (s for s in lex if isinstance(s, str) and " " in s),
                key=lambda s: len(s.split()), reverse=True)
            phrase_words = [(p, p.split()) for p in phrases]
            i = 0
            while i < len(raw):
                matched = False
                lowered = [w.lower() for w in raw]
                for surf, pw in phrase_words:
                    k = len(pw)
                    if k and lowered[i:i + k] == pw:
                        orig_tokens.append(" ".join(raw[i:i + k]))
                        tokens.append(surf)
                        i += k
                        matched = True
                        break
                if matched:
                    continue
                orig_tokens.append(raw[i])
                tokens.append(raw[i].lower())
                i += 1

        # For CJK, orig == tokens (no case distinction).
        if not orig_tokens:
            orig_tokens = list(tokens)

        # First pass: resolve what we already know. A token that doesn't
        # resolve to a content concept is checked against the FUNCTION-WORD
        # references (Wiktionary POS / the grounded particle set). When it
        # IS a function word we GROUND it as a FunctionWord node (carrying
        # function + the grammatical_role the grounded grammar assigns) and
        # record (position, FunctionWord node) so the role-assignment can
        # use it — instead of FILTERING it out. Only genuine unknown content
        # words go to inference.
        resolved: list[tuple[str, str]] = []
        unknown_positions: list[tuple[int, str]] = []
        # pos -> grounded FunctionWord node id for this parse.
        function_word_at: dict[int, Any] = {}
        skip_tokens = _CJK_PARTICLES.get(language, set())
        for pos, tok in enumerate(tokens):
            concept = lex.get(tok)
            # LEMMA fallback: do-support strands a BARE verb stem ("...does
            # John LIVE?") whose surface differs from the grounded inflected
            # form ("lives" -> live). When the exact surface misses, try the
            # surface's lemma (chased->chase, lives->live) and the +s/+ed
            # inflections of it, so the bare stem resolves to the concept the
            # inflected form grounded. Pure surface morphology (the permitted
            # I/O-boundary helper); en-only (other langs just lowercase).
            if not concept and language == "en":
                lemma = _lemmatize(tok, language)
                concept = (lex.get(lemma) or lex.get(lemma + "s")
                           or lex.get(lemma + "es") or lex.get(lemma + "d")
                           or lex.get(lemma + "ed"))
            if concept:
                resolved.append((tok, concept))
                continue
            # INTERROGATIVE PROFORM (closed-class wh->role fact). A wh-word
            # resolves to its language-neutral placeholder (?WHO … ?HOW)
            # straight from interrogative_reference — it does NOT need a
            # grounded LexEntry, because it is a finite closed class (the
            # same status as the do-support auxiliaries). The placeholder is
            # the queried-slot marker the downstream stack keys on.
            proform = ireg.proform_placeholder(tok, language)
            if proform is not None:
                resolved.append((tok, proform))
                continue
            # Function-word grounding (reference + grounded grammar derived).
            nxt = tokens[pos + 1] if pos + 1 < len(tokens) else None
            fw_nid = None
            try:
                fw_nid = fwref.ground_function_word(self, tok, language, nxt)
            except Exception:
                fw_nid = None
            if fw_nid is not None:
                function_word_at[pos] = fw_nid
                continue
            # Legacy fallback sets (offline / no Wiktionary extract): still
            # treat known function words / relations / particles as
            # non-content so the inferer isn't polluted.
            if (tok in _LATIN_FUNCTION_WORDS.get(language, set())
                    or tok in _RELATION_CONCEPTS
                    or tok in skip_tokens):
                continue
            unknown_positions.append((pos, tok))
        self._last_function_words = function_word_at

        # Context-weighted inference for unknown content words —
        # delegated to the substrate. The world adapter creates an
        # UnknownToken per unknown content position, wires each to the
        # phase_composer_language_trigger Mt, and lets the
        # graph-resident Rules fire on tick() to emit LexEntry nodes.
        # The adapter then reads the inferred LexEntries back out
        # mechanically — no Python decision logic between create and
        # read.
        inferred_records: list[tuple[int, str, str, float]] = []
        if unknown_positions:
            # Predicate of the sentence = the resolved (already-known)
            # concept whose surface morphology marks it a verb. A
            # mechanical surface fact handed to the rules so a KNOWN
            # predicate's selectional restriction can type the unknown;
            # None when the verb itself is unseen (the John/dog demos).
            known_predicate: str | None = None
            for surf, concept in resolved:
                if _event_tense_probe(language, surf, concept) is not None:
                    known_predicate = concept
                    break
            inferred_records = self._infer_unknowns_via_substrate(
                tokens, orig_tokens, unknown_positions, resolved, language,
                text, known_predicate)
            persist = self.teacher_disabled
            inferred_lex: dict[str, str] = {}
            for pos, surface, candidate, weight in inferred_records:
                if persist:
                    self._add_lex_entry(language, surface, candidate,
                                        tentative=True, weight=weight)
                else:
                    inferred_lex[surface] = candidate
            # Replay tokens through the augmented (in-parse) lexicon so
            # position ordering is preserved.
            resolved = []
            for tok in tokens:
                concept = lex.get(tok) or inferred_lex.get(tok)
                if concept:
                    resolved.append((tok, concept))
        self._last_inferred = inferred_records

        # Position-aware resolved list (surface, concept, token_position) so
        # the role assignment can ask, per content noun, whether an ADJACENT
        # grounded FunctionWord marks it as a location. Rebuilt from `tokens`
        # order to stay aligned with `function_word_at`.
        resolved_pos: list[tuple[str, str, int]] = []
        for tpos, tok in enumerate(tokens):
            concept = lex.get(tok) or (
                {s: c for _, s, c, _ in inferred_records}.get(tok)
                if inferred_records else None)
            if concept is None:
                concept = next((c for s, c in resolved if s == tok), None)
            if concept:
                resolved_pos.append((tok, concept, tpos))

        frame: dict[str, Any] = {}
        # Event = the first resolved concept that maps to one of the
        # canonical event concepts. We don't know which mapping is the
        # event a-priori; pick a concept whose surface is morphologically
        # a verb-ish form (-ed/-ing/-s/sentó/rompió/persiguió/...). For
        # simplicity: an event is any concept that is also the target
        # of a tense-marker heuristic per language. We look at all
        # resolved concepts and select the one matching the per-language
        # event-marker probe.
        event_concept: str | None = None
        tense: str | None = None
        for surf, concept in resolved:
            t = _event_tense_probe(language, surf, concept)
            if t is not None:
                event_concept = concept
                tense = t
                break

        # Fallback: honour the substrate's own typing. If the morphology
        # probe found no event but the substrate TYPED an inferred token
        # into the `event` slot, that typed concept IS the event. (Reads
        # graph-decided slot data; the adapter only relays it.) This is
        # what lets a brand-new verb with no morphological tense hook
        # — e.g. an unseen Mandarin verb — still fill the event slot.
        if event_concept is None and self._last_inferred_slots:
            for surf, concept in resolved:
                if self._last_inferred_slots.get(surf) == "event":
                    event_concept = concept
                    break

        # VOICE-EXPANSION fallback: an IRREGULAR past whose SURFACE the
        # per-language morphology probe cannot classify ("brought"/"sang" --
        # no -ed, not in the tiny hard-coded irregular list) is recovered from
        # the GROUNDED LexEntry's own `voice_feature` tag (grounded by a
        # voice-curriculum morphology lesson from the UniMorph feature column).
        # This is the round-trip twin of production's feature-aware selection:
        # the graph fact the morphology lesson grounded, read back to recover
        # the tense the bare surface-morphology probe misses. GATED on a
        # grounded voice_feature -- no existing entry carries one, so every
        # pre-voice-curriculum parse is byte-identical.
        if event_concept is None:
            for surf, concept in resolved:
                feat = self._grounded_voice_feature(surf, language)
                if feat in ("past", "past_participle"):
                    event_concept = concept
                    tense = "past"
                    break

        # DO-SUPPORT reconstruction (en do-insertion). When a grounded
        # AUXILIARY FunctionWord (do/does/did, function=auxiliary) is present,
        # English has stranded the clause TENSE on that dummy auxiliary and
        # left the lexical verb a BARE STEM ("...does Mary LOVE?", "...did the
        # cat BREAK?"). The morphology probe keys off -ed/-s/irregular surface,
        # so it never flags the bare verb — the event slot is lost and the
        # tense floats on the auxiliary. Recover both from grounded cues:
        #   EVENT  = the bare lexical verb following the auxiliary (skipping the
        #            intervening inverted-subject NP) — a grounded do-support
        #            cue, not a keyword test.
        #   TENSE  = the auxiliary form's tense, reference-derived from the
        #            morphology reference (did->past, do/does->present).
        ds_event, ds_tense = self._do_support_event_tense(
            resolved_pos, tokens, language)
        if ds_event is not None:
            event_concept = ds_event
            tense = ds_tense

        # COMPARATIVE construction (a grammatical construction, not a lexical
        # fact). "[subj] is [ADJ-er] than [standard]" realizes a transitive
        # ordering relation R(subj, standard). When a comparative-degree form
        # (cmpref: -er morphology / grounded comparative) AND a grounded
        # standard-marker ('than'/'que', a FunctionWord) are present, the
        # comparative adjective IS the event (the relation) and the NP after the
        # marker is the `standard`. Detected here so the relation is excluded
        # from the noun (agent/patient) assignment below. comp_standard_pos is
        # the standard NP's token position (filled after marker detection).
        comp_relation: str | None = None
        comp_standard_pos: int | None = None
        if event_concept is None:
            for surf, concept, tpos in resolved_pos:
                rel = cmpref.comparative_relation(surf, concept, language)
                if rel is not None:
                    comp_relation = rel
                    event_concept = rel
                    break
        if comp_relation is not None:
            # The standard marker is a grounded function word ('than'); the
            # standard is the nearest content noun AFTER it. Read the grounded
            # FunctionWord set + the closed-class marker membership.
            for mpos, tok in enumerate(tokens):
                if not cmpref.is_standard_marker(tok, language):
                    continue
                # Confirm it grounded as a function word (not a bare keyword).
                if self._function_word_node(tok, language) is None:
                    try:
                        fwref.ground_function_word(self, tok, language)
                    except Exception:
                        pass
                j = mpos + 1
                content_set = {tp for _, _, tp in resolved_pos}
                while j < len(tokens) and j not in content_set:
                    j += 1
                if j < len(tokens):
                    comp_standard_pos = j
                break

        if event_concept:
            frame["event"] = event_concept
            if tense:
                frame["tense"] = tense

        # Speech act + question agent.
        is_question = (shape.get("terminator") == "question"
                       or "?" in text or "？" in text)
        # Agent / patient / location assignment — POSITION-aware so the
        # grounded FunctionWord adjacent to each content noun can tag its
        # role (the locative round-trip fix). Build the ordered list of
        # (concept, token_position) for non-event, non-relation content
        # concepts, de-duplicated, preserving surface order.
        # OBLIQUE interrogative proforms (where/when/why/how) query a FIXED
        # non-core slot (location/time/cause/manner) named by the closed-class
        # wh->role fact (interrogative_reference). They need NO gap
        # reconstruction — the placeholder drops straight into its queried slot
        # — and they must NOT compete for the agent/patient SVO assignment. So
        # set them here and exclude them from `other`. PARTICIPANT proforms
        # (?WHO/?WHAT) still flow through the wh-gap logic below.
        oblique_entry = next(
            ((tok, c, tpos) for tok, c, tpos in resolved_pos
             if ireg.is_oblique(c)), None)
        if oblique_entry is not None and is_question:
            obl_slot = ireg.queried_slot_for(oblique_entry[1])
            if obl_slot:
                frame[obl_slot] = oblique_entry[1]

        wh_entry = next(((tok, c, tpos) for tok, c, tpos in resolved_pos
                         if c in ("?WHO", "?WHAT")), None)
        wh_concept = wh_entry[1] if wh_entry else None
        wh_surface = wh_entry[0] if wh_entry else None
        wh_pos = wh_entry[2] if wh_entry else None
        # COMPARATIVE: the standard NP fills the `standard` role; exclude it
        # (and the comparative relation itself, already the event) from the
        # agent/patient noun assignment.
        if comp_standard_pos is not None:
            std_concept = next((c for _, c, tp in resolved_pos
                                if tp == comp_standard_pos), None)
            if std_concept is not None:
                frame["standard"] = std_concept

        other: list[tuple[str, int]] = []
        seen_c: set[str] = set()
        for _, c, tpos in resolved_pos:
            if c in ("?WHO", "?WHAT") or ireg.is_oblique(c) or c == event_concept:
                continue
            if tpos == comp_standard_pos:
                continue
            if c.lower() in _RELATION_CONCEPTS:
                continue
            if c in seen_c:
                continue
            seen_c.add(c)
            other.append((c, tpos))

        # Which content noun (by token position) bears a THEMATIC ROLE from a
        # grounded FunctionWord? Reads the FunctionWord nodes the parse
        # grounded (graph data — the role is VerbNet-derived for prepositions),
        # not a Python `if word == "on"`. {tpos: role}.
        content_positions = {tpos for _, _, tpos in resolved_pos}
        role_positions = self._role_marked_positions(
            tokens, self._last_function_words, content_positions, language)

        # wh-GAP RECONSTRUCTION. A FRONTED wh-word in an interrogative may fill
        # the SUBJECT gap (subject-wh: "Who broke the vase?" -> agent) or the
        # OBJECT gap (object-wh: "Who does Mary love?" -> patient, with the
        # intervening NP the agent). Which one is read off GROUNDED cues — an
        # object case-marker on the wh (ja を / es personal-a), do-support +
        # subject-aux inversion (a grounded AUXILIARY between the fronted wh and
        # the main verb, with an intervening subject NP), or explicit "whom".
        # The wh then fills the queried GAP role; the bound NP fills agent.
        wh_gap_role: str | None = None
        if wh_concept is not None and is_question:
            wh_gap_role = self._wh_gap_role(
                wh_surface, wh_pos, tokens, content_positions,
                role_positions, event_concept, resolved_pos, language)

        if wh_concept and wh_gap_role:
            # OBJECT-wh (or other marked gap): the wh fills its grounded role
            # (を/personal-a -> patient); the intervening content NP -> agent.
            frame[wh_gap_role] = wh_concept
            # The marked wh position no longer competes for its content role.
            role_positions.pop(wh_pos, None)
            if other:
                # First content NP not otherwise role-marked = the subject.
                unmarked = [(c, tpos) for c, tpos in other
                            if tpos not in role_positions]
                pick = unmarked[0] if unmarked else other[0]
                frame["agent"] = pick[0]
                other.remove(pick)
        elif wh_concept:
            # SUBJECT-wh — unchanged: the wh is the queried agent.
            frame["agent"] = wh_concept
        elif other:
            # The agent is the first content noun NOT marked with an oblique
            # role by a preposition/particle (so "to John" can't become the
            # agent). Falls back to the first noun when all are marked.
            unmarked = [(c, tpos) for c, tpos in other
                        if tpos not in role_positions]
            if unmarked:
                pick = unmarked[0]
                frame["agent"] = pick[0]
                other.remove(pick)
            else:
                frame["agent"] = other.pop(0)[0]

        # Assign the remaining content nouns: a role-marked noun fills its
        # marked role; an unmarked noun falls to patient (the direct object).
        # When several nouns carry the SAME role, the last one wins (matches
        # the prior location behaviour). Fine roles (recipient/instrument/
        # source/beneficiary/topic) come straight from the grounded
        # FunctionWord; location is the coarse spatial role as before.
        for c, tpos in other:
            role = role_positions.get(tpos)
            if role:
                frame[role] = c
            else:
                frame.setdefault("patient", c)

        if is_question:
            frame["speech_act"] = "question"
            # POLAR (yes/no) question: no interrogative proform present AND the
            # clause is copula/auxiliary-INITIAL (subject-aux inversion with
            # nothing fronted). Read from grounded data: no ?WH placeholder in
            # the frame + the first token grounded as a copula/auxiliary
            # FunctionWord. A polar comparative ("Is the cat bigger than the
            # mouse?") routes to reason_transitive downstream.
            has_wh = any(frame.get(s) in ireg.ALL_PLACEHOLDERS
                         for s in _FRAME_ROLES + ("agent", "patient"))
            if not has_wh:
                first_fw = self._last_function_words.get(0)
                first_fn = None
                if first_fw is not None:
                    try:
                        first_fn = self.s.node(first_fw)["attrs"].get("function")
                    except Exception:
                        first_fn = None
                if first_fn in ("copula", "auxiliary"):
                    frame["polar"] = True

        return frame

    # ----- grounded-function-word role marking ----------------------------

    def _role_marked_positions(self, tokens: list[str],
                               function_word_at: dict[int, Any],
                               content_positions: set[int],
                               language: str) -> dict[int, str]:
        """Map content-noun token positions -> the THEMATIC ROLE a grounded
        FunctionWord marks on them. Reads each FunctionWord node's
        grammatical_role + attaches attrs (graph data — the role is
        VerbNet-derived for prepositions, grammar-derived for particles) and
        applies them to the nearest CONTENT noun:
          * attaches=="precedes" (en/es prepositions): the content noun
            AFTER the function word, skipping intervening function words.
          * attaches=="follows" (ja/zh particles): the content noun BEFORE
            the function word, skipping intervening function words (の, 上 …).
        Roles are the fine-grained inventory: recipient / instrument / source
        / beneficiary / topic / location / ... Driven entirely by the grounded
        node attrs, not by the literal surface word."""
        marked: dict[int, str] = {}
        n = len(tokens)
        for fpos, fnid in function_word_at.items():
            try:
                attrs = self.s.node(fnid)["attrs"]
            except Exception:
                continue
            role = attrs.get("grammatical_role")
            if not role:
                continue
            attaches = attrs.get("attaches")
            if attaches == "follows":
                # Walk left to the nearest CONTENT token.
                j = fpos - 1
                while j >= 0 and j not in content_positions:
                    j -= 1
                if j >= 0:
                    marked[j] = role
            else:  # "precedes" (prepositions/determiners)
                j = fpos + 1
                while j < n and j not in content_positions:
                    j += 1
                if j < n:
                    marked[j] = role
        return marked

    # ----- do-support event + tense reconstruction -----------------------

    def _do_support_event_tense(
            self, resolved_pos: list[tuple[str, str, int]],
            tokens: list[str], language: str
    ) -> tuple[str | None, str | None]:
        """Reconstruct the (event, tense) stranded by English do-support.

        English do-insertion puts a dummy auxiliary (do/does/did) that carries
        the clause tense+agreement before a BARE lexical verb in questions /
        negation ("...does Mary LOVE?", "...did the cat BREAK?"). The
        morphology probe (_event_tense_probe) keys off -ed/-s/irregular surface
        and so never flags the bare verb, dropping the event slot and leaving
        the tense on the auxiliary.

        Reads only GROUNDED data:
          * the auxiliary is the grounded FunctionWord with function=auxiliary
            (self._last_function_words) — the do-support cue, reused from the
            object-wh handling; NOT a Python ``if word in {do,does,did}``.
          * the EVENT is the first content concept whose token position follows
            the auxiliary (the intervening inverted-subject NP is skipped
            automatically — the verb is simply the LAST content token after the
            aux, but taking the first content token that the morphology probe
            did NOT already type as a verb and that sits after the subject is
            unnecessary: in do-support the lexical verb is the bare stem at/near
            the clause end, so we take the last post-aux content concept).
          * the TENSE comes from the auxiliary surface via the morphology
            reference (morph.auxiliary_tense: did->past, do/does->present).

        Returns (None, None) when no grounded auxiliary is present (the
        non-do-support path is untouched)."""
        fw_at = self._last_function_words or {}
        # Find a grounded auxiliary FunctionWord (do-support cue).
        aux_pos: int | None = None
        aux_surface: str | None = None
        for pos, nid in fw_at.items():
            try:
                attrs = self.s.node(nid)["attrs"]
            except Exception:
                continue
            if attrs.get("function") == "auxiliary":
                # Earliest auxiliary anchors the do-support clause.
                if aux_pos is None or pos < aux_pos:
                    aux_pos = pos
                    aux_surface = attrs.get("surface")
        if aux_pos is None:
            return (None, None)

        # TENSE from the auxiliary form (reference-derived). If the surface
        # isn't one of the closed do-support auxiliaries (e.g. a perfect
        # have/has/had or modal will), this returns None and we leave tense
        # unset rather than guess — do-insertion proper is do/does/did.
        if aux_surface is None:
            aux_surface = tokens[aux_pos] if aux_pos < len(tokens) else None
        ds_tense = morph.auxiliary_tense(aux_surface or "", language)
        if ds_tense is None:
            # Not a tense-bearing do-support auxiliary — not our case.
            return (None, None)

        # EVENT = the bare lexical verb after the auxiliary. The inverted
        # subject NP sits between the aux and the verb; the verb is the LAST
        # content concept of the post-aux span (the clause-final bare stem),
        # which skips the intervening subject NP without naming it.
        post_aux = [(c, tpos) for _, c, tpos in resolved_pos
                    if tpos > aux_pos and c not in ("?WHO", "?WHAT")]
        if not post_aux:
            return (None, None)
        post_aux.sort(key=lambda ct: ct[1])
        ds_event = post_aux[-1][0]
        return (ds_event, ds_tense)

    # ----- wh-gap reconstruction (subject-wh vs object-wh) ----------------

    def _wh_gap_role(self, wh_surface: str | None, wh_pos: int | None,
                     tokens: list[str], content_positions: set[int],
                     role_positions: dict[int, str], event_concept: str | None,
                     resolved_pos: list[tuple[str, str, int]],
                     language: str) -> str | None:
        """Decide whether a FRONTED interrogative wh-word fills the OBJECT gap.

        Returns the GAP ROLE the wh fills (``patient`` / a finer object role)
        when this is an OBJECT-wh question, or ``None`` for a SUBJECT-wh
        question (wh -> agent, the existing behaviour).

        The decision is read off GROUNDED data the agent already has, not a
        hardcoded English rule:

          * The wh carries/precedes a grounded OBJECT case-marker — Japanese
            を (``grammatical_role=patient``, ``attaches=follows``) gives the wh
            position a role directly in ``role_positions``; Spanish personal-``a``
            (a grounded *preposition* FunctionWord, left role-UNMAPPED for the
            recipient/patient ambiguity) immediately precedes the fronted wh,
            which in an interrogative is the object marker -> patient.
          * English do-support + subject-aux inversion — a grounded AUXILIARY
            FunctionWord (do/does/did, ``function=auxiliary``) sits between the
            fronted wh and the main verb, with an intervening subject NP. The
            inversion is the object-wh signal; the wh fills the object gap.
          * Explicit object wh — the surface is ``whom``.

        The wh must be FRONTED (no CONTENT token precedes it) for the
        aux/personal-a cues; the case-marker cue (を) holds regardless. Fronting
        is a mechanical sentence-boundary cue (allowed); everything else reads
        grounded FunctionWord nodes."""
        if wh_pos is None:
            return None

        # (a) Grounded OBJECT case-marker already on the wh position (ja を ->
        # patient; any object-marking particle/preposition that role-marked it).
        # The SUBJECT markers (が agent, は topic) are NOT object gaps — a
        # wh marked agent/topic stays SUBJECT-wh (the existing behaviour).
        marked_role = role_positions.get(wh_pos)
        if marked_role and marked_role not in ("agent", "topic"):
            return marked_role

        # Is the wh FRONTED? (No content token to its left.)
        fronted = not any(tpos < wh_pos for tpos in content_positions)

        # (b) Explicit object wh.
        if fronted and wh_surface and wh_surface.lower() == "whom":
            return "patient"

        fw_at = self._last_function_words or {}

        def _fw_function(pos: int) -> str | None:
            nid = fw_at.get(pos)
            if nid is None:
                return None
            try:
                return self.s.node(nid)["attrs"].get("function")
            except Exception:
                return None

        # (c) Spanish personal-`a`: a grounded PREPOSITION FunctionWord directly
        # before the fronted wh. (es `a` is grounded role-UNMAPPED; in a wh
        # question `a quién` is the object.)
        if fronted and _fw_function(wh_pos - 1) == "preposition":
            return "patient"

        # (d) en do-support + subject-aux inversion: a grounded AUXILIARY after
        # the fronted wh and before the main verb (event), with an intervening
        # subject NP (a content noun between the aux and the verb).
        if not fronted:
            return None
        event_pos = next((tpos for _, c, tpos in resolved_pos
                          if c == event_concept), None)
        aux_pos = None
        for pos in range(wh_pos + 1, len(tokens)):
            if event_pos is not None and pos >= event_pos:
                break
            if _fw_function(pos) == "auxiliary":
                aux_pos = pos
                break
        if aux_pos is None:
            return None
        # An intervening SUBJECT NP between the aux and the verb (the inverted
        # subject). Bounded by the verb position when known, else end of clause.
        right = event_pos if event_pos is not None else len(tokens)
        has_subject_np = any(aux_pos < tpos < right
                             and tpos != wh_pos
                             for tpos in content_positions)
        if has_subject_np:
            return "patient"
        return None

    # ----- context-weighted inference of unknown words --------------------

    def _infer_unknowns_via_substrate(
            self, tokens: list[str],
            orig_tokens: list[str],
            unknown_positions: list[tuple[int, str]],
            resolved: list[tuple[str, str]],
            language: str,
            text: str,
            known_predicate: str | None = None) -> list[tuple[int, str, str, float]]:
        """Hand each unknown content token to the substrate.

        World-adapter mechanics:
          1. Compute a slot HINT for each unknown — pure surface
             positional / morphological classification (no graph
             reads). The slot string ("agent" / "patient" /
             "location" / "event") is the only adapter-side semantic
             decision; the agent's graph-resident Rules read it as a
             match condition and pick the concept.
          2. Create an UnknownToken node per unknown carrying
             {word, slot, language, position, sentence_id}.
          3. Wire each UnknownToken to the
             phase_composer_language_trigger Microtheory via
             has_unknown so the rules match it.
          4. Call substrate.tick() — the phase composer rules fire,
             emitting LexEntry nodes wired to each UnknownToken via
             has_lex.
          5. Walk has_lex and read each LexEntry's `concept` attr;
             that's the inferred candidate. Return as
             (pos, surface, candidate, weight) tuples — same shape
             the old Python inferer returned, so callers don't
             change.

        The rules + categories live in
        domains/phase_composer_language_rules.py and
        seeds/conceptual_categories.json. Both are graph data the
        substrate reads at install time; this adapter only
        constructs UnknownToken nodes and reads LexEntries — no
        Python decisions over graph state."""
        # Build a snapshot of what's already filled in the parse so
        # the slot-hint computation can pick the next unfilled role
        # left-to-right (a position-only heuristic, no graph reads).
        prior_filled: set[str] = set()
        for surf, concept in resolved:
            t = _event_tense_probe(language, surf, concept)
            if t is not None:
                prior_filled.add("event")
            elif concept in ("?WHO", "?WHAT"):
                prior_filled.add("agent")
            elif concept.lower() in _RELATION_CONCEPTS:
                continue
            else:
                # Fall through — order-of-encounter assigns to
                # leftover roles below.
                pass
        # Order-of-encounter for leftover resolved concepts.
        leftover = [
            c for s, c in resolved
            if c not in ("?WHO", "?WHAT")
            and c.lower() not in _RELATION_CONCEPTS
            and _event_tense_probe(language, s, c) is None
        ]
        if "agent" not in prior_filled and leftover:
            prior_filled.add("agent")
            leftover.pop(0)
        if leftover:
            if _has_locative_marker(text, language):
                prior_filled.add("location")
            else:
                prior_filled.add("patient")

        sentence_id = f"snt:{id(text):x}"
        # Context bag for reference-based sense selection (Lesk): the
        # sentence's OTHER content surfaces plus any already-resolved concept
        # names. Mechanical — just a bag of lowercased surfaces handed to the
        # WordNet sense scorer; no graph decisions here.
        context_words: list[str] = []
        for tk in tokens:
            w = tk.strip().lower()
            if w:
                context_words.append(w)
        for surf, concept in resolved:
            if surf:
                context_words.append(surf.strip().lower())
            if concept and not concept.startswith("?"):
                context_words.append(concept.strip().lower())

        unknown_nids: list[tuple[int, str, Any]] = []
        seen_surface: set[str] = set()
        slot_taken: set[str] = set(prior_filled)
        # surface -> (slot, concept) for tokens the WordNet dictionary
        # resolved this parse (grounded mechanically, no UnknownToken).
        self._dict_resolved: dict[str, tuple[str, str]] = {}
        for pos, surface in unknown_positions:
            if surface in seen_surface:
                continue
            seen_surface.add(surface)
            slot = _slot_hint_from_surface(pos, surface, tokens, language,
                                          slot_taken)
            if slot is None:
                continue
            slot_taken.add(slot)
            # Mechanical orthographic / morphological cues — pure surface
            # string + immediate-context computation (no graph reads),
            # the explicitly-permitted thin I/O-boundary classifier. The
            # rules consume these as token attrs; Python decides nothing.
            cues = _orthographic_cues(pos, surface, orig_tokens, tokens,
                                      language)
            # --- Dictionary (WordNet) layer -------------------------------
            # Try the dictionary BEFORE context-typing: a common noun/verb
            # resolves mechanically from WordNet to its canonical English
            # concept (cross-lingual nouns included: perro→dog). Proper
            # nouns (capitalized, no determiner — "Sasha") are NOT
            # dictionary words; SKIP the dictionary for them so they keep
            # going to context-typing / name handling. External I/O at the
            # adapter boundary — it grounds graph data the rules consume.
            is_proper = bool(cues["is_capitalized"]
                             and not cues["has_determiner"])
            if not is_proper:
                # Context = the other content surfaces (drop this one so a
                # synset's own lemma doesn't self-match in the Lesk overlap).
                ctx = [w for w in context_words if w != surface.strip().lower()]
                concept = dlex.ingest_word(self, surface, slot, language,
                                           context_words=ctx)
                if concept is not None:
                    self._dict_resolved[surface] = (slot, concept)
                    continue  # resolved — no UnknownToken needed
                # --- Wiktionary (kaikki) layer ----------------------------
                # For NON-ENGLISH content tokens, consult the cold mmap'd
                # Wiktionary slabs (cache_aside: we only reach here because
                # the hot grounded lexicon + the WordNet OMW lookup MISSED).
                # The chain is form_of→lemma → English translation →
                # WordNet-type the English word. Broader than UniMorph+OMW
                # for inflected non-English verbs (persiguió→perseguir→
                # follow). English keeps to WordNet/morphy — skip Wiktionary
                # for it so the en path is unchanged.
                if language != "en":
                    concept = wikt.ingest_wiktionary(
                        self, surface, language, slot, context_words=ctx)
                    if concept is not None:
                        self._dict_resolved[surface] = (slot, concept)
                        continue
                # --- Morphology (UniMorph) layer --------------------------
                # WordNet keys on citation forms, so an inflected non-English
                # surface (persiguió, 追いかけた) misses above. Reduce the form
                # to its lemma via the ingested UniMorph form→lemma table
                # (mechanical reference lookup — no hand paradigm, no ML), then
                # re-run the SAME WordNet lookup on that lemma. Ground both the
                # InflectionEntry (surface→lemma) and, if WordNet resolves the
                # lemma, the resulting Concept+LexEntry on this surface.
                lemma = morph.lemmatize(surface, language, slot)
                if lemma is not None and lemma != surface:
                    morph.ingest_inflection(self, surface, lemma, language)
                    concept = dlex.ingest_word(self, lemma, slot, language,
                                               context_words=ctx)
                    if concept is not None:
                        # The inflected surface denotes the same concept.
                        self._add_lex_entry(language, surface, concept,
                                            tentative=False, weight=1.0,
                                            source="unimorph+wordnet")
                        self._dict_resolved[surface] = (slot, concept)
                        continue
            try:
                u_nid = self.s.add_node("UnknownToken", {
                    "word": surface,
                    "slot": slot,
                    "language": language,
                    "position": pos,
                    "sentence_id": sentence_id,
                    "predicate": known_predicate,
                    "lemma": cues["lemma"],
                    "is_capitalized": cues["is_capitalized"],
                    "has_determiner": cues["has_determiner"],
                    "suffix_ed": cues["suffix_ed"],
                    "suffix_s": cues["suffix_s"],
                })
            except Exception:
                continue
            try:
                pclr.wire_unknown(self.s, u_nid)
            except Exception:
                pass
            unknown_nids.append((pos, surface, u_nid))

        # Run the agent. The phase-composer language rules fire,
        # emitting one LexEntry per UnknownToken (per slot) and
        # wiring it via has_lex.
        try:
            self.s.tick()
        except Exception:
            pass

        # Read back: walk has_lex outgoing edges per UnknownToken and
        # pull the inferred concept. There may be zero — the substrate
        # has no candidate for some slot — or one. Take the first.
        inferred: list[tuple[int, str, str, float]] = []
        # surface -> slot the substrate TYPED this inferred concept into
        # (read straight off the emitted LexEntry, graph data — not a
        # Python decision). Lets the frame builder honour the substrate's
        # own typing of a new event-concept whose surface morphology the
        # per-language event-probe can't recognise (e.g. a brand-new zh
        # verb has no morphological tense hook and isn't in the canonical
        # English event set).
        self._last_inferred_slots = {}
        # Dictionary-resolved tokens: ground their slot typing so the
        # frame builder can honour a new verb the morphology probe misses,
        # and surface them in the inferred log. The LexEntry is already
        # grounded by ingest_word; re-adding via the caller is idempotent.
        for surface, (slot, concept) in self._dict_resolved.items():
            self._last_inferred_slots[surface] = slot
        for pos, surface, u_nid in unknown_nids:
            lex_nids = self.s.neighbours(u_nid, "has_lex")
            chosen: str | None = None
            weight: float = 1.0
            slot_typed: str | None = None
            for lex_nid in lex_nids:
                attrs = self.s.node(lex_nid)["attrs"]
                cand = attrs.get("concept")
                if isinstance(cand, str) and cand:
                    chosen = cand
                    w = attrs.get("weight")
                    if isinstance(w, (int, float)):
                        weight = float(w)
                    sl = attrs.get("slot")
                    if isinstance(sl, str):
                        slot_typed = sl
                    break
            if chosen is None:
                continue
            if slot_typed:
                self._last_inferred_slots[surface] = slot_typed
            inferred.append((pos, surface, chosen, weight))
        # Surface dictionary resolutions in the inferred list too (source
        # is the LexEntry's source=="wordnet"; weight 1.0 = confirmed).
        for pos, surface in unknown_positions:
            if surface in self._dict_resolved:
                _slot, concept = self._dict_resolved[surface]
                inferred.append((pos, surface, concept, 1.0))
        return inferred

    # ----- grounding ------------------------------------------------------

    def _ground(self, spec: dict, text: str, language: str,
                shape_key: str, shape_dict: dict[str, Any]) -> dict[str, Any]:
        """Ground the teacher's spec into the graph. Creates Language /
        Grammar / Lexicon / Production / LexEntry / SemanticFrame nodes
        and the wiring edges. Returns the grounded frame dict."""
        # The teacher may overrule our language ID (e.g. mixed script).
        code = spec.get("language") or language
        # Ground the sentence's FUNCTION WORDS (reference + grammar derived)
        # so production can read them back even after only the teacher pass.
        self._ground_function_words_in_text(text, code)
        lang_nid = self._get_or_create_language(code)
        grammar_nid = self._get_or_create_grammar(
            code, summary=spec.get("grammar_summary", ""))
        lex_nid = self._get_or_create_lexicon(code)
        shape_nid = self._get_or_create_shape(shape_key, shape_dict)

        try:
            self.s.add_edge(grammar_nid, "has_shape", shape_nid, None)
        except Exception:
            pass
        try:
            self.s.add_edge(shape_nid, "of_language", lang_nid, None)
        except Exception:
            pass

        for rule in spec.get("productions", []):
            self._add_production(code, rule)
        for pair in spec.get("lexicon", []):
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            surface, concept = pair[0], pair[1]
            # Normalise surface for latin scripts (lowercase).
            if code in ("en", "es"):
                surface_norm = str(surface).lower()
            else:
                surface_norm = str(surface)
            self._add_lex_entry(code, surface_norm, str(concept))

        # Materialise the meaning as a SemanticFrame node.
        meaning = spec.get("meaning", {}) or {}
        frame_nid = self.s.add_node("SemanticFrame", {
            "language": code,
            "source_text": text,
            **{k: v for k, v in meaning.items() if isinstance(v, (str, int, float, bool))}
        })
        try:
            self.s.add_edge(frame_nid, "of_language", lang_nid, None)
        except Exception:
            pass
        # Wire the event concept and role concepts.
        event = meaning.get("event")
        if event:
            evt_nid = self._get_or_create_concept(event)
            try:
                self.s.add_edge(frame_nid, "frame_event", evt_nid, None)
            except Exception:
                pass
        for role in _FRAME_ROLES:
            v = meaning.get(role)
            if isinstance(v, str):
                cn = self._get_or_create_concept(v)
                try:
                    self.s.add_edge(frame_nid, "frame_role", cn, {"role": role})
                except Exception:
                    pass

        # Remember per-shape that this language has now been seen.
        self._shape_cache[shape_key] = {
            "language": code,
            "last_frame": dict(meaning),
        }
        return meaning

    def _record_observation(self, text: str, language: str,
                            frame: dict[str, Any]) -> None:
        try:
            obs_nid = self.s.add_node("LanguageObservation", {
                "text": text,
                "language": language,
                "frame_repr": repr(frame),
            })
            lang_nid = self._language_nodes.get(language)
            if lang_nid is not None:
                try:
                    self.s.add_edge(obs_nid, "observed_in", lang_nid, None)
                except Exception:
                    pass
        except Exception:
            pass

    # ----- the world's traversal -----------------------------------------

    def run(self) -> list[dict]:
        """For each task: identify (language, shape); look up grounded
        Grammar + Lexicon for the language; if absent OR the grounded
        lexicon doesn't cover enough of the surface, ask the teacher
        and ground the response. Cumulative across calls in same and
        future runs (graph is the source of truth)."""
        log: list[dict] = []
        for task in self.tasks:
            text = task["text"]
            expected = task["expected_meaning"]
            hint = task.get("language")
            calls_before = self._teacher_call_count
            asked: list[str] = []

            language, shape_key, shape_dict = self._identify(text, hint)
            # Coverage probe: do we have a grounded lexicon for this
            # language that covers most of the content words?
            covered, total = self._lexicon_coverage(text, language)
            grammar_present = language in self._grammar_nodes
            need_teacher = (not grammar_present
                            or (total > 0 and covered / total < 0.6))

            self._last_inferred = []
            if need_teacher and not self.teacher_disabled:
                gap = (f"language={language} shape={shape_key}: lexicon coverage"
                       f" {covered}/{total}, grammar_present={grammar_present}")
                asked.append(gap)
                # Both teachers accept (gap, text, language_hint); the
                # third arg is optional on the stub but informative.
                try:
                    spec = self.teacher(gap, text, language)
                except TypeError:
                    spec = self.teacher(gap, text)
                self._teacher_call_count += 1
                frame = self._ground(spec, text, language, shape_key, shape_dict)
            else:
                # Use the grounded grammar to parse.
                frame = self._parse_with_grounded(text, language, shape_dict)
                # Materialise a SemanticFrame node for inspection.
                lang_nid = self._get_or_create_language(language)
                try:
                    fnid = self.s.add_node("SemanticFrame", {
                        "language": language,
                        "source_text": text,
                        "source": "parsed",
                        **{k: v for k, v in frame.items()
                           if isinstance(v, (str, int, float, bool))}
                    })
                    self.s.add_edge(fnid, "of_language", lang_nid, None)
                except Exception:
                    pass

            self._record_observation(text, language, frame)
            matched = _frame_equal(frame, expected)
            structural = _frame_structural_match(frame, expected)
            log.append({
                "text": text,
                "language": language,
                "shape_key": shape_key,
                "expected": expected,
                "frame": frame,
                "matched": matched,
                "structural_match": structural,
                "inferred": list(self._last_inferred),
                "asked": asked,
                "teacher_calls": self._teacher_call_count - calls_before,
                "lexicon_coverage": (covered, total),
            })
        return log

    def _lexicon_coverage(self, text: str, language: str) -> tuple[int, int]:
        """Cheap coverage probe: fraction of content tokens covered
        by the grounded lexicon for `language`. For latin scripts we
        split on word chars and count word-types in our cache; for CJK
        we greedy-match. The threshold drives the cache-miss decision."""
        lex = self._lexicon_cache.get(language, {})
        if language in ("zh", "ja"):
            surfaces = sorted(lex.keys(), key=len, reverse=True)
            i = 0
            total = 0
            covered = 0
            # Estimate total content chars as non-particle, non-punct CJK.
            for ch in text:
                if ch.isspace():
                    continue
                cp = ord(ch)
                if (0x3000 <= cp <= 0x303F) or cp in (ord("。"), ord("？")):
                    continue
                total += 1
            # Now greedy-walk and count covered chars.
            while i < len(text):
                if text[i].isspace():
                    i += 1
                    continue
                matched = False
                for surf in surfaces:
                    if text.startswith(surf, i):
                        covered += len(surf)
                        i += len(surf)
                        matched = True
                        break
                if not matched:
                    i += 1
            # Coarse: cap covered at total (greedy match might count
            # particles inside a multi-char surface).
            covered = min(covered, total)
            return covered, max(total, 1)
        tokens = [t.lower() for t in re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]+", text)]
        if not tokens:
            return 0, 0
        content_tokens = [t for t in tokens
                          if t not in _LATIN_FUNCTION_WORDS.get(language, set())]
        if not content_tokens:
            return 0, 0
        covered = sum(1 for t in content_tokens if t in lex)
        return covered, len(content_tokens)

    # ----- summary --------------------------------------------------------

    @staticmethod
    def summary(log: list[dict]) -> dict:
        per_lang_calls: dict[str, int] = {}
        per_lang_total: dict[str, int] = {}
        per_lang_matched: dict[str, int] = {}
        per_lang_structural: dict[str, int] = {}
        for e in log:
            lang = e["language"]
            per_lang_total[lang] = per_lang_total.get(lang, 0) + 1
            per_lang_calls[lang] = per_lang_calls.get(lang, 0) + e["teacher_calls"]
            if e["matched"]:
                per_lang_matched[lang] = per_lang_matched.get(lang, 0) + 1
            if e.get("structural_match"):
                per_lang_structural[lang] = per_lang_structural.get(lang, 0) + 1
        return {
            "tasks": len(log),
            "matched": sum(1 for e in log if e["matched"]),
            "structural_matched": sum(1 for e in log
                                       if e.get("structural_match")),
            "teacher_calls": sum(e["teacher_calls"] for e in log),
            "asks": sum(len(e["asked"]) for e in log),
            "per_language_calls": per_lang_calls,
            "per_language_total": per_lang_total,
            "per_language_matched": per_lang_matched,
            "per_language_structural": per_lang_structural,
        }


# ---------------------------------------------------------------------------
# Static metadata + tense-probe — small per-language tables. Not English-
# specific decision logic; these are pure surface-marker probes mirrored
# across all four languages.
# ---------------------------------------------------------------------------


def _script_class(s: str) -> str:
    """Rough script-family bucket of the first non-whitespace char of
    `s`. Used by the inference layer's shape-similarity feature."""
    for ch in s:
        if ch.isspace():
            continue
        cp = ord(ch)
        if 0x0041 <= cp <= 0x024F:
            return "latin"
        if 0x3040 <= cp <= 0x309F:
            return "hira"
        if 0x30A0 <= cp <= 0x30FF:
            return "kata"
        if 0x4E00 <= cp <= 0x9FFF:
            return "han"
        return "other"
    return "other"


def _has_locative_marker(text: str, language: str) -> bool:
    """Per-language locative-marker probe with word boundaries for
    latin scripts (so bare "en" inside "Quién" doesn't fire) and
    direct substring for CJK (ideographs are their own boundary).
    All four language slots use the same shape of check."""
    if language in ("zh", "ja"):
        markers = {"zh": ("在", "上"), "ja": ("に", "で")}.get(language, ())
        return any(m in text for m in markers)
    markers = {"en": ("on", "in", "at"), "es": ("en", "sobre")}.get(language, ())
    tokens = [t.lower() for t in re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]+", text)]
    return any(m in tokens for m in markers)


# The full SemanticFrame role inventory (taught in seeds/thematic_roles.json):
# the coarse core (agent/patient/location) plus the fine-grained oblique roles
# the VerbNet-derived preposition->role mapping recovers. SemanticFrame nodes
# wire a frame_role edge per filled role.
_FRAME_ROLES = ("agent", "patient", "location", "recipient", "goal",
                "source", "instrument", "beneficiary", "topic", "comitative",
                "cause", "time", "manner", "standard")


_LANG_NAMES = {
    "en": "English",
    "es": "Spanish",
    "zh": "Mandarin Chinese",
    "ja": "Japanese",
}

_LANG_FAMILIES = {
    "en": "Indo-European/Germanic",
    "es": "Indo-European/Romance",
    "zh": "Sino-Tibetan",
    "ja": "Japonic",
}


# Per-language function words to exclude from coverage denominators.
# Concepts that surface forms can ground to but that don't fill a role
# in a semantic frame (they ARE the role, not its filler). Cross-lingual
# — same set applies whether the parser learned them from English (on,
# in), Spanish (in, on), Mandarin (on, at, top) or Japanese (top, at).
_RELATION_CONCEPTS = {"on", "in", "at", "to", "from", "above", "below", "top", "under"}


# Per-language CJK particles + aspect markers — tokenized for positional
# slot cues (が ⇒ next position fills the agent slot, を ⇒ patient) but
# excluded from the content-word inference path. These are grammatical
# function words, not concept fillers; treating them as unknowns
# pollutes the inferer's candidate scoring.
_CJK_PARTICLES = {
    "ja": {"が", "を", "に", "は", "で", "の", "へ", "と", "も", "や", "から",
            "上", "下", "中", "間"},
    "zh": {"了", "在", "上", "下", "里", "的", "得", "地", "和", "与"},
}


_LATIN_FUNCTION_WORDS = {
    "en": {"the", "a", "an", "on", "in", "at", "to", "of", "is", "are", "was", "were"},
    "es": {"el", "la", "los", "las", "un", "una", "en", "sobre", "a", "de",
            "se", "es", "son", "era", "fue"},
}


def _event_tense_probe(language: str, surface: str, concept: str) -> str | None:
    """Return a tense label if the surface form indicates the concept
    is functioning as a verb here; else None. Pure surface-marker test
    per language — no general parser, no English-bias logic; each lang
    gets the same shape of probe written from its own morphology."""
    if language == "en":
        # past tense -ed / irregular sat / broke / chased / loves.
        if surface.endswith("ed"):
            return "past"
        if surface in ("sat", "broke", "chased", "ate", "ran", "wrote",
                       "gave", "came", "bought", "cut", "made", "went",
                       "took", "told", "said", "saw"):
            return "past"
        if surface.endswith("s") and not surface.endswith("ss"):
            return "present"
        return None
    if language == "es":
        # -ó / -ió → past 3sg; -a / -e → present 3sg.
        if surface.endswith("ó") or surface.endswith("ió"):
            return "past"
        if surface in ("ama", "come", "vive", "ve"):
            return "present"
        return None
    if language == "zh":
        # Mandarin marks tense via aspect particles (了) — not on the
        # verb. The probe says "if the concept is one of our canonical
        # event concepts AND the surface is one of the verb-surface
        # entries we grounded, it's an event". Tense omitted.
        EVENTS = {"sit", "love", "break", "chase"}
        if concept in EVENTS:
            return ""  # event without tense
        return None
    if language == "ja":
        # Japanese: -た (ta) past, -ている (te-iru) progressive/present.
        if surface.endswith("た"):
            return "past"
        if surface.endswith("ている") or surface.endswith("います"):
            return "present"
        EVENTS = {"sit", "love", "break", "chase"}
        if concept in EVENTS:
            return ""
        return None
    return None


# ---------------------------------------------------------------------------
# Frame comparison — robust to extra keys the teacher may include but
# the expected_meaning omits (e.g. teacher adds 'speech_act': 'assertion'
# to a plain sentence). We only require the EXPECTED keys to match.
# ---------------------------------------------------------------------------


# Cross-language proper-noun + synonym equivalence used to live as a
# Python `_CONCEPT_ALIASES` dict — it's been stripped per CLAUDE.md.
# Frame equality is now pure case-insensitive string match. The teacher
# is responsible for grounding to canonical concept names so cross-
# language frames compare cleanly (teacher_stub already maps "maría" →
# "Mary"). When a real teacher grounds to a non-canonical form, the
# strict-match score takes the hit; the structural-match check below
# only requires animacy class agreement and so is unaffected.


def _concepts_equiv(a: str, b: str) -> bool:
    return a.lower() == b.lower()


def _frame_equal(produced: dict, expected: dict) -> bool:
    """The produced frame matches the expected one IFF every expected
    key is present in produced with an equivalent value. Mandarin lacks
    a 'tense' field in the expected dicts; the produced frame's tense
    is allowed to be absent or empty for zh. Proper-noun and synonym
    aliases (María≡Mary, alfombra≡mat) count as equal."""
    if not isinstance(produced, dict) or not isinstance(expected, dict):
        return False
    for k, v in expected.items():
        pv = produced.get(k)
        if pv is None:
            return False
        if isinstance(v, str) and isinstance(pv, str):
            if not _concepts_equiv(v, pv):
                return False
        elif pv != v:
            return False
    return True


# Coarse animate / inanimate buckets used by the structural-match check.
# This is NOT a feature the substrate uses for inference (the inference
# layer's slot/role plausibility is keyed off OBJECT/ANIMATE concept
# lists privately). It's the OUTCOME-side criterion the test runs to
# distinguish strict word-match from "got the SHAPE right" when the
# substrate's context inference necessarily substitutes a known concept
# for an unseen one. Held-out's `dog` is unseen, but if the substrate
# substitutes another animate concept, the role-shape is preserved.
_ANIMATE_TAG = {"cat", "dog", "mary", "john", "person", "child",
                "?who", "?what", "bird", "fish", "horse", "cow"}
_INANIMATE_TAG = {"mat", "vase", "ball", "rug", "carpet", "book",
                  "table", "chair", "rock", "tree", "alfombra"}


def _frame_structural_match(produced: dict, expected: dict) -> bool:
    """Loose check: every EXPECTED role is filled in PRODUCED, and the
    filler has the correct ANIMATE / INANIMATE class. Tense and exact
    word match are not required. Designed to credit context-inferred
    parses where the substrate substituted a known concept (e.g. cat)
    for an unseen one (e.g. dog) but preserved the slot SHAPE."""
    if not isinstance(produced, dict) or not isinstance(expected, dict):
        return False
    # Each expected role must be present in produced.
    for role in ("event", "agent", "patient", "location"):
        if role not in expected:
            continue
        pv = produced.get(role)
        if not pv:
            return False
        exp = expected[role]
        if role in ("agent",):
            if not _same_animacy(exp, pv, expect_animate=True):
                return False
        elif role in ("patient", "location"):
            if not _same_animacy(exp, pv, expect_animate=False):
                return False
        # event: just need any concept filling it (the surface morphology
        # already determined the produced concept was "event-like").
    # Speech act + question agents must match if present.
    if expected.get("speech_act") and produced.get("speech_act") != expected["speech_act"]:
        return False
    return True


def _same_animacy(expected: str, produced: str, expect_animate: bool) -> bool:
    """Returns True iff `produced` falls in the same animacy class as
    the EXPECTED filler. Unknown concepts default to matching (we want
    to credit the substrate when its candidate has the right SHAPE; we
    don't penalise for concepts the test bank didn't classify)."""
    e_low, p_low = expected.lower(), produced.lower()
    if _concepts_equiv(expected, produced):
        return True
    p_animate = p_low in _ANIMATE_TAG
    p_inanimate = p_low in _INANIMATE_TAG
    if expect_animate:
        if p_animate:
            return True
        if p_inanimate:
            return False
    else:
        if p_inanimate:
            return True
        if p_animate:
            return False
    # Concept not in either bucket — credit by default; structural-match
    # is the LOOSE criterion.
    return True
