"""DS03 source audit: no shared/global RNG or process-salted seeds at runtime.

The audit is a matcher over production Python source.  It deliberately reads
code only: comments and string literals are blanked with :mod:`tokenize` before
matching, so a docstring that *describes* ``hash()`` or ``random.Random`` does
not fail the audit.

Creation-time generation is the documented exception.  It may use a seeded
``numpy`` stream because it runs once before the shard simulation and derives
from the run/map seed.  Each allowlisted file names only the rules it needs, so
a new ``random.Random`` in an allowlisted file still fails.
"""
from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

from domains import determinism
from domains.autopilot import habit_roll
from worlds.bigville_world import BigvilleWorld

ROOT = Path(__file__).resolve().parent.parent
PRODUCTION_ROOTS = ("bigville", "worlds", "domains")


# --------------------------------------------------------------------------- rules
# Each rule is (name, compiled pattern).  The patterns are intentionally narrow:
# a broad "random" match would flag the word in prose and in the determinism
# helper's own public API.
RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    # A shared mutable RNG attribute/state on a world, game or module
    # (``_rng``, ``_rng_state``, ``_rng_stream``).
    ("shared-rng", re.compile(r"(?<![A-Za-z0-9])_rng\w*")),
    # Importing the stdlib random module, even before a call appears.
    ("stdlib-random-import", re.compile(
        r"^[ \t]*(?:import[ \t]+random\b|from[ \t]+random[ \t]+import\b)")),
    # The stdlib random module: Random(), random(), randrange(), shuffle(), ...
    ("stdlib-random", re.compile(
        r"\brandom\.(?:Random|random|randrange|randint|choice|shuffle|sample|"
        r"uniform|seed|randbytes|getrandbits)\b")),
    # A numpy Generator, seeded or not, outside the documented creation allowlist.
    ("numpy-random", re.compile(r"\b(?:np|numpy)\.random\b")),
    # A local generator variable seeded with numpy default_rng: rng.choice(...), etc.
    ("rng-method", re.compile(
        r"\b(?:rng|nrng|rrng|krng|drng|[A-Za-z_]+_rng)\."
        r"(?:random|randrange|randint|choice|shuffle|sample|permutation|"
        r"uniform|integers|normal|bytes)\b")),
    # A generator method call whose variable is not named rng (.random()).
    ("dot-random", re.compile(r"\.random\s*\(")),
    ("bare-rand", re.compile(r"\b(?:randrange|randint)\(")),
    # Bare shuffle/sample calls, excluding the determinism helper's exported
    # functions and their definition.
    ("bare-shuffle", re.compile(r"(?<![\w.])(?<!def )(?:shuffle|sample)\(")),
    # Python's process-salted hash() and identity id().  Both are hard failures:
    # a seed derived from either changes between processes.
    ("builtin-hash", re.compile(r"(?<![\w.])hash\(")),
    ("builtin-id", re.compile(r"(?<![\w.])id\(")),
    # Wall clock and uuid are process/run identity.  They are only a problem in a
    # stochastic seed path, so these rules require a seed/draw marker on the line.
    ("wall-clock", re.compile(
        r"\btime\.(?:time|time_ns|gmtime|localtime|strftime|monotonic|"
        r"perf_counter|sleep)\b")),
    ("process-uuid", re.compile(r"\buuid\.uuid[14]?\b")),
)

# Rules that are only a problem when the same line is a stochastic seed path.
SEED_PATH_RULES = frozenset({"wall-clock", "process-uuid"})
_SEED_CONTEXT = re.compile(
    r"\b(?:seed|seeded|rng|random|shuffle|sample|draw|roll|jitter|trait|"
    r"chance|stochastic)\b", re.IGNORECASE)

# ------------------------------------------------------------------------- allowlist
# Minimal, per-file and per-rule.  Every entry is creation-time generation that
# derives from an explicit run/map seed; none reads the wall clock, uuid, id() or
# an unseeded RNG.  Do not add a directory.
ALLOWLIST: dict[str, frozenset[str]] = {
    # Town-100 cast: rng(seed), names rng(seed+7), traits rng(seed+13).
    "worlds/bigville_town100_world.py": frozenset({"numpy-random", "rng-method", "dot-random"}),
    # Social priors and partner/kind streams: rng(seed+31/+37/+41).
    "worlds/bigville_social_seed.py": frozenset({"numpy-random", "rng-method", "dot-random"}),
    # Population, founding age, kinship and history streams: rng(seed + stream).
    "domains/population.py": frozenset({"numpy-random", "rng-method", "dot-random"}),
    # Per-record knowledge draws: rng(seed * 1000003 ^ crc32(name)).
    "domains/knowledge.py": frozenset({"numpy-random", "rng-method", "dot-random"}),
    # Founding relationships: rng(seed + cfg["stream"]).
    "domains/relationship_seeding.py": frozenset({"numpy-random", "rng-method", "dot-random"}),
    # Kinship (seed + KINSHIP_STREAM) and draw_capacities (seed + crc32(actor)):
    # creation-time streams keyed on the map seed and an actor name.  builtin-hash
    # is the TypeError probe used by the position/location bucket indexes, not a
    # seed input.
    "worlds/bigville_world.py": frozenset({"numpy-random", "rng-method", "dot-random", "builtin-hash"}),
    # The determinism helper is the single source of runtime draws.  Its id()
    # calls only detect reference cycles in canonicalisation; no seed uses them.
    "domains/determinism.py": frozenset({"builtin-id"}),
}

# Sites the plan asks us to audit and document even though they do not match a
# rule above.  The test below checks each one still exists and has a rationale.
CREATION_SITES: dict[str, str] = {
    "worlds/bigville_town100_world.py":
        "creation-time cast/trait streams from np.random.default_rng(seed + offset)",
    "worlds/bigville_social_seed.py":
        "creation-time social priors from np.random.default_rng(seed + offset)",
    "domains/population.py":
        "creation-time population/kinship streams from np.random.default_rng(seed + offset)",
    "domains/knowledge.py":
        "creation-time per-record knowledge stream from the seed and the record name",
    "domains/relationship_seeding.py":
        "creation-time founding relationships from np.random.default_rng(seed + stream)",
    "worlds/bigville_world.py":
        "creation-time kinship and capacity streams keyed on the map seed and actor name",
    "domains/interoception.py":
        "draw() is a local SHA-256 presentation/creation draw (acuity, sound, jitter), not an outcome",
    "bigville/llm_log.py":
        "new_run_id() uses wall time and uuid4 only to name a log file, never a simulation outcome",
}


# ----------------------------------------------------------------------- matcher
def _code_lines(text: str) -> list[tuple[int, str]]:
    """Source lines with comments and string literals blanked, one per line.

    Blanking keeps line numbers stable while preventing prose and docstrings
    from tripping the audit.  On a file that cannot be tokenised (e.g. a
    synthetic fragment) the raw lines are used so the rule still fires.
    """
    lines = text.splitlines()
    masked = list(lines)
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return list(enumerate(lines, 1))
    for token in tokens:
        if token.type not in (tokenize.STRING, tokenize.COMMENT):
            continue
        start_row, start_col = token.start
        end_row, end_col = token.end
        for row in range(start_row, end_row + 1):
            line = masked[row - 1]
            first = start_col if row == start_row else 0
            last = end_col if row == end_row else len(line)
            masked[row - 1] = line[:first] + " " * (last - first) + line[last:]
    return list(enumerate(masked, 1))


def scan_source(text: str, path: str,
                *, allowlist: dict[str, frozenset[str]] | None = None) -> list[dict]:
    """Find forbidden stochastic/process sources in ``text`` as ``path``.

    Returns one finding per (line, rule) with the path, 1-based line, rule name
    and the trimmed source line, so a failure names the exact site.
    """
    allowed = (ALLOWLIST if allowlist is None else allowlist).get(path, frozenset())
    findings: list[dict] = []
    for number, line in _code_lines(text):
        for rule, pattern in RULES:
            if rule in allowed:
                continue
            if rule in SEED_PATH_RULES and not _SEED_CONTEXT.search(line):
                continue
            match = pattern.search(line)
            if match is None:
                continue
            findings.append({"path": path, "line": number, "rule": rule,
                             "match": match.group(0),
                             "text": line.strip()})
    return findings


def production_files(root: Path = ROOT) -> list[tuple[str, Path]]:
    """Production Python files, excluding tests, tools and generated game assets."""
    files: list[tuple[str, Path]] = []
    for relative_root in PRODUCTION_ROOTS:
        base = root / relative_root
        for path in sorted(base.rglob("*.py")):
            relative = path.relative_to(root).as_posix()
            if relative.startswith("bigville/game/assets/") or "/assets/" in relative:
                continue
            files.append((relative, path))
    return files


def _format(findings: list[dict]) -> str:
    return "\n".join(
        f"{item['path']}:{item['line']}: {item['rule']}: {item['text']}"
        for item in findings)


# ------------------------------------------------------------------------- tests
def test_production_sources_have_no_shared_or_global_rng():
    findings: list[dict] = []
    for relative, path in production_files():
        findings.extend(scan_source(path.read_text(encoding="utf-8"), relative))
    assert not findings, (
        "new stochastic/process-salted source found; migrate it to domains.determinism "
        "or add a minimal, commented creation-time allowlist entry:\n" + _format(findings))


def test_audit_rejects_stdlib_random_and_shared_rng_state():
    findings = scan_source(
        "import random\n"
        "class World:\n"
        "    def roll(self):\n"
        "        self._rng = random.Random(7)\n"
        "        return self._rng.random()\n",
        "domains/synthetic.py")
    assert {(item["line"], item["rule"]) for item in findings} == {
        (1, "stdlib-random-import"),
        (4, "shared-rng"), (4, "stdlib-random"),
        (5, "shared-rng"), (5, "dot-random")}


def test_audit_rejects_numpy_and_bare_shuffle_outside_the_allowlist():
    findings = scan_source(
        "import numpy as np\n"
        "rng = np.random.default_rng(seed)\n"
        "rng.shuffle(names)\n"
        "order = shuffle(names)\n"
        "picked = sample(names, 2)\n",
        "worlds/synthetic.py")
    assert {item["rule"] for item in findings} == {
        "numpy-random", "rng-method", "bare-shuffle"}


def test_allowlist_is_per_file_and_per_rule():
    # The town stream is allowed ...
    assert scan_source("rng = np.random.default_rng(seed)\nrng.shuffle(rows)\n",
                       "worlds/bigville_town100_world.py") == []
    # ... but a stdlib Random in the same file is still a violation.
    findings = scan_source("import random\nrandom.Random(seed).shuffle(rows)\n",
                           "worlds/bigville_town100_world.py")
    assert {item["rule"] for item in findings} == {
        "stdlib-random-import", "stdlib-random"}


def test_audit_rejects_builtin_hash_and_id_in_a_seed():
    findings = scan_source(
        "seed = hash(actor)\n"
        "other = id(actor)\n",
        "domains/synthetic.py")
    assert {item["rule"] for item in findings} == {"builtin-hash", "builtin-id"}


def test_audit_only_rejects_clock_and_uuid_in_a_seed_path():
    seeded = scan_source("seed = int(time.time())\nseed = uuid.uuid4()\n",
                         "domains/synthetic.py")
    assert {item["rule"] for item in seeded} == {"wall-clock", "process-uuid"}
    # A log filename may use wall time and uuid: it is not a simulation outcome.
    assert scan_source('run_id = time.strftime("%Y") + uuid.uuid4().hex\n',
                       "bigville/synthetic.py") == []


def test_audit_reads_code_not_docstrings_or_comments():
    text = (
        '"""Documentation says hash(), id(), random.Random and uuid.uuid4 are forbidden."""\n'
        "# random.shuffle(rows) and np.random.default_rng(seed) are forbidden here\n"
        "value = 1\n"
    )
    assert scan_source(text, "domains/synthetic.py") == []


def test_every_documented_creation_site_exists_and_has_a_rationale():
    for relative, rationale in CREATION_SITES.items():
        assert (ROOT / relative).is_file(), relative
        assert rationale.strip(), relative


def test_report_sample_is_stable_for_the_same_seed():
    world = BigvilleWorld.from_town100(autonomous_actors=False)
    first = world.report(sample_size=12, seed=17)["population"]["sample_estimate"]
    again = world.report(sample_size=12, seed=17)["population"]["sample_estimate"]
    changed = world.report(sample_size=12, seed=18)["population"]["sample_estimate"]
    assert first == again
    assert first["sample_size"] == changed["sample_size"] == 12
    assert first["estimates"] != changed["estimates"]


def test_habit_roll_is_stable_and_uses_the_determinism_helper():
    first = habit_roll("Ada", "boundary", 3, "work")
    assert first == habit_roll("Ada", "boundary", 3, "work")
    assert 0.0 <= first < 1.0
    assert first == determinism.uniform(0, "autopilot-habit", "Ada", "boundary", 3, "work")
