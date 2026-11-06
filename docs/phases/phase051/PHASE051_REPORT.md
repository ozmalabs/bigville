# Phase 051 report: words for numbers and statuses (the lexicon)

## Summary

The pack now holds a lexicon: band tables for 28 numeric quantities, status tables for 6 more, one alias
(`trade`), reverse words for intensity, amounts and verbs, and a registry that maps observation fields to
quantities. `domains/lexicon.py` reads it through `domains.pack.load_pack`. `describe`, `value_for`,
`bands`, `quantities`, `intensity_value`, `amount_value` and `resolve_verb` take an optional `pack`. The
hamlet test pack has its own smaller lexicon, and its words differ with no code change.

Nothing in the world or any backend changed. The phase translates numbers that already exist.

## Changes

New files:
- `domains/lexicon.py`: the reader (API above). Lookup is by thresholds: monotone, total, values clamped to
  the range. Status keys map to phrases, with `unknown` as the fallback.
- `domains/lexicon_check.py`: `check_lexicon(pack_path_or_name, errors, warnings, info)`, called by the entity
  self-test. It reads the pack directly, not through `world_affordances` (deliberate, as the supervisor asked).
- `packs/bigville/world/lexicon.json`: tables `LEXICON_QUANTITIES`, `INTENSITY_WORDS`, `AMOUNT_WORDS`,
  `VERB_ALIASES`, `LEXICON_PAYLOAD`. Written in the export tool's byte format; the export round-trip test passes.
- `packs/test_hamlet/world/lexicon.json`: three quantities (energy, hunger, hour) with different words, and
  smaller reverse-word tables.
- `tests/test_phase051_lexicon.py`: 179 tests (parametrised over the band tables).
- `docs/phases/phase051/PHASE051_REPORT.md` (this file) and `full_suite.log`.

Shared files (tract A also has uncommitted edits in these; only my hunks are listed):
- `packs/bigville/pack.json`: 24 added lines. Five manifest entries (`LEXICON_QUANTITIES`, `INTENSITY_WORDS`,
  `AMOUNT_WORDS`, `VERB_ALIASES`, `LEXICON_PAYLOAD`, each file `world/lexicon.json`) after the
  `FISCAL_BACKEND_OWNED` entry at the end of `tables`. The file had no other changes.
- `packs/test_hamlet/pack.json`: the same 24 added lines at the same place. The file had no other changes.
- `domains/bigville_entities.py`: one hunk in `check_consistency`, lines 1589 to 1591, directly after
  `_check_fiscal(errors, warnings, info)`. It adds a comment, the import of `check_lexicon`, and the call
  `check_lexicon(_WORLD_PACK.path, errors, warnings, info)`. The other added hunks in this file (around line
  613 `_check_health`, and line 1582 `_check_health(...)`) are tract A's Phase 037 work, not mine.

Existing tests: none changed. No assertion was edited, weakened or removed.

Quantities (ranges and thresholds; "src" is the pack table or code the edge is aligned with; "APPROX" is my
invented model choice):

| Quantity | Range | Self edges | Other edges | Source of edges |
|---|---|---|---|---|
| energy | 0 to 100 | 0, 5, 15, 35, 40, 70 | 0, 15, 40 | EXHAUSTION e_collapse, e_low, e_mid, e_high (x100, cross-checked); 35 = simple backend `rest_energy_threshold` (cheap.py, code, not cross-checked) |
| hunger | 0 to 4 | 0, 1, 2, 3 | 0, 2 | 1 = one unmet meal (worlds/bigville_world.py adds 1.0); 2 = CARE care_hunger_need and malnourished_hunger (cross-checked); 4 = CARE starve_limit (cross-checked); 3 APPROX |
| health (value) | 0 to 1 | 0, 0.25, 0.5, 0.75 | same | 0.5 = CARE treat_health_base (cross-checked); 0.25, 0.75 APPROX |
| health_status | keys of HEALTH_CONDITIONS | per key | per key (not unknown) | HEALTH_CONDITIONS keys (cross-checked) |
| strength | 0 to 2 | 0, 0.5, 0.9, 1.3 | same | 1.0 is ACTOR_DEFAULTS str_base (not an edge); others APPROX |
| stamina (capacity) | 0 to 2 | 0, 0.5, 0.9, 1.3 | none (self only) | APPROX |
| mood | 0 to 1 | 0, 0.25, 0.5, 0.75 | same | 0.5 = ACTOR_DEFAULTS body.mood (cross-checked); others APPROX |
| intoxication | 0 to 1 | 0, 0.2, 0.5, 0.8 | same | APPROX; not published (Phase 034) |
| deficiency | 0 to 1 | 0, 0.25, 0.5, 0.75 | none | APPROX; not published (Phase 035) |
| strain | 0 to 1 | 0, 0.3, 0.6, 0.85 | same | APPROX; not published (Phase 050) |
| condition (item) | 0 to 1 | 0, 0.25, 0.5, 0.75 | same | APPROX |
| quality (item) | 0 to 1 | 0, 0.25, 0.5, 0.75 | same | APPROX |
| load (carry ratio) | 0 to 3 | 0, 0.5, 1, 2 | 0, 1, 2 | 1 = CARRYING overload_ratio, 2 = drop_ratio (cross-checked); 0.5, 3 APPROX |
| chill | 0 to 1 | 0, 0.3, 0.6, 0.85 | same | APPROX; not published |
| soaked | 0 to 1 | 0, 0.3, 0.6, 0.85 | same | APPROX; not published |
| skill (and alias trade) | 0 to 1 | 0, 0.2, 0.4, 0.6, 0.8 | none | APPROX; ACTOR_DEFAULTS skill 0.7 is in the "skilled" band |
| hour | 0 to 24 | 0, 5, 7, 12, 14, 18, 21 | same | 5 and 21 = EXHAUSTION night_end_hour and night_start_hour (cross-checked); others APPROX |
| season | keys of SEASONS | per key | same | cross-checked |
| weather | keys of WEATHER | per key | same | cross-checked |
| light | 0 to 1 | 0, 0.1, 0.4, 0.8 | same | APPROX; not published (Phase 042) |
| distance (tiles) | 0 to 52 | 0, 2, 6, 15, 30 | same | 52 = FOUNDING_MAP width (cross-checked); others APPROX |
| duration (minutes) | 0 to 1440 | 0, 15, 60, 240, 480 | same | 15 = TIME minutes_per_tick; 1440 = ticks_per_day x minutes_per_tick (both cross-checked); 240, 480 APPROX |
| amount (count) | 0 to 100 | 0, 1, 2, 5, 10, 25, 50 | same | APPROX; words match AMOUNT_WORDS (tested) |
| age (years) | 0 to 100 | 0, 4, 13, 18, 65 | same | LIFE_STAGES age_min (cross-checked) |
| life_stage | keys of LIFE_STAGES | per key | none | cross-checked |
| relationship_strength (tie) | 0 to 10 | 0, 0.5, 1.5, 3, 5 | same | bond band codes of worlds/bigville_bond_world.py `_band_code` (code, not cross-checked); top 10 APPROX |
| relationship_kind | keys: feud, friend, acquaintance, blood_kin, chosen, unknown | per key | none | must cover RELATIONSHIP_KINDS and RELATIONSHIP_DEFAULT kinds (cross-checked) |
| temperament (valence) | -1 to 1 | -1, -0.33, 0.33 | same | FOUNDING_PERSONALITY valence (key checked); not published (058) |
| trust, spite, outlook | 0 to 1 | thirds / 0.15, 0.4, 0.7 | none | FOUNDING_PERSONALITY keys (checked); spite's 0.15 is the founding mean; not published |
| charm | 0 to 1 | 0, 0.33, 0.67 | same | FOUNDING_PERSONALITY charm_weight; not published |
| finery | 0 to 6 | (none) | 0, 1, 3, 5 | APPROX; other only; not published |
| day_block | keys (provisional) | per key | per key | Phase 058 will set the blocks; not published |

"Not published" means no world read-off exists yet. Those tables carry "read-off not yet published" in their
`_doc`, and the self-test requires that text on exactly those tables.

Reverse words:
- `INTENSITY_WORDS` (APPROX numbers, 1.0 normal): gently 0.5, carefully 0.7, normally 1.0, hard 1.5, with all
  your strength 2.0.
- `AMOUNT_WORDS`: none 0, one 1, a few 3, a handful 5, several 10, a lot 25, a cartload 60. Each word
  describes back to its own phrase (tested).
- `VERB_ALIASES`: 23 canonical verbs, 65 words including each canonical verb mapped to itself. For example
  smash, break, bash, batter all map to `smash`.

Payload registry (`LEXICON_PAYLOAD`): 29 entries. Eleven name a quantity. The other 18 name a hidden field with a reason
(engine counters, coordinates, multipliers, the tie band code).

## Validation

Run in `/home/matt/ozmadev/bigville`:

1. Baseline self-test before my change: `python3 domains/bigville_entities.py` gave ERRORS (0), WARNINGS (0),
   exit 0. Tract A's uncommitted work was already present then.
2. New tests: `python3 -m pytest -q -p no:cacheprovider tests/test_phase051_lexicon.py` gives 179 passed.
3. Self-test after my change: `python3 domains/bigville_entities.py` gives ERRORS (0), WARNINGS (0), exit 0. The
   lexicon info line reads "LEXICON (bigville): 35 quantities (28 numeric), 5 intensity words, 7 amount words,
   65 verb words, 29 payload fields; all checks pass".
4. Hamlet self-test: `python3 -m domains.check --pack test_hamlet` gives ERRORS (0), WARNINGS (0), exit 0.
5. Full suite on the final files: `timeout 1500 python3 -m pytest -q -p no:cacheprovider` gives 3 failed,
   1222 passed, 2 skipped, in 362 s. Log: `docs/phases/phase051/full_suite.log`.
   - The 3 failures are the known Ocelot baseline: `test_bigville_ocelot_communication.py::
     test_real_ocelot_advertises_only_wired_communication_capabilities`,
     `test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`,
     `test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`.
     Each raises `OcelotUnavailableError` (no module `worlds.bigville_ocelot_adapter`). None involves a lexicon file.
   - No other failure appeared, including with tract A's uncommitted edits present.
   - During development three tests failed because child packs (tests in phase013b, phase014, phase015) ran the
     self-test on a temporary directory. I fixed that by passing the pack directory. One of them (phase014) also
     showed a real drift case: that child pack moves TIME minutes_per_tick to 7.5. I made drift in a child pack a
     warning, not an error, so its existing zero-error assertion still holds. Drift in the bigville pack is an error.

What the tests cover (`tests/test_phase051_lexicon.py`):
- Every numeric band table is contiguous (each band's max is the next band's min), starts at the range low,
  ends at the range high, has unique labels, and every band is reachable over a grid that includes values outside
  the range. Lookup never steps back as the value rises.
- `value_for` then `describe` returns the same label for every band.
- No digit appears in any label or phrase.
- Hunger: self "famished", other "looks gaunt". Stamina, skill, deficiency, trust, spite, outlook and
  relationship kind have no other phrase. Strength has one. Finery has no self phrase.
- Status keys equal their source tables, with `unknown` as fallback.
- Reverse words resolve; numbers pass through; unknown words raise ValueError.
- The hamlet pack gives different words for energy, hunger and "hard", and resolves "bash" to `smash`.
- The payload test builds a real town100 world (`create_game(scenario="town100", default_backend="simple")`,
  about one second) and checks every numeric field of the first five residents' observations against the registry.
- Self-test checks reject a band table that does not start at the range low, a repeated label, a missing
  `unknown`, a digit in a phrase, an edge that drifts from its source, and a reverse word that names nothing.
- A child pack that moves a source edge gets a warning and no error.

## Limits

- The payload test reads turn 0 only. At turn 0 the observation lists `worn`, `practice`, `physical_objects`
  and `physical_events` were empty, so their numeric fields were not checked. Fields that appear later are not
  checked either.
- Terrain tile names and calendar counters are registered as hidden. No word table covers tile names.
- Thresholds marked APPROX are model choices, not sourced figures. The phrases are my drafts. No one has
  reviewed the wording.
- Status quantities: `value_for` returns the key string, not a number.
- Relationship strength: bond codes 0 (no tie) and 1 (under 0.5) are one band, "stranger". The signed strength in
  RELATIONSHIP_KINDS is not used.
- Intensity and verb words are not tied to Phase 050. The pack has no `VERBS` table, so the canonical verb check
  is skipped and reported as info. The intensity numbers are APPROX, not Phase 050's `intensity`.
- The source-edge checks run for the bigville pack and its children. A child's drift is a warning. A test pack
  states its own edges and is not checked against bigville.
- `describe` with a template phrase (skill, trade) needs `what=`. Without it the call raises ValueError.
- Nothing was run in a 100-resident village. The phase changes no behaviour, so no run was needed.

## Open questions

1. Phase 050 lands the `VERBS` table and an `intensity` scale. At that point, check that every alias resolves
   and align INTENSITY_WORDS with the scale. The check is already in place: it runs when `VERBS` exists.
2. Phase 058 should set the day-block keys. The current `day_block` keys are provisional.
3. Should `other` perspectives for temperament, charm and finery be kept? I gave them an observer view because
   manner and clothes are visible. That is a judgement call.
4. Should `relationship_strength` also use the signed strength from RELATIONSHIP_KINDS?
5. Should the 3.0 hunger edge and the skill edges be replaced with values from the design notes? They are APPROX.
