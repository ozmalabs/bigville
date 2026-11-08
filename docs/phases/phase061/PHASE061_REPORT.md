# Phase 061 report: speech parser (a small model, a cache, and the fixed reference)

## Summary

A simple listener can now place speech that the Phase 060 grammar cannot. `SpeechParser.parse` runs the
grammar and the speaker's raw payload first. Only when the speaker gave no structure, the listener is a simple
backend, and the text is short enough, does it look in its own cache, then make at most one model call (plus one
repair). Every failure leaves the utterance unplaced and is counted by cause. The parser is off by default: the
simple backend uses it only when a caller passes one in (`speech_in.using_parser`).

Measured on a hand-labelled set of 200 utterances (`tests/fixtures/speech_labelled.json`), the grammar places 47
lines, with 7 of those misplaced. With a model that answers each line correctly, 155 lines are placed and 7 are
misplaced. A scripted model with 14 plausible mistakes places 151, and 14 lines end up misplaced in total: 7 from the grammar
and 7 from the model's scripted mistakes. These numbers are for the
harness with scripted answers. No real model was called (see Limits).

The 60-turn simple run, with the switch off, matches a fresh `git archive HEAD` run on all 100 residents.

## Changes

New files:
- `bigville/backends/speech_parser.py`: `SpeechParser`, `frame` (the normalised key), `check_reply` (the act and
  slot check), `fixed_prefix` and `reference_hash`, the JSONL cache, the budget and timeout, the repair, `summary`.
- `domains/speech_parser_check.py`: the self-test for `SPEECH_PARSER` (caps, confidence, that the prefix names every
  understood act, and that every example reply passes `check_reply`).
- `packs/bigville/world/speech_parser.json` and `packs/test_hamlet/world/speech_parser.json`: `SPEECH_PARSER` with
  `enabled: false`, `schema_version`, `caps`, `confidence.model`, and the prefix text (intro, reply schema, five
  examples). Both files are exporter-canonical (checked with `tools/export_pack.py` into a scratch directory).
- `tests/test_phase061_speech_parser.py`: 25 tests.
- `tests/fixtures/speech_labelled.json`: 200 utterances, each with the act it should give or `null`.
- `docs/phases/phase061/`: this report, `scores.json` (written by the test file's `__main__`), two 60-turn
  behaviour files and their comparison, and `logs/`.

Shared files (each hunk is small; the anchor is the unchanged line before it):
- `bigville/backends/speech_in.py` (a Phase 060 file, edited here because the hook belongs in the listener). Four
  hunks:
  1. After the body of `switched()`, the line `        _OVERRIDE = previous`: a new context manager
     `using_parser(parser)` sets the module variable `_PARSER` for a block.
  2. After `_OVERRIDE = None          # None: the pack's switch. ...`: the line `_PARSER = None` (default None).
  3. In `understand`, the signature becomes `understand(utterance, listener_context=None, parser=None)`, and the
     branch `found = G.place(...)` followed by `if found is None:` now returns `None` when `parser` is None, else
     `parser.parse(...)`. The docstring gains a paragraph on the parser.
  4. In `hear`, after `tie = float(nearby.get(speaker, {}).get("tie_strength", 0.0))`, the call
     `understand(record, {"stranger": ...})` now passes the listener, the turn, the names in view, the listener's
     name and the affordance kinds (as topic words), and `parser=_PARSER`. `hear` returns at once while the switch
     is off, so these arguments are not evaluated in the default run.
- `packs/bigville/pack.json` and `packs/test_hamlet/pack.json`: after `    {"name": "SPEECH_ACTS", "file": "world/speech_acts.json"},`
  (the Phase 060 row for `SPEECH_UNDERSTANDING` is the line that gained a comma), one line
  `{"name": "SPEECH_PARSER", "file": "world/speech_parser.json"}` at the end of `tables`.
- `domains/bigville_entities.py`: two lines in `check_consistency`, after the line
  `    check_speech_acts(_WORLD_PACK.path, errors, warnings, info)` and before `    stats = {`: a lazy import of
  `check_speech_parser` and its call.

Not touched: `bigville/backends/ocelot.py`, `worlds/bigville_world.py`, `bigville/backends/cheap.py`,
`bigville/providers/` (used only), and the other sessions' dirty files.

### Design

- **Stage one** is `speech_in.understand` (raw payload, then grammar). **Stage two** runs only when the speaker sent
  no raw payload (`raw_data` is None), the listener's `kind` is `"cheap"` (the simple backend), and the text is at
  most `max_utterance_chars` long.
- **Prefix.** The system text is built from `SPEECH_PARSER.prefix` and the understood rows of `SPEECH_ACTS`: one line
  per act, with its description and slots, then the reply schema and the examples. The user part is the utterance
  and three context fields: the speaker's name, whether the listener knows the speaker, and the topic words. A repair
  adds a `repair` field to the user part. The prefix is the same bytes on every call, and its hash is part of the
  cache key.
- **Frame and cache key.** Names (the speaker, the listener, and the names in view, plus a capitalised vocative at
  the start or end of the line that is not a word of the act table) become `{name1}`, `{name2}`, ...; count words and
  digits become `{n1}`, .... The key is the frame text. Each cache line is `{"key", "schema", "ref", "answer"}`. A line
  whose schema or reference hash differs from the parser's is skipped and counted as stale. A slot value is stored
  with the same placeholders, so "Bram, bring me two loaves" and "Ada, bring me three loaves" share one answer, and
  the answer is filled in again for the utterance now heard.
- **Validation** (`check_reply`) is the same as a speaker's raw payload (an understood act, slots the act names), plus
  the slot kinds: a `name` must be the speaker, the listener, or a name in view; a `word`, `text` or `question` slot
  must be words of the line; a `question` must start with a question word. A null act is a valid answer; it is
  cached as well.
- **Failures** (`unplaced` plus a cause): `provider_error`, `timeout`, `replay_mismatch`, `invalid_output` (after the
  repair), `invalid_cache`, `call_cap`, `spend_cap`, `too_long`, `not_eligible`, `model_none`, `cache_declined`. A
  failure is not cached.
- **Budget.** `CallBudget` (Phase 055, `bigville/backends/autopilot.py`) with one fixed key: its per-day cap is the
  per-run call cap, and `max_spend` caps the summed `last_cost`. A repair counts as a call.
- **Timeout.** The call runs in a worker thread that is joined for `timeout_s`. An abandoned call keeps running, and
  its cost is not counted.

## Validation

Commands are run from `/home/matt/ozmadev/bigville` unless stated.

| Check | Command | Result |
|---|---|---|
| Entity self-test | `python3 domains/bigville_entities.py` | exit 0; ERRORS (0), WARNINGS (0); new info line `SPEECH_PARSER: off by default ..., 5 examples, the fixed prefix is 2411 bytes` |
| test_hamlet self-checks | `check_speech_acts` and `check_speech_parser` on `packs/test_hamlet` (called directly) | 0 errors, 0 warnings |
| Phase 061 tests | `python3 -m pytest -q -p no:cacheprovider tests/test_phase061_speech_parser.py` | 25 passed (2.1 s) |
| Phase 060 tests (after the 4 `speech_in.py` hunks) | `python3 -m pytest -q -p no:cacheprovider tests/test_phase060_speech_in.py` | 62 passed, 3 skipped (same as the Phase 060 report) |
| Pack export | `python3 tools/export_pack.py --pack <bigville, test_hamlet> --out <scratch>` | `speech_parser.json` (both packs), `pack.json` and `speech_acts.json` byte-identical to the working tree |
| Score table | `PYTHONPATH=.:tests python3 tests/test_phase061_speech_parser.py` | writes `docs/phases/phase061/scores.json` and prints the table below |
| 60-turn, switch off, working tree vs `git archive HEAD` | `docs/phases/phase060/measure_speech.py --switch off --turns 60` on a snapshot of each tree (logs in `logs/`) | both: 285 utterances, hunger mean 0.4442, 0 deaths; `compare_arms.py`: 0 of 100 residents with a different action sequence |
| Full suite | `timeout 3600 python3 -m pytest -q -p no:cacheprovider -rfE` on a snapshot of the working tree (`logs/full_suite_tree.log`) | **6 failed, 2122 passed, 12 skipped** in 2993 s (see below) |

The full suite ran on a snapshot taken after every code change except one: the `precision` column in the score
printout (`_grade` in the test file) was corrected after the snapshot. No test asserts that column.

Full-suite failures and attribution:
- `tests/test_bigville_server.py::test_asset_manifest_covers_entity_items_and_modular_buildings`: `jail` is in the world
  and not in the asset manifest. On the snapshot with this phase's additions removed, it still fails.
- Four `tests/test_phase057_tui.py` tests (`over_http_a_menu_row...`, `over_http_walking_to_a_known_place...`,
  `over_http_a_reaction_is_delivered...`, `the_server_refuses_a_bad_reply...`): the same result with this phase's
  additions removed (5 failed and 44 passed for these two files). The failing assertions concern the contest log and
  intensity checks in the server, not speech. These come from other sessions' uncommitted changes.
- `tests/test_phase055_concurrency.py::test_a_slow_provider_is_faster...`: a timing check (about 14 s against 10.8 s
  under load, run in parallel with the 60-turn runs). It passes on rerun (6 passed for that file).
- Clean `git archive HEAD` copy: the six failing tests and all of `test_phase057_tui.py` pass there (50 passed). HEAD
  lacks the uncommitted Phase 060 and the other sessions' work, so this run does not isolate the cause on its own.
  The with-and-without comparison above is the isolation.
- No Ocelot test failed in this run. Phase 060 saw three Ocelot failures from a missing module; they did not occur in
  this snapshot.

### Scores on the labelled set

Labels are hand-written from the act meanings in `SPEECH_ACTS`, not from the grammar: 155 lines with an act and 45
with none (plain facts, odd remarks, and call-outs, which are not acts). Speakers, listeners and names in view were
assigned to each line by index. Scripted answers are keyed to the fixture's utterance text. The "ceiling" arm answers
each label. The "errors" arm answers the label except for 14 lines where the fixture gives a plausible mistake (wrong
act, invented name, or non-JSON). Both arms run the grammar first, as the parser does.

| Arm | Placed (of 200) | Correct (of 200) | Misplaced (of 200) | Precision | Recall (of 155) | Model calls | Cost | Latency |
|---|---|---|---|---|---|---|---|---|
| Grammar only | 47 (23.5%) | 85 (42.5%) | 7 (3.5%) | 0.851 | 0.258 | 0 | none | none |
| Grammar + model, label ceiling | 155 (77.5%) | 193 (96.5%) | 7 (3.5%) | 0.955 | 0.955 | 153 | not measured | not measured |
| Grammar + model, 14 scripted mistakes | 151 (75.5%) | 179 (89.5%) | 14 (7.0%) | 0.907 | 0.884 | 160 | not measured | not measured |

- Placed by source, first pass: grammar 47, model 108 (ceiling) or 104 (errors), cache 0, raw 0. The set has no raw
  payloads, and the first pass had no cache hits (no line reached the model with a frame an earlier line had stored).
- Second pass over the same set, ceiling arm: 0 calls and 153 cache hits (valid answers and null answers).
- Errors arm, invalid replies: 7 lines failed after the repair (3 invented names, 2 non-questions, 1 unknown act,
  1 non-JSON). Repairs: 7. Of the 45 lines with no act, 42 got a null answer. The other 3 (`Two carts went past the
  church.`, `Eight geese on the green.`, `Bell rang at noon.`) got a wrong act from the errors arm, so they are in
  the misplaced column.
- The grammar's 7 misplacements are all question-slot matches: "Can you help me with the fence?", "Would you lend me
  your hammer", "Would you give me a loaf for my boy", "Shall I carry that for you", "Have some ale, on the house",
  "Who knows about the weather", "Have you heard? The bridge is closed". They are placed as `question`, because the
  question slot accepts any words after an opener. The model stage cannot correct them, because the grammar places
  first. Those misplacements are in Phase 060's grammar, which this phase did not change.

Latency is not measured: the scripted provider returns at once, so the figure (about 0.1 ms per call, including the
worker thread) says nothing about a real service. Cost is 0 because the scripted provider reports none.

### Tests (tests/test_phase061_speech_parser.py, 25 tests)

- Frame and vocatives: the joined frame of two utterances, and that "Hello, Ada" and "Thanks, Ivo" differ.
- Cache: a normalised duplicate hits the cache with no call; the cache loads at start and a stale line is skipped;
  a null answer is cached.
- Prefix: byte-identical across calls and equal to `fixed_prefix`; it names every understood act and not `inform`;
  the payload's variable fields are the line and its context.
- Validation: an invented name is rejected and repaired once; an unknown act is rejected; a listener's own name is
  accepted; a slot must come from the line.
- Failures and caps: provider error (unplaced, counted, not cached); timeout; call cap; spend cap; only a simple
  listener with no raw payload and a short text is asked.
- Grammar placements are kept and make no call.
- Loopback: the provider class runs against `tests/llm_stub.py` (the system message equals the prefix, and the key is
  not in the summary); a 500 is a provider error; a bad reply is repaired once.
- Record and replay: a recorded run (`RecordingProvider` into a `Transcript`) replays with the same placements
  (`ReplayProvider`, fresh cache); with the recorded cache, the replay makes fewer calls and places the same acts.
- Listener hook: a heard greeting is placed only when a parser is given, and the reply is queued.
- Self-test: `check_speech_parser` is clean for both packs.
- Labelled set: 200 unique lines, 45 with no act; the pinned scores above (grammar 47 / 85 / 7; ceiling 155 / 193 / 7
  with 153 calls; errors 151 / 179 / 14 with 160 calls); the second pass makes no call.
- Cause names: a check that `CAUSES` holds the causes the report lists.

## Limits

- **No real model was called.** The model rows are the fake provider's scripted answers, so they describe this
  harness, not a small model. The ceiling arm answers every label, and the errors arm uses 14 mistakes I chose by
  hand. Neither says how a real model would do. Choosing and measuring the model are out of scope (brief).
- **Cost and latency are not measured** (see above). The caps in `SPEECH_PARSER.caps` (1000 calls per run, timeout
  10 s, one repair, 240 characters) are APPROX authored values, marked as such in the pack's `_doc`.
- **The labels are my judgements.** No second reader checked them, and a reader may disagree on some lines.
- **Names.** A name is a slot only when it is the speaker, the listener, a name in view, or a capitalised vocative.
  An unknown name in mid-sentence stays as words in the frame, so "I saw Martha" and "I saw Ivo" have different keys.
- **Raw share is 0 on the set** (no raw payloads). The raw path is covered by Phase 060's tests.
- **Timeout.** A timed-out call keeps running in its thread, and its cost, if any, is not counted. The provider's own
  timeout (60 s by default) is longer than the parser's 10 s.
- **Concurrency.** The cache and the counts are locked, and so is the budget. Parallel residents are not tested with
  a parser. The parser is not wired into the game: the only caller is the listener hook, which the default run never
  reaches.
- **Topic words** are the affordance kinds in view (up to 8). That is an approximation of "topic words in sight", and
  no test checks its content.
- **The cache** has no size limit and no eviction. It is written beside the path the caller gives; the parser does not
  choose a path.
- **Parser and vocabulary.** A capitalised word that appears in the act table's wording (for example "Good", "Hello")
  is never a vocative. A resident named with such a word would not be a name slot.
- **Grammar** (Phase 060, not changed here): the question slot takes any words after an opener, and the name slot
  takes any words, so "Thanks, that was kind of you" gives `target` "that was kind of you" and "Hello there!" gives
  `target` "there". The first is the thanks act with a wrong slot; the second is the greeting act with a wrong slot.

## Open questions

1. Should the grammar's question and name slots be narrowed? The 7 misplacements above come from the question slot.
   This is a Phase 060 fix. It changes the listener only where the switch is on.
2. Who checks the 200 labels? A second reader would give a measure of label disagreement, which the scores do not
   have.
3. Is a live run on the 200 lines with a small model wanted? It needs a model choice and spend approval (both are out
   of scope here).
4. Where does the cache file live for a run, and should a replay use the recorded cache by default? The report
   assumes the caller passes the path.
5. Null answers are cached. A new reference hash (for example, a changed prefix or model) invalidates them. Should the
   model name also be part of the reference hash? It is not now.
6. `max_calls_per_run` is one budget key, so one parser per run gets the whole cap. If one run ever has several
   parsers, each gets its own cap. Is that the intended scope?
7. A timed-out call keeps running. Should the parser cancel it, or count its cost when it finishes?
8. The 60-turn comparison was run once per arm, with the Phase 058 script's default seeding and the pack's default.
   Phase 060 ran the same way, so the two can be compared, but neither has a second seed.
