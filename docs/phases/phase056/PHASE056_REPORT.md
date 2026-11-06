# Phase 056: evaluation, how well residents learn the world

## Summary

`bigville/learning_eval.py` reads a run's records and writes per-resident curves and summaries: refusals by reason,
failures, repeat-mistake rate, tries before switching, improvised and wrong-tool attempts, accidents, tool breakages,
strain, lessons recorded and later used, survival, food, work, and social ties. It also runs the leak guard over every
prompt in a run, and it runs the learner and non-learner controls. `tools/run_learning_eval.py` writes the JSON record
and a Markdown report.

The control result separates the two fakes as the brief asks. The learner's repeat-mistake rate is 0.000. The
non-learner's is 0.967 over 30 turns.

Only scripted fake providers were used. No network was used, `.env` was not read, and nothing was committed. No shared
file was edited. The simple backend's 60-turn town100 run matches a clean `git archive HEAD` run on all 14 compared
fields.

Known limits, detailed below: the Ocelot arm is skipped because its adapter is not importable here. No real model was run.
Accidents and tool breakages did not occur in the 60-turn runs, so those metrics are zero and untested in practice.
Per-resident improvised-work counts do not exist in the world, so they are not reported.

## Changes

### Created

- `bigville/learning_eval.py`. Metrics, the recorder, the leak guard, the control providers, the arms, the controls,
  the marginal effect, `render_markdown`, `write_json` and `run_evaluation`.
  - `ScriptedLearner`. It reads `public.last` (merging delta packets so that a repeated, identical refusal still counts).
    After one refused raw action it retries once with another target. After that it switches to the first option in
    `public.can` whose handle has not failed. Each switch comes with a lesson in `memory_updates`.
  - `ScriptedNonLearner`. It sends the same raw action (`lift`, target `1`) every consult and ignores `public.last`.
  - `guard_log` and `guard_message`. The Phase 052 rules applied to each system and user message in a Phase 066 log.
    Assistant replies are not checked.
- `tools/run_learning_eval.py`. Runs the evaluation, or with `--render-only` rebuilds the Markdown from a saved JSON.
- `tests/test_phase056_learning_eval.py`. 8 tests (listed under Validation).
- `docs/phases/phase056/`:
  - `PHASE056_REPORT.md` (this file).
  - `evaluation/learning_eval.json` and `evaluation/LEARNING_EVAL.md`, the output of the 60-turn run.
  - `evaluation/logs/`: the Phase 066 logs of the control and LLM arms (gzip, 1.4 MB in total). The guard read these.
  - `run_learning_eval.log`, `selftest_bigville.txt`, `selftest_test_hamlet.txt`, `full_suite.log`.
  - `failed_ids_live.txt` and `failed_ids_final.txt`: the failing test IDs of the two full-suite runs (see Validation).
  - `behaviour_head.json` and `behaviour_mine.json`: the simple-backend identity check.

### Shared files

None. `bigville/reporting.py`, `bigville/game.py`, `bigville/backends/*`, `worlds/*`, `domains/*` and the packs are
unchanged by this phase. The brief allowed a small hook in `reporting.py`, but the evaluator reads the world and the
logs directly, so no hook was needed.

### Definitions

- Proposal key: `[verb, target, tool]`. The verb is the action name, or the `verb` parameter for `attempt`. The target is
  the first of `target`, `recipe`, `kind`, `animal`, `sow_kind` or `destination` that is set. The tool is `tool` or `with`.
- Learning failure: a proposal that did not apply, or an attempt whose outcome was `no_progress` or `stuck`.
  A refusal for the body (`asleep`, `collapsed`, `passed_out`) is a body-state refusal. It is counted in the refusals,
  but it is not a learning failure, because the resident cannot change it by learning.
- Repeat-mistake rate: learning failures whose key had failed before for the same resident, over all learning failures.
- Tries before switch: the number of failures under one key before the resident proposed a different key or a proposal
  that did not fail. An episode still open at the end is censored, and reported with the tries it had.
- Improvised attempt: an attempt with bare hands (the world records the tool as `""`). Wrong-tool attempt: the proposal
  named a tool and the world used another. Accidents are the `harm(..., "accident")` calls, counted by wrapping
  `world.harm` on the evaluator's instance. Breakages are tools that turned broken, attributed to the resident who holds
  them, and counted as unattributed when no one holds them.
- Lesson recorded: a `lesson` memory update. Offered: its text is sent to the model in a later message of that resident.
  Used: it was offered, and the resident's first decision from the offer turn onward has a different key from the key
  the lesson is about.
- Deviation rate (LLM residents): replies that departed from the autopilot's would-be choice, over accepted replies.

### Sample: learner against non-learner (30 turns, three residents, every turn a consult, no call cap)

From `evaluation/LEARNING_EVAL.md`:

| metric | learner | non-learner |
| --- | --- | --- |
| learning failures | 6 | 90 |
| repeat failures | 0 | 87 |
| repeat-mistake rate | 0.000 | 0.967 |
| refusals | 6 | 90 |
| tries before switch (mean) | 1.000 | n/a |
| censored episodes (never switched) | 0 | 3 |
| lessons recorded | 6 | 0 |
| void | no | no |

The learner's lessons, as the model wrote them through the scripted reply, were: "The action did not happen with one
target. I try another target before I give up on the action." and "That did not happen, so I choose one of the options the
world lists instead." Each was offered in the next consult's packet (`offered` 2, `used` 2 per resident).

### Sample: backends on town100, seed 305000, 60 turns

| arm | kind | void | survived (subjects) | learning failures | repeat-mistake rate | deviation rate | work (subjects) | body-state refusals (subjects) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simple | simple | no | 3/3 | 0 | n/a | n/a | 1 | 9 |
| scripted_learner | llm | no | 3/3 | 6 | 0.000 | 0.294 | 0 | 9 |
| scripted_nonlearner | llm | no | 3/3 | 36 | 0.917 | 1.000 | 1 | 6 |
| ocelot | ocelot | skipped (`ModuleNotFoundError: worlds.bigville_ocelot_adapter`) | | | | | | |

The three subjects are the first three names in sorted order: Adelina Gorse, Adelina Norbisham and Adelina Sputterfield.

Pack hash `6f8a636fef373804b3ee3e87fae524c3e47e9554bfd737b9934bd4dc257e1ac5`, prompt schema `bigville/prompt/3`. Both
are written into the report header.

## Validation

All commands run in `/home/matt/ozmadev/bigville`. The live tree is shared, and other sessions' uncommitted work was
present throughout (`git status --short` listed 43 entries at the end, and this phase's new files are among them).

- `python3 domains/bigville_entities.py`: exit 0, `ERRORS (0)`, `WARNINGS (0)`. Output `selftest_bigville.txt`.
- `python3 -m domains.check --pack test_hamlet`: exit 0, `ERRORS (0)`, `WARNINGS (0)`. Output `selftest_test_hamlet.txt`.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase056_learning_eval.py`: **8 passed**. The tests are:
  - the learner's repeat-mistake rate is 0 and the non-learner's is above 0.5, with the learner's lessons used;
  - the control metrics are deterministic (same digest and residents on a second run);
  - a simple run is deterministic and records no lessons;
  - the scripted learner reacts to a refusal in `public.last`, with a target change, then a switch, and a lesson each time;
  - the scripted non-learner sends the same action whatever it is told;
  - the guard voids a run whose prompt holds a referee-only key, and passes one whose only number is in the model's reply;
  - the guard flags a raw number, and allows the packet's own counts;
  - the report header names the scenario, seed, pack hash and prompt schema.
- `python3 tools/run_learning_eval.py` (defaults: town100, seed 305000, 60 turns, control 30 turns, three LLM residents):
  exit 0, no void arm. Output `run_learning_eval.log`, `evaluation/`. The digest of the record is
  `14c509706f10b2b5233e981ae7e6bfa12d0a3f5904fdc12702781a19da94a6fb`. The guard checked 853 + 946 prompts in the controls
  and 209 + 270 in the comparison arms, with 0 violations. The run took about 10 minutes.
- Simple backend identity, `PYTHONHASHSEED=0 python3 docs/phases/phase058/measure_behaviour.py --turns 60` (town100, seed
  305000): a clean `git archive HEAD` copy and the same copy with this phase's three new files added. All 14 fields are
  identical: action counts `eat` 5, `move` 3526, `none` 1065, `rest` 1334, `sleep` 55, `work` 15; 285 utterances; 0 deaths;
  hunger mean at turn 60 0.4442; the per-resident digests. Files `behaviour_head.json`, `behaviour_mine.json`.
  Nothing in the simulation imports the new modules, so this is expected.
- Full suite, live tree, `timeout 2700 python3 -m pytest -q -p no:cacheprovider` (`full_suite.log`, 1122 s): **56 failed,
  1604 passed, 3 skipped.**
  - 3 failures are the Ocelot adapter tests (`ModuleNotFoundError: worlds.bigville_ocelot_adapter`), the known ones.
  - 53 failures are in other tests (food, decay, animals, crops, simple life, and the migrated and persona tests). They are
    not in this phase's files. On a clean `git archive HEAD` copy, all 53 pass (`53 passed`, 128 s). They are caused by the
    other sessions' uncommitted edits to the shared world, not by this phase.
  - An earlier full run on the same tree (before the body-state and lesson-ordering fixes, same new files) gave 105
    failed, 1555 passed, 3 skipped. Its 102 non-Ocelot failures also passed on clean HEAD (`102 passed`), and they also
    passed on HEAD with this phase's files added (`102 passed`). The failing set changed between the two runs, which
    shows the live tree was changing during this session.
  - The four Phase 057 TUI HTTP tests (`test_phase057_tui.py`) failed in both live runs. They are among the 53, and
    they pass on clean HEAD.

## Limits

- **No real model.** The learner and non-learner are scripted fakes. Their behaviour shows that the metrics separate a
  learner from a non-learner. It says nothing about any real model's learning.
- **Ocelot skipped.** `bigville/backends/ocelot.py` cannot import `worlds.bigville_ocelot_adapter` in this checkout. The
  arm is reported as skipped with that reason, not run.
- **Short horizon.** The comparison runs 60 turns, and the controls 30. Survival is 3 of 3 in every arm, and food at the end
  is 0 for the subjects in every arm. Ties are 0 because relationship seeding is off (Phase 058). The outcome
  comparison is therefore not informative at this length.
- **Tools and accidents not exercised.** No tool broke and no accident happened in any 60-turn run, so the accident and
  breakage metrics are all zero. They are implemented but not tested by a run that produces them.
- **Improvised jobs.** The world keeps only a town-wide tally (`tool_tally`: `improvised_jobs`, `accidents`,
  `broken_tools`). Work done with bare hands per resident is not in the records, so `improvised_attempts` covers attempts
  only. Wrong-tool counts cover attempts only.
- **Body-state refusals.** `collapsed` refusals are most of the refusals in the simple arm (305 in 60 turns, all 100
  residents, see the whole-town table in `LEARNING_EVAL.md`). The simple backend keeps proposing actions while a resident
  is collapsed, and the world refuses each one. These are kept out of the learning failures, and the report shows them
  separately. This looks like a simple-backend issue for Tract B, and I did not change it.
- **Repeat-mistake rate mixes autopilot and model turns.** In the autopilot arms, a resident's failures on turns the
  autopilot decided count too, so the arm rates (0.000 and 0.917) are not the model's alone. The control table, where
  every turn is a consult, is the clean comparison.
- **Lesson use is measured from text.** A lesson is "offered" when its text appears in a later message of that resident.
  "Used" compares the next decision after the offer with the failed key. This does not show that the model reasoned from
  the lesson.
- **Deviation is against the autopilot.** The would-be choice is the simple backend's action for that turn. A deviation
  rate of 0.294 means the learner's replies differed from the simple backend's choice on that share of consulted turns.
  It does not measure the quality of either choice.
- **Delta packets hide a repeated refusal.** A delta packet shows `last` only when it changes. A second identical refusal
  therefore produces no change. The learner handles this by keeping the last value it was shown. A model that reads only
  the new text would not see a repeated refusal at all. See open question 1.
- **Leak guard covers prompts only.** It checks the system and user messages in the log. It does not check the agent view
  (Phase 052's test does that), nor the model's replies.
- **The guard's digit rule** exempts handles, `lessons`, `notes`, `kept`, `lead`, `pack_hash` and `system`, because they
  carry the resident's own words or the handles. Packet numbers are exempt only under `sizes` and `omitted`.
- **Digest.** The digest is the SHA-256 of each arm's per-turn proposals and results. The record digest covers the metric
  content, not file paths or provenance.

## Open questions

1. **Delta packets and repeated refusals.** Should a repeated refusal be shown as a new outcome, for example with a turn
   number in `last`? Right now an identical refusal is invisible in a delta, and a model that reads only the delta would
   repeat itself. The fix is in the packet (Phase 054 and 066), not here.
2. **Body-state proposals.** Should the simple backend stop proposing actions while the resident is collapsed? In these
   runs that removes 305 refusals in 60 turns (Tract B's file).
3. **Per-resident improvised work.** Should the world record, per resident, jobs run without their named tool (Phase 048
   follow-up)? The evaluator can only count attempts per resident.
4. **Horizon.** Is 60 turns the length for the outcome comparison, or should the marginal-effect run use a longer horizon
   (for example one period of 100 turns, or several days)? Longer runs cost about 1.6 s per turn for town100, plus the
   model calls.
5. **Ocelot arm.** Should the Ocelot arm run in a checkout that has the adapter? The current skip is recorded and explained.
6. **Lessons.** Is text-based "offered" good enough, or should the packet record which lessons it included, so that
   "offered" is exact?
7. **Phase 068 decision.** Phase 068 (graph memory) waits for this data. The measures this phase gives are: the
   repeat-mistake rate of a model arm, lessons used, and the tries before switching. The real-model run that would make
   those comparisons is not done, so the decision rule cannot be applied yet.

## Steering

The steering message asked for planning of phases on speech, perception, the LLM harness and the TUI. None of that is in
this phase's scope: `docs/FEATURE_PHASES.md` is outside this phase's write scope, and I did not edit it. Programme E already
has briefs for those items (Phases 060 to 065, 066, 067 and 068). Phase 066 (the harness, session and complete log) is
already done, and this phase's learner and guard use its log. The message's questions about speech and perception are
open for the supervisor to plan (Phases 060 to 065).
