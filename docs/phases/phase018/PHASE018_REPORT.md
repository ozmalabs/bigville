# Phase 018: generated LLM instructions

## Summary

`PromptBuilder` now builds the system text from the data pack. The premise, the action vocabulary with
descriptions, the boundary and continuation rules, and the response fields all come from pack tables. Each
prompt record carries the schema (`bigville/prompt/2`), the pack name, and a sha256 of the pack's base data.

The private part carries what the resident holds, selected by a documented rule with fixed caps. It no longer
carries every memory. For three founders of the 100-resident town, the private part fell from 103 to 160 KB (before)
to 6.0 to 6.6 KB (after). An aware-only item appears as name and gist, with no basis and no content. A place appears at the
precision held (exact cell or landmark), never the map.

Derived law and policy understanding now reaches `_context`'s `world_frames`. A resident gets the laws and policies
they are aware of or understand, at the level held. The global law list is not restored. The chatter and weather
phrases moved from `bigville/runtime.py` into the pack.

Self-test: 0 errors, 0 warnings. Hamlet check: 0 errors, 0 warnings. Seeds check: matches. Full suite: 486 passed,
2 skipped, 3 failed. The 3 failures are the other session's Ocelot tests, and they fail on the same import as the
Phase 019 baseline.

## Changes

New files:
- `packs/bigville/world/llm_instructions.json`, `packs/test_hamlet/world/llm_instructions.json`: the new prompt tables.
- `packs/bigville/frames/speech_lexicon.json`, `packs/test_hamlet/frames/speech_lexicon.json`: the chatter and weather tables.
- `tests/test_phase018_llm_instructions.py`: 17 tests.
- `docs/phases/phase018/`: this report, `measure_prompt_size.py`, the before and after size outputs, the pytest logs,
  and the self-test and hamlet outputs.

Modified pack data (both packs):
- `world/major_actions.json`, `world/free_actions.json`: each action gained a `description` field. No other field changed.
- `pack.json`: manifest entries for the 6 prompt tables and 2 lexicon tables.

Code:
- `bigville/backends/prompts.py`: rewritten. `PromptBuilder(pack=...)`, `build_system_text`, `pack_hash`,
  `select_knowledge`, and `PromptRecord` (new fields `pack`, `pack_hash`).
- `bigville/game.py` (`_context` and one new method):
  - `_context`: the derived law and policy frames are appended to `known_laws` and `known_policies`.
  - `_derived_document_frames`: new method, placed before `_context`.
- `bigville/runtime.py` (`_realize_meaning` only): `_speech_lexicon` is new. `_realize_meaning` takes an optional
  `lexicon`. Its topic and weather branches read the lexicon.
- `domains/world_affordances.py`: binds `WORLD_PREMISE`, `PROMPT_BOUNDARY_RULES`, `PROMPT_CONTINUATION_RULES`,
  `PROMPT_RESPONSE_FIELDS`, `PROMPT_SELECTION`, `MEMORY_GIST`.
- `domains/shared_frames.py`: binds `SPEECH_CHATTER`, `SPEECH_WEATHER`.
- `domains/bigville_entities.py`: new `_check_prompt_instructions`, called from `check_consistency`.
- `tests/test_bigville_backends.py`: 3 schema assertions changed (see Test edits).

### Shared-file hunks (for staging)

`bigville/game.py`, mine:
- `_context`: the `known_laws`/`known_policies` block, with the new call to `_derived_document_frames`.
- `_derived_document_frames`: new method.

`bigville/game.py`, the other session's (not touched): the `record_action_outcome` block in `_apply_response`.

`bigville/runtime.py`, mine:
- `_speech_lexicon` (new), and the `_realize_meaning` signature, its multi-key recursion, and the topic and weather branches.

`bigville/runtime.py`, the other session's (not touched): the import block, `_checkpoint_encode`, `_checkpoint_decode`,
and the `BigvilleGraph` checkpoint methods.

`worlds/bigville_world.py`: not touched.

## Prompt structure

System text (about 3.4 KB, the same for every resident of a pack):
1. Premise: "You are one resident of {name}. {premise}" (`WORLD_PREMISE`).
2. Major actions, one line each with its description, in pack order (`MAJOR_ACTIONS`).
3. Free actions, one line each (`FREE_ACTIONS`).
4. Rules: `PROMPT_BOUNDARY_RULES`, then `PROMPT_CONTINUATION_RULES`.
5. The response fields (`PROMPT_RESPONSE_FIELDS`).

Record: `{schema, pack, pack_hash, system, context: {private, public}}`. The `public` part is the turn packet
(observations, `legal_affordances`, `recipient_interfaces`), unchanged in shape.

Private part:
- `identity`, `personality`, `backend`: unchanged.
- `knowledge.understood`: understood items (name, type, degree, and for places `location` and `position` or `landmark`).
  No `basis`, no `source`, no learned/period fields.
- `knowledge.aware`: aware-only items as `{item, type, name, gist}`.
- `memories`: non-derived memories (episodic, scenario law and policy notes, scenario recipe priors that the situation touches).
  Each keeps `memory_id`, `kind`, `turn`, and `content`. A text longer than `max_memory_text` is cut.
- `held_frames`: capped.
- `selection`: counts of held and shown memories, understood, aware, and frames.

## Memory selection rule and caps

The rule is documented in the `_doc` of the `PROMPT_SELECTION` table, and the caps are in the same table.

1. Standing understood knowledge: understood items whose type is in `standing_types` (law, policy, charter, concept,
   kin_term, office, procedure), plus non-derived law, policy, and reference notes. Sorted by type and name, up to
   `max_standing_understood` = 40.
2. Touched items. An item is touched when its name is a kind or item named by the affordances (kind, recipe, trade,
   item, good, target), a held item kind, an inventory key, a visible physical object kind, or a nearby resident's
   name. A place is also touched when its exact cell is within `place_radius` = 8 cells (Chebyshev) of the resident or
   of an affordance destination.
   - Understood touched items: up to `max_relevant_understood` = 30.
   - Aware-only touched items: name and gist only, up to `max_relevant_aware` = 20.
3. Recent non-derived memories (episodic and anything else): newest first, up to `max_recent_episodic` = 12. Each text
   is cut at `max_memory_text` = 400 characters.
4. Held frames: up to `max_held_frames` = 40.

The caps are authored design judgement (APPROX). They are not measured or sourced.

Gist text per item type is in `MEMORY_GIST`. The `basis` strings are never in the prompt. The test suite checks this.

## Prompt sizes (bytes), founders of the 100-resident town

Measured by `docs/phases/phase018/measure_prompt_size.py` (seed 305000, `BigvilleGame(..., autonomous=True)`,
`PromptBuilder().build(game._context(name))`, JSON as sent). Before: `prompt_size_before.txt`, measured on the tree
before this phase's edits. After: `prompt_size_after.txt`.

| Founder | Memories held | Prompt before | Prompt after | Private before | Private after | Public before | Public after |
|---|---|---|---|---|---|---|---|
| Adelina Gorse (index 0) | 339 | 153,772 | 42,082 | 125,752 | 6,625 | 27,104 | 31,852 |
| Ida Sedge (index 50) | 278 | 128,963 | 39,711 | 103,313 | 6,624 | 24,734 | 29,482 |
| Winifred Ottermole (index 99) | 436 | 186,632 | 35,538 | 160,461 | 6,033 | 25,255 | 25,900 |

The system text was 841 bytes before and is 3,391 bytes after.

The public part grew by 0.6 to 4.7 KB per founder (4.7 KB for the first two, 0.6 KB for the third). The growth is the derived laws and policies in `world_frames`.
Each understood law carries its spec and concepts, about 1 KB each. Nothing else in the public part changed.

## World_frames routing

`_derived_document_frames` reads the resident's own memories with `source == "derived"`, type `law` or `policy`:
- Understood (`understands > 0`) and the spec is in the world: the spec, with `aware: true` and `understands`. The
  spec's `knowledge` block is removed. It describes who understands the law, which is world mechanics.
- Aware-only: `{name, aware, understands: 0.0, gist}`. No spec.
- A law or policy that the explicit `law_knowledge` or `policy_knowledge` memory already carries is skipped.

Charters have no `world_frames` key, so an understood charter does not reach the context (see Limits).

The existing `law_knowledge` and `policy_knowledge` path is unchanged. It still copies the full spec, `knowledge`
block included. See Open questions.

## Chatter and weather

- `SPEECH_CHATTER`: `phrases` (keyed by trade), `work_template` (`There is always more work in {trade}.`), and `empty`.
- `SPEECH_WEATHER`: `phrases` (keyed by calendar weather), and `template` (`The weather is {weather} today.`).

The strings are the same as the old literals. The runtime reads them from the default `bigville` pack through
`_speech_lexicon`. `_realize_meaning(value, lexicon=...)` accepts another lexicon.

Hamlet has its own lexicon: `baker` only, with the same weather phrases.

## Pack tables added

World (`world/llm_instructions.json`):
- `WORLD_PREMISE`: `{name, premise}`. Bigville: "Bigville". Hamlet: "Test hamlet".
- `PROMPT_BOUNDARY_RULES`: 7 rules (validation, no invention, private memories are what is held, text plus raw,
  people not buildings, communication is free, waiting is valid).
- `PROMPT_CONTINUATION_RULES`: 2 rules.
- `PROMPT_RESPONSE_FIELDS`: the 5 keys `ActorResponse.from_dict` reads.
- `PROMPT_SELECTION`: `_doc`, `standing_types`, `place_radius`, the 5 caps, `max_held_frames` (see the rule above),
  and `max_memory_text`.
- `MEMORY_GIST`: one gist per item type, plus `default`.

Frames (`frames/speech_lexicon.json`): `SPEECH_CHATTER`, `SPEECH_WEATHER` (described above).

Descriptions: each `MAJOR_ACTIONS` and `FREE_ACTIONS` entry in both packs has a `description`. Two actions, `sell` and
`sell_labor`, say "Retired: the world refuses this action (it returns false)". That matches the boundary audit.

## Validation

| Check | Command | Result |
|---|---|---|
| Self-test | `python3 domains/bigville_entities.py` | exit 0; ERRORS (0), WARNINGS (0). `selftest_after.txt` |
| Hamlet | `python3 -m domains.check --pack test_hamlet` | exit 0; ERRORS (0), WARNINGS (0). `hamlet_after.txt` |
| Seeds | `python3 tools/generate_seeds.py --check` | exit 0; matches pack 'bigville' (22 files). Not regenerated: no generated seed reads the changed tables |
| Phase 018 tests | `pytest tests/test_phase018_llm_instructions.py` | 17 passed |
| Affected files together | `pytest tests/test_phase018_llm_instructions.py tests/test_bigville_backends.py tests/test_phase013a_packs.py tests/test_ported_features.py tests/test_phase019_knowledge.py` | 60 passed (17 of them new) |
| Full suite | `timeout 1500 python3 -m pytest -q -p no:cacheprovider` | 3 failed, 486 passed, 2 skipped. `pytest_after.txt` |
| Full suite, other session's failures deselected | same, with the 3 test IDs below deselected | 486 passed, 2 skipped, 3 deselected. `pytest_ignoring_other_session_ocelot.txt` |

The 3 failures, verbatim from the run (all are the other session's; the same import error is on the Phase 019 baseline):
```
FAILED tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities
FAILED tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control
FAILED tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action
E   ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'
```

The export byte test (`test_export_rerun_is_byte_identical`) passes. The JSON files were written in the exporter's format.

The 100-resident village run (`run_village`) was not run; the brief did not ask for it.

## Test edits

`tests/test_bigville_backends.py`: three `"bigville/prompt/1"` assertions became `"bigville/prompt/2"`
(lines 18, 28, 37). They assert the schema string, which changed because the private part changed. No other
assertion changed. The file is not in the other session's list.

No other existing test was edited. The 17 new tests are in `tests/test_phase018_llm_instructions.py`.

Existing tests that cover the changed behaviour and still pass without edits: `test_unread_laws_and_policies_are_not_implicit_actor_knowledge`
(`tests/test_bigville_game_api.py`), and the chatter and weather assertions in `tests/test_ported_features.py` (lines 95 and 107).

## Limits

- The selection is a fixed rule and fixed caps, chosen by the author. It was not tuned against a played village.
- The public part grows with understood laws and policies (see Prompt sizes). It is not capped. A town with more
  law items would grow it further.
- `PromptBuilder` defaults to the `bigville` pack. An LLM backend on another pack must pass `PromptBuilder(pack=...)`.
  Nothing in `BigvilleGame` does that today.
- Speech (`_realize_meaning`) reads the `bigville` lexicon unless a caller passes one. A world on another pack gets
  the bigville phrases.
- Charters: a derived charter understanding does not reach `world_frames` (there is no charter frame in `_context`).
- `SPEECH_CHATTER` has a phrase for `carpenter`, which is not a trade in this pack. The self-test reports it as info,
  and the phrase is never used. It was kept so the output does not change.
- Hamlet's chatter is `baker` only. The hamlet's weather phrases are the bigville phrases.
- The `knowledge` block removal applies to derived law entries only.
- `MEMORY_GIST` gives one gist per type. It is not per item.
- The prompt is built from `ActorContext`. It does not read the world directly.

## Deviations

1. The schema moved from `bigville/prompt/1` to `bigville/prompt/2` because the private part changed. Three test
   assertions were updated (see Test edits).
2. The private part gained `knowledge` and `selection` keys. The `memories` key keeps its name and shape for non-derived memories.
3. The brief asked for `world_frames` routing. It did not ask for the public part to stay the same size. It grew by 0.6
   to 4.7 KB per founder, and the size is reported above.
4. The brief said to put the prompt tables in the pack. The tables are in new files, `world/llm_instructions.json`
   and `frames/speech_lexicon.json`, and bound in `world_affordances.py` and `shared_frames.py`. Those are the
   two modules that already bind world and frame data.
5. The continuation rules are a separate table from the boundary rules, so each list stays short. The brief named boundary rules only.

## Open questions

1. Should the existing `law_knowledge` and `policy_knowledge` path also drop the `knowledge` block? That path still
   copies the full spec, including the rule for who understands the law. Removing it is a one-line change, but it is
   outside this phase's brief.
2. Should `_context` route understood charters? That needs a charter key in `world_frames` and a decision on whether
   a charter's text is shown.
3. Should the public part be capped? The derived law specs are the main growth.
4. Should `PromptBuilder` take the pack from the world, rather than the caller?

## Follow-ups

For Phase 031 (register the LLM backend):
- Phase 031 must validate provider output against a response schema. `PromptRecord` carries no `requested_output_schema`
  yet. The plan (`docs/AGENT_BACKENDS_PLAN.md`, section 2) asks for one. Phase 031 needs it, and it can be derived from
  `PROMPT_RESPONSE_FIELDS`.
- The repair prompt (validation errors only) and the idle response need no pack change. The prompt record already
  carries `pack_hash` and `schema`, which Phase 031's failure counts can record.
- The turn packet has no last-outcome field. Phase 021 (result feedback) adds it. Phase 031 depends on 021, as its
  brief states.
- The plan's `format="json"` and redacted audit view are not built.
- `PromptBuilder` needs a pack argument from the world, or Phase 031's `create_game` must pass it.

For later phases:
- The cap values are APPROX. Tune them against recorded turns, not from this measurement.
- `bigville/backends/prompts.py` reads `knowledge` memories by `type`. If Phase 019's derived content changes its keys,
  the selection changes with it.

## Working tree

Start (`git status --short`): the other session's modified files (README.md, bigville/backends/ocelot.py,
bigville/game.py, bigville/runtime.py, bigville/seeds/bigville_actor_decision.json, docs/AGENT_BACKENDS_PLAN.md,
docs/FEATURE_PHASES.md, tests/test_bigville_game_api.py, tests/test_bigville_scenarios.py, worlds/bigville_world.py) and
its untracked files.

End: the same files, plus this phase's changes listed above. Nothing was committed, staged, stashed, reverted, or
reformatted. `docs/FEATURE_PHASES.md` and the other session's tests were not edited.
