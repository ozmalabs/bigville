"""LanguageProduction — goal-based utterance PRODUCTION as the INVERSE of
the comprehension stack in ``language_world.py``.

This is step 3 (research -> teach -> BUILD) of the ``language_production``
microtheory (seeds/lang_production.json). Production turns a communicative
GOAL into an utterance by running the SAME grounded grammar/lexicon the
comprehension stack uses, in reverse, and self-monitors by parsing its own
output back through comprehension ("say it to yourself" — Levelt's
self_monitoring_loop).

The pipeline mirrors the taught stage names:

  conceptual_preparation        goal (frame + intent) -> preverbal_message
                                (frame + mood + queried-slot)
  grammatical_encoding          preverbal_message -> surface_structure
                                (ordered lemma slots, via the grounded
                                Grammar productions read in reverse)
  morphophonological_encoding   surface_structure -> phonological_word seq
                                (lexicon-in-reverse: concept -> surface word
                                for that language; surfaces are already the
                                inflected forms the comprehension teacher
                                grounded)
  articulation                  phonological_word seq -> overt_speech
                                (join + apply the mood's surface marking)

  self_monitoring_loop          parse overt_speech back with the SAME
                                LanguageWorld comprehension parser, recover a
                                frame, compare to the goal preverbal_message;
                                accept on match, flag + one repair attempt on
                                mismatch.

ARCHITECTURE (CLAUDE.md). This is a WORLD ADAPTER: it only does mechanical
I/O — reading grounded graph data (LexEntry surface<->concept, Production
rule strings, Grammar/Lexicon nodes) back out, ordering it, and emitting a
string. It makes NO new agent decisions: the grammar/lexicon/morphology it
uses were all grounded by the comprehension stack; production reads them in
reverse. The one I/O-boundary mapping (intent -> mood) is the taught
``mood_assignment`` table verbatim from the seed, not an English rule.

HONEST REALIZABILITY (stated plainly, see the module-level notes and the
test report):
  * FUNCTION WORDS (the / on / a / が / を / に) ARE NOW grounded by
    comprehension as FunctionWord nodes (identity + function from Wiktionary
    POS, role from the grounded grammar — see function_word_reference.py).
    Production reads those nodes back in reverse and INSERTS them around the
    content words: a definite determiner before a common noun, a location
    preposition before a location noun (en/es), the case particle after a
    noun (ja/zh). So overt_speech moves from lemma-level ("cat sat mat") to
    "The cat sat on the mat." / "El gato sentó en el alfombra." / "猫がマット
    に座った。". Only GROUNDED function words are emitted; what isn't grounded
    is omitted and SAID SO. COARSE preposition→location (the spatial subset);
    es determiner gender agreement (la vs el) and the reflexive "se" are not
    yet modelled — minor fluency gaps that don't break the round-trip.
  * INFLECTION is realized by the lexicon-in-reverse, NOT a morphology
    generator: the grounded LexEntry surface for ``sit`` IS already ``sat``
    (the teacher grounded the inflected surface against the concept), so
    tense falls out for free for grounded events. The morphology_reference
    slab only maps form->lemma (one direction); a lemma->form GENERATOR
    would need a reverse index the slab doesn't build, so we do NOT use it
    and rely on the grounded inflected surface. For an event with no
    grounded inflected surface, only the bare lemma is realizable.
  * WORD ORDER comes from the grounded Production rule strings parsed in
    reverse (SVO for en/es/zh, SOV for ja from ``NP-ga NP-o ... V``). When
    the rules can't be cleanly inverted we fall back to the per-language
    canonical order recorded here and SAY SO in the stage trace.
  * The real demonstration is the SELF-MONITOR ROUND-TRIP: produce ->
    parse-back -> the recovered frame matches the goal. Not human-fluent
    English.
"""
from __future__ import annotations

import json
from typing import Any, Optional

# The comprehension stack we invert + reuse for self-monitoring.
from domains import language_world as lw
from domains import preposition_roles as preprole


# ---------------------------------------------------------------------------
# mood_assignment — the taught goal->sentence-type hook (lang_production.json,
# concept "mood_assignment"). Verbatim from the seed: inform->declarative,
# ask->interrogative, request->imperative. This is the I/O-boundary mapping
# CLAUDE.md permits (a fixed taught table, not an English parsing rule).
# ---------------------------------------------------------------------------

_INTENT_TO_MOOD = {
    "inform": "declarative",
    "ask": "interrogative",
    "request": "imperative",
}

# Surface marking per mood (articulation stage). Latin scripts use ASCII
# terminators; CJK uses fullwidth so the comprehension parser's terminator
# probe (which accepts both ? and ？) recovers the speech act. The marks are
# the ONLY orthography production adds beyond grounded surfaces — they're the
# mood's externalization, the inverse of comprehension's terminator probe.
_MOOD_TERMINATOR = {
    "declarative": {"latin": ".", "cjk": "。"},
    "interrogative": {"latin": "?", "cjk": "？"},
    "imperative": {"latin": "!", "cjk": "！"},
}

# Per-language canonical constituent order — the FALLBACK when the grounded
# Production rules can't be cleanly inverted. These mirror the order the
# comprehension parser itself assumes (its SVO default + ja particle/final-
# verb handling), so production and comprehension agree. "role tokens":
# agent=subject, event=verb, patient=object, location=oblique.
# The fine-grained oblique roles (PP arguments) follow the object in SVO and
# precede the verb in SOV, after location. recipient/instrument/source/
# beneficiary/topic each surface as a PP (en/es) or particle-marked NP (ja).
_OBLIQUE_ROLES = ["recipient", "goal", "instrument", "source",
                  "beneficiary", "topic", "comitative"]

_CANONICAL_ORDER = {
    # SVO: subject verb object, then the oblique PPs (location + fine roles).
    "en": ["agent", "event", "patient", "location", *_OBLIQUE_ROLES],
    "es": ["agent", "event", "patient", "location", *_OBLIQUE_ROLES],
    "zh": ["agent", "event", "patient", "location", *_OBLIQUE_ROLES],
    # SOV: subject, object, obliques, verb-final.
    "ja": ["agent", "patient", "location", *_OBLIQUE_ROLES, "event"],
}

# Languages whose grounded surfaces use no inter-word space (CJK).
_NO_SPACE = {"zh", "ja"}


# VOICE-EXPANSION feature selection (all no-ops without a grounded
# `voice_feature`; see `_concept_surface_by_feature`).
def _desired_feature(role: str, tense: Optional[str],
                     inflect: dict[str, str]) -> Optional[str]:
    """The morphological feature production should request for `role`'s
    content word: an explicit per-role `inflect` request wins; otherwise the
    event role inherits `past` from a past-tense goal (so an ordinary
    past-tense goal selects the grounded irregular past with no extra goal
    field). None means "no feature request" -- the base map is used."""
    explicit = inflect.get(role)
    if explicit:
        return explicit
    if role == "event" and tense == "past":
        return "past"
    return None


def _feature_surface(feat_map: dict[str, dict[str, str]], concept: str,
                     desired: Optional[str]) -> Optional[str]:
    """The grounded surface for (concept, desired feature), or None. A `past`
    request also accepts a `past_participle` surface (strong verbs share the
    form: brought/brought, sung is the ptcp of sing but sang is the past --
    the past tag is tried first, so sang wins when both are grounded)."""
    if not desired:
        return None
    forms = feat_map.get(concept)
    if not forms:
        return None
    surface = forms.get(desired)
    if surface is None and desired == "past":
        surface = forms.get("past_participle")
    return surface


# ---------------------------------------------------------------------------
# Reverse views over the grounded graph data. Pure mechanical reads of the
# LexEntry / Production / Lexicon / Grammar nodes the comprehension stack
# grounded — no decisions, no new agent state.
# ---------------------------------------------------------------------------


def _concept_to_surface_map(world: "lw.LanguageWorld",
                            language: str) -> dict[str, str]:
    """Build the concept -> surface reverse lexicon for ``language`` by
    walking the grounded LexEntry nodes (the INVERSE of comprehension's
    surface -> concept lookup). Prefers a confirmed entry over a tentative
    one when a concept has several surfaces; otherwise first-seen wins.

    Reads the substrate (source of truth), not the world's cache, so it
    sees every grounded entry including ones added by inference."""
    confirmed: dict[str, str] = {}
    tentative: dict[str, str] = {}
    for eid in world.s.nodes("LexEntry"):
        a = world.s.node(eid)["attrs"]
        if a.get("language") != language:
            continue
        concept = a.get("concept")
        surface = a.get("surface")
        if not concept or not surface:
            continue
        bucket = (confirmed if a.get("status") != "tentative" else tentative)
        bucket.setdefault(concept, surface)
    # Confirmed wins; fall back to tentative.
    out = dict(tentative)
    out.update(confirmed)
    return out


def _concept_surface_by_feature(world: "lw.LanguageWorld",
                                language: str) -> dict[str, dict[str, str]]:
    """concept -> {voice_feature: surface} over the grounded LexEntry nodes
    that carry a `voice_feature` tag (past / past_participle / plural /
    comparative / superlative -- grounded by a voice-curriculum morphology
    lesson from the UniMorph feature column). The feature-partitioned twin of
    `_concept_to_surface_map`: it lets production emit the inflected surface
    the goal's requested feature names ("went" for concept 'go' + feature
    'past'), instead of the tense-blind first-grounded surface. EMPTY when no
    entry carries a feature tag (every pre-voice-curriculum world), so
    production is byte-identical without it. First-seen wins per (concept,
    feature) -- the same stable-order rule the base map uses."""
    out: dict[str, dict[str, str]] = {}
    for eid in world.s.nodes("LexEntry"):
        a = world.s.node(eid)["attrs"]
        if a.get("language") != language:
            continue
        feat = a.get("voice_feature")
        concept = a.get("concept")
        surface = a.get("surface")
        if not feat or not concept or not surface:
            continue
        out.setdefault(concept, {}).setdefault(feat, surface)
    return out


def _grounded_function_words(world: "lw.LanguageWorld",
                             language: str) -> list[dict[str, Any]]:
    """All grounded FunctionWord nodes for ``language`` as plain attr dicts
    (the same data comprehension grounded — read back in reverse for
    production)."""
    out: list[dict[str, Any]] = []
    for fid in world.s.nodes("FunctionWord"):
        a = world.s.node(fid)["attrs"]
        if a.get("language") == language:
            out.append(dict(a))
    return out


def _pick_function_word(fws: list[dict[str, Any]], *, function: str = None,
                        role: str = None,
                        definiteness: str = None) -> dict[str, Any] | None:
    """Pick a grounded FunctionWord matching the given function / role /
    definiteness filters (first match; grounding order is stable). None if
    none grounded — production then simply omits that function word and SAYS
    SO (honest: only grounded function words are emitted)."""
    for a in fws:
        if function is not None and a.get("function") != function:
            continue
        if role is not None and a.get("grammatical_role") != role:
            continue
        if definiteness is not None and a.get("definiteness") != definiteness:
            continue
        return a
    return None


def _fw_token(fw: dict[str, Any], kind: str) -> dict[str, Any]:
    """A phonological-word token for a grounded function word (so it joins
    into the surface string like any other word). ``function_word`` flags it
    for the trace; it carries no frame role of its own."""
    return {
        "role": f"fn:{kind}",
        "concept": fw.get("function", kind),
        "surface": fw.get("surface", ""),
        "realized": True,
        "function_word": True,
    }


def _grammar_productions(world: "lw.LanguageWorld",
                         language: str) -> list[str]:
    """The grounded Production rule strings for ``language`` (read straight
    off the Production nodes — the same data comprehension grounded)."""
    rules: list[str] = []
    for pid in world.s.nodes("Production"):
        a = world.s.node(pid)["attrs"]
        if a.get("language") == language:
            rule = a.get("rule")
            if rule:
                rules.append(str(rule))
    return rules


def _order_from_productions(language: str,
                            rules: list[str]) -> tuple[list[str], str]:
    """Derive constituent order (role -> position) from the grounded
    Production rule strings, run in REVERSE: the grammar tells us how a
    clause expands into constituents, and we read that expansion left-to-
    right to order the roles for generation.

    Returns (ordered_roles, provenance) where provenance is "grammar" when
    the rules drove the order or "canonical_fallback:<why>" when we couldn't
    cleanly invert and fell back to _CANONICAL_ORDER.

    The mapping from grammar symbols to frame roles:
        subject NP (the NP in ``S -> NP VP``)      -> agent
        V (verb head of VP)                         -> event
        object NP (the NP in ``VP -> V NP``)        -> patient
        PP / oblique NP                             -> location
    For ja the order is read from the explicit positional rule
    ``S -> NP-ga (NP-o)? (NP-ni)? V`` (ga=agent, o=patient, ni=location,
    final V=event)."""
    canon = _CANONICAL_ORDER.get(language, ["agent", "event", "patient",
                                            "location"])
    if not rules:
        return canon, "canonical_fallback:no-grounded-productions"

    # Japanese: a single positional rule encodes the whole order. Read the
    # particle order directly (ga -> o -> ni -> V).
    if language == "ja":
        for r in rules:
            comp = r.replace(" ", "")
            if "NP-ga" in comp and r.strip().endswith("V"):
                order: list[str] = []
                # Walk the rule body in textual order, mapping particle ->
                # role and a trailing V -> event.
                body = r.split("->", 1)[1] if "->" in r else r
                # Tokenize on whitespace; strip optional-markers.
                for tok in body.split():
                    t = tok.strip("()?")
                    if t.startswith("NP-ga"):
                        order.append("agent")
                    elif t.startswith("NP-o"):
                        order.append("patient")
                    elif t.startswith("NP-ni"):
                        order.append("location")
                    elif t == "V":
                        order.append("event")
                if "event" in order and "agent" in order:
                    return order, "grammar"
        return canon, "canonical_fallback:ja-positional-rule-not-found"

    # SVO-family (en/es/zh): infer from S -> ... and VP -> ... rules whether
    # the subject precedes the verb and whether the object follows it.
    s_rule = next((r for r in rules if r.split("->", 1)[0].strip() == "S"),
                  None)
    vp_rules = [r for r in rules if r.split("->", 1)[0].strip() == "VP"]
    if s_rule is None or not vp_rules:
        return canon, "canonical_fallback:no-S-or-VP-rule"

    s_body = s_rule.split("->", 1)[1].split()
    # Subject-before-verb iff NP precedes VP in the S expansion.
    try:
        subj_before_verb = s_body.index("NP") < s_body.index("VP")
    except ValueError:
        return canon, "canonical_fallback:S-rule-not-NP-VP"

    # Object after verb iff any VP rule expands V before NP (VP -> V NP).
    obj_after_verb = False
    loc_after_verb = False
    for r in vp_rules:
        body = r.split("->", 1)[1].split()
        if "V" in body:
            vi = body.index("V")
            if "NP" in body and body.index("NP") > vi:
                obj_after_verb = True
            if ("PP" in body and body.index("PP") > vi) or "PP" in body:
                loc_after_verb = True

    # Compose the role order from the inferred relations. Default SVO shape.
    order = []
    if subj_before_verb:
        order = ["agent", "event"]
    else:
        order = ["event", "agent"]
    if obj_after_verb:
        order.append("patient")
    else:
        order.insert(0, "patient")
    if loc_after_verb:
        order.append("location")
    else:
        order.append("location")
    # De-dup preserving order.
    seen: set[str] = set()
    order = [r for r in order if not (r in seen or seen.add(r))]
    # Ensure all four roles present (append any missing in canonical order).
    for r in canon:
        if r not in order:
            order.append(r)
    return order, "grammar"


# ---------------------------------------------------------------------------
# The production pipeline. Each method is a named stage; the return values
# are the named representations from lang_production.json.
# ---------------------------------------------------------------------------


class LanguageProduction:
    """Produce an utterance from a goal, inverting the grounded
    comprehension stack and self-monitoring via comprehension.

    Construct with an ALREADY-TRAINED LanguageWorld (run the comprehension
    bank first, exactly as language_test does, so the grammar/lexicon are
    grounded). Production reads that grounding back out in reverse.
    """

    def __init__(self, world: "lw.LanguageWorld"):
        self.world = world
        self.s = world.s

    # ----- stage 1: conceptual_preparation --------------------------------

    def conceptual_preparation(self, goal: dict[str, Any]) -> dict[str, Any]:
        """goal = a target SemanticFrame {event, agent, patient, location,
        tense} + an ``intent`` (inform / ask / request). Maps intent -> mood
        via the taught mood_assignment table and identifies which slot is
        QUERIED (the ?WHO / ?WHAT slot, for questions).

        Output: a preverbal_message = {frame, mood, queried_slot}. NOT yet
        words — the input to grammatical_encoding."""
        intent = goal.get("intent", "inform")
        mood = _INTENT_TO_MOOD.get(intent, "declarative")
        frame = {k: v for k, v in goal.items() if k != "intent"}
        # Which slot is queried? The role whose filler is a wh-placeholder.
        queried_slot: Optional[str] = None
        for role in ("agent", "patient", "location"):
            v = frame.get(role)
            if isinstance(v, str) and v in ("?WHO", "?WHAT"):
                queried_slot = role
                break
        return {
            "frame": frame,
            "mood": mood,
            "queried_slot": queried_slot,
        }

    # ----- stage 2: grammatical_encoding ----------------------------------

    def grammatical_encoding(self, language: str,
                             preverbal: dict[str, Any]) -> dict[str, Any]:
        """Order the frame's filled roles into the language's word order by
        reading the grounded Grammar productions IN REVERSE (the inverse of
        comprehension's parse). Output a surface_structure = ordered list of
        (role, concept) lemma slots, plus the order provenance."""
        frame = preverbal["frame"]
        rules = _grammar_productions(self.world, language)
        order, provenance = _order_from_productions(language, rules)
        # Lay the filled roles out in the grammar-derived order. A queried
        # slot (?WHO) is realized in position too; for en/es interrogatives
        # the wh-word fronts (English/Spanish wh-fronting) — handled here as
        # a positional adjustment the grammar's question form implies.
        slots: list[tuple[str, str]] = []
        for role in order:
            v = frame.get(role)
            if isinstance(v, str) and v:
                slots.append((role, v))
        # Wh-fronting for en/es interrogatives: move the queried slot to the
        # front (the comprehension parser recovers the wh-word as agent
        # regardless of position, so this is purely about producing the
        # canonical question shape; documented as a surface convention, not
        # grammar-derived since the grounded productions don't record it).
        qs = preverbal.get("queried_slot")
        wh_fronted = False
        if (preverbal["mood"] == "interrogative" and qs is not None
                and language in ("en", "es")):
            for i, (role, _c) in enumerate(slots):
                if role == qs and i != 0:
                    slots.insert(0, slots.pop(i))
                    wh_fronted = True
                    break
        return {
            "ordered_slots": slots,
            "order": order,
            "order_provenance": provenance,
            "wh_fronted": wh_fronted,
            # optional {role -> adjective-concept} modifiers, realized before the role's noun (see
            # morphophonological_encoding). Empty by default, so production is unchanged without them.
            "adjectives": frame.get("adjectives") or {},
            # VOICE-EXPANSION morphological feature requests (all optional, all
            # empty by default so production is byte-identical without them):
            #   tense           -- the clause tense (past selects the grounded
            #                      irregular past for the event role);
            #   inflect         -- {role -> feature} for a role's CONTENT word
            #                      (e.g. {"agent": "plural"} -> "children");
            #   adjective_features -- {role -> feature} for a role's ADJECTIVE
            #                      (e.g. {"agent": "comparative"} -> "better").
            "tense": frame.get("tense"),
            "inflect": frame.get("inflect") or {},
            "adjective_features": frame.get("adjective_features") or {},
        }

    # ----- stage 3: morphophonological_encoding ---------------------------

    def morphophonological_encoding(self, language: str,
                                    surface_structure: dict[str, Any]
                                    ) -> dict[str, Any]:
        """Realize each lemma slot -> a surface word via the lexicon IN
        REVERSE (concept -> grounded surface for this language). The grounded
        surface is already the inflected form the comprehension teacher
        grounded against the concept (``sit`` -> ``sat``), so inflection
        falls out without a morphology generator.

        Output: phonological_word sequence = list of
        {role, concept, surface, realized} dicts. ``realized`` is False for a
        concept with no grounded surface (an unrealizable slot) — reported
        honestly rather than faked."""
        rev = _concept_to_surface_map(self.world, language)
        feat_map = _concept_surface_by_feature(self.world, language)
        fws = _grounded_function_words(self.world, language)
        adjectives = surface_structure.get("adjectives") or {}
        inflect = surface_structure.get("inflect") or {}
        adj_features = surface_structure.get("adjective_features") or {}
        tense = surface_structure.get("tense")
        words: list[dict[str, Any]] = []
        for role, concept in surface_structure["ordered_slots"]:
            # Wh-placeholders realize to their grounded interrogative word
            # (?WHO -> "who"/"quién"/"谁"/"誰") — also a LexEntry the teacher
            # grounded, so the same reverse lookup serves them.
            #
            # VOICE-EXPANSION: pick the requested morphological feature's
            # surface FIRST (the grounded irregular), falling back to the
            # tense-blind base map. A `past` request also accepts a
            # `past_participle`-tagged surface (many strong verbs share it:
            # brought/brought). `feat_map` is empty without a voice-curriculum
            # morphology grounding, so this whole branch is a no-op then.
            desired = _desired_feature(role, tense, inflect)
            surface = _feature_surface(feat_map, concept, desired)
            if surface is None:
                surface = rev.get(concept)
            content = {
                "role": role,
                "concept": concept,
                "surface": surface if surface is not None else concept,
                "realized": surface is not None,
            }
            is_wh = isinstance(concept, str) and concept in ("?WHO", "?WHAT")
            is_proper = isinstance(concept, str) and concept[:1].isupper()
            is_noun_role = (role in ("agent", "patient", "location")
                            or role in preprole.FINE_ROLES)
            # Function words read back from the grounded FunctionWord nodes.
            for fw in self._function_words_for_slot(
                    fws, role, language, is_wh, is_proper, is_noun_role):
                words.append(fw)
            # ADJECTIVE (e.g. a perceived colour) for this role's noun, realized after the determiner and
            # before the noun ("the blue thing"). The adjective surface is a grounded LexEntry, resolved by the
            # same reverse concept->surface map; an ungrounded adjective is reported unrealized, not faked.
            adj = adjectives.get(role) if is_noun_role else None
            if adj:
                # VOICE-EXPANSION: a comparative/superlative request on this
                # role's adjective ("better" for concept 'good' + feature
                # 'comparative') picks the grounded degree form first, else
                # the base surface. No-op without a grounded degree form.
                adj_surface = _feature_surface(feat_map, adj, adj_features.get(role))
                if adj_surface is None:
                    adj_surface = rev.get(adj)
                words.append({"role": "modifier", "concept": adj,
                              "surface": adj_surface if adj_surface is not None else adj,
                              "realized": adj_surface is not None})
            words.append(content)
            for fw in self._particles_after_slot(
                    fws, role, language, is_wh, is_noun_role):
                words.append(fw)
        return {"words": words}

    def _function_words_for_slot(self, fws: list[dict[str, Any]], role: str,
                                 language: str, is_wh: bool, is_proper: bool,
                                 is_noun_role: bool) -> list[dict[str, Any]]:
        """Function words emitted BEFORE a content word (en/es). For a
        PP-marked role — location OR a fine oblique role (recipient ->"to",
        instrument ->"with", source ->"from", beneficiary ->"for", topic
        ->"about") — emit the role's preposition, then a definite determiner
        for a common noun. The preposition comes from a grounded FunctionWord
        whose grammatical_role matches; if none is grounded for that role we
        fall back to the VerbNet-derived role_preposition (so production can
        emit the marker even before that exact preposition was seen in
        comprehension). Reads grounded data first; the reverse table is the
        documented fallback."""
        out: list[dict[str, Any]] = []
        if is_wh or not is_noun_role:
            return out
        # PP preposition (precedes) for location + fine oblique roles. ja/zh
        # mark these with a POST-noun particle instead (handled in
        # _particles_after_slot), so only emit a preposition for en/es.
        pp_role = (role == "location") or (role in preprole.FINE_ROLES)
        if pp_role and language in ("en", "es"):
            prep = _pick_function_word(fws, function="preposition", role=role)
            if prep is not None and prep.get("attaches") == "precedes":
                out.append(_fw_token(prep, "preposition"))
            else:
                # Fallback: the VerbNet-derived reverse table (role -> prep).
                surface = preprole.role_preposition(role, language)
                if surface:
                    out.append(_fw_token(
                        {"surface": surface, "function": "preposition"},
                        "preposition"))
        # Definite determiner for a COMMON noun (proper nouns take none).
        if not is_proper:
            det = _pick_function_word(fws, function="determiner",
                                      definiteness="definite")
            if det is not None:
                out.append(_fw_token(det, "determiner"))
        return out

    def _particles_after_slot(self, fws: list[dict[str, Any]], role: str,
                              language: str, is_wh: bool,
                              is_noun_role: bool) -> list[dict[str, Any]]:
        """Particles emitted AFTER a content noun (ja/zh: the case particle
        for the role — が agent, を patient, に location). Reads the grounded
        FunctionWord whose grammatical_role == role and attaches == follows."""
        out: list[dict[str, Any]] = []
        if not is_noun_role or language not in ("ja", "zh"):
            return out
        part = _pick_function_word(fws, function="particle", role=role)
        if part is not None and part.get("attaches") == "follows":
            out.append(_fw_token(part, "particle"))
        return out


    # ----- stage 4: articulation ------------------------------------------

    def articulation(self, language: str, mood: str,
                     phonological: dict[str, Any]) -> dict[str, Any]:
        """Join the phonological words into the surface string and apply the
        mood's surface marking (declarative -> '.'; interrogative -> '?';
        imperative -> '!'; CJK fullwidth equivalents). Output overt_speech
        (the string) + the joined token list."""
        # PROPER-NOUN capitalisation: the agent mirrors two operations it
        # already holds — the is_proper signal (concept[:1].isupper(), as in
        # morphophonological_encoding) and its own capitalisation op — applying
        # the latter to every proper-noun surface (Mary / John / Jabberwock).
        # Composed from held ops; authored by the self-modification faculty.
        tokens = []
        for w in phonological["words"]:
            s = w.get("surface", "")
            c = w.get("concept")
            if (language not in _NO_SPACE and isinstance(c, str)
                    and c[:1].isupper() and not c.startswith("?") and s):
                # Proper-noun capitalisation. A MULTI-WORD proper surface (a named
                # entity re-exposed as one lexical item, "justice department")
                # capitalises EACH word ("Justice Department") — the same op
                # applied per whitespace word. A single-word surface has one part,
                # so this is byte-identical to the prior first-char upcase (no
                # regression for Mary / John / Jabberwock). Orthography only; the
                # comprehension parser lowercases on the way in, so the round-trip
                # is unaffected.
                s = " ".join((p[:1].upper() + p[1:]) if p else p
                             for p in s.split(" "))
            tokens.append(s)
        # CJK uses no inter-word space; latin joins with a space. For latin,
        # the first word is capitalized (orthographic convention; the
        # comprehension parser lowercases on the way in, so this does not
        # affect the round-trip).
        sep = "" if language in _NO_SPACE else " "
        if language not in _NO_SPACE and tokens:
            tokens = [tokens[0][:1].upper() + tokens[0][1:]] + tokens[1:]
        body = sep.join(tokens)
        script = "cjk" if language in _NO_SPACE else "latin"
        mark = _MOOD_TERMINATOR.get(mood, {}).get(script, ".")
        overt = body + mark
        return {"overt_speech": overt, "tokens": tokens}

    # ----- self_monitoring_loop -------------------------------------------

    def self_monitor(self, language: str, overt_speech: str,
                     preverbal: dict[str, Any]) -> dict[str, Any]:
        """"Say it to yourself": parse the produced overt_speech back through
        the EXISTING comprehension parser, recover a frame, and compare it to
        the goal preverbal_message's frame. Returns
        {recovered_frame, match, missing, mismatched} — the inverse of
        production closing on itself.

        Uses the comprehension world's own _identify + _parse_with_grounded
        (the same path language_test uses for held-out parsing), so this is
        genuinely the comprehension system, not a private re-implementation."""
        recovered = self._comprehend(language, overt_speech)
        goal_frame = preverbal["frame"]
        match, missing, mismatched = _compare_frames(goal_frame, recovered,
                                                     preverbal["mood"])
        return {
            "recovered_frame": recovered,
            "match": match,
            "missing": missing,
            "mismatched": mismatched,
        }

    def _comprehend(self, language: str, text: str) -> dict[str, Any]:
        """Run the comprehension parser on ``text`` for ``language`` — the
        same grounded-grammar parse comprehension uses for held-out
        sentences. Teacher stays out of it (we parse from grounded knowledge,
        the point of the round-trip)."""
        # _identify computes the TextShape (terminator, etc.); _parse_with
        # _grounded walks the grounded lexicon + cues to a frame.
        _lang, _shape_key, shape = self.world._identify(text, language)
        return self.world._parse_with_grounded(text, language, shape)

    # ----- the whole pipeline ---------------------------------------------

    def produce(self, language: str, goal: dict[str, Any]) -> dict[str, Any]:
        """Run the full pipeline goal -> overt_speech with self-monitoring,
        returning every stage's output for inspection. On a self-monitor
        mismatch, attempt ONE repair (re-realize a mismatched slot via an
        alternative grounded surface) and re-monitor."""
        preverbal = self.conceptual_preparation(goal)
        surface_structure = self.grammatical_encoding(language, preverbal)
        phonological = self.morphophonological_encoding(
            language, surface_structure)
        articulated = self.articulation(language, preverbal["mood"],
                                        phonological)
        monitor = self.self_monitor(language, articulated["overt_speech"],
                                    preverbal)

        repair: Optional[dict[str, Any]] = None
        if not monitor["match"]:
            repair = self._repair_once(language, preverbal, surface_structure,
                                       phonological, monitor)

        return {
            "language": language,
            "goal": goal,
            "preverbal_message": preverbal,
            "surface_structure": surface_structure,
            "phonological_word": phonological,
            "overt_speech": articulated["overt_speech"],
            "tokens": articulated["tokens"],
            "self_monitor": monitor,
            "repair": repair,
            "accepted": monitor["match"] or bool(repair and repair["match"]),
        }

    def _repair_once(self, language: str, preverbal: dict[str, Any],
                     surface_structure: dict[str, Any],
                     phonological: dict[str, Any],
                     monitor: dict[str, Any]) -> dict[str, Any]:
        """One cheap repair attempt: for each mismatched/missing slot, try an
        ALTERNATIVE grounded surface for that concept (a different LexEntry),
        re-articulate, and re-monitor. Reports what it tried and whether the
        round-trip then matched. No new agent decisions — just a second pass
        over the grounded lexicon's alternatives."""
        # Gather alternative surfaces per concept (all grounded LexEntries,
        # not just the first-picked one).
        alts: dict[str, list[str]] = {}
        for eid in self.s.nodes("LexEntry"):
            a = self.s.node(eid)["attrs"]
            if a.get("language") != language:
                continue
            c, sfc = a.get("concept"), a.get("surface")
            if c and sfc:
                alts.setdefault(c, [])
                if sfc not in alts[c]:
                    alts[c].append(sfc)
        # Rebuild words, swapping a mismatched slot's surface for an alt.
        bad_roles = set(monitor["missing"]) | {m[0] for m in monitor["mismatched"]}
        new_words = []
        tried: list[str] = []
        for w in phonological["words"]:
            w2 = dict(w)
            if w["role"] in bad_roles:
                candidates = [x for x in alts.get(w["concept"], [])
                              if x != w["surface"]]
                if candidates:
                    w2["surface"] = candidates[0]
                    w2["realized"] = True
                    tried.append(f"{w['role']}:{w['surface']}->{candidates[0]}")
            new_words.append(w2)
        articulated = self.articulation(language, preverbal["mood"],
                                        {"words": new_words})
        monitor2 = self.self_monitor(language, articulated["overt_speech"],
                                     preverbal)
        return {
            "tried": tried,
            "overt_speech": articulated["overt_speech"],
            "recovered_frame": monitor2["recovered_frame"],
            "match": monitor2["match"],
            "missing": monitor2["missing"],
            "mismatched": monitor2["mismatched"],
        }


# ---------------------------------------------------------------------------
# Frame comparison for the self-monitor. Reuses the comprehension stack's own
# concept-equivalence so production and comprehension agree on what "matches".
# ---------------------------------------------------------------------------


def _compare_frames(goal: dict[str, Any], recovered: dict[str, Any],
                    mood: str) -> tuple[bool, list[str], list[tuple[str, str, str]]]:
    """Compare the goal frame against the comprehension-recovered frame.

    Returns (match, missing_roles, mismatched). ``missing`` = goal roles the
    recovered frame lacks; ``mismatched`` = (role, goal_value, recovered_value)
    where both present but unequal. Tense is compared leniently (a language
    that doesn't mark tense, like zh, may recover no tense — not a mismatch).
    speech_act: an interrogative goal must recover speech_act=question."""
    missing: list[str] = []
    mismatched: list[tuple[str, str, str]] = []
    for role in ("event", "agent", "patient", "location"):
        if role not in goal:
            continue
        gv = goal[role]
        rv = recovered.get(role)
        if rv is None:
            missing.append(role)
        elif isinstance(gv, str) and isinstance(rv, str):
            if not lw._concepts_equiv(gv, rv):
                mismatched.append((role, gv, rv))
        elif gv != rv:
            mismatched.append((role, str(gv), str(rv)))
    # Tense: lenient — only a mismatch if BOTH present and differ.
    if "tense" in goal:
        gt, rt = goal.get("tense"), recovered.get("tense")
        if rt and gt and gt != rt:
            mismatched.append(("tense", str(gt), str(rt)))
    # Mood -> speech act check for questions.
    if mood == "interrogative":
        if recovered.get("speech_act") != "question":
            mismatched.append(("speech_act", "question",
                               str(recovered.get("speech_act"))))
    match = not missing and not mismatched
    return match, missing, mismatched


__all__ = ["LanguageProduction"]
