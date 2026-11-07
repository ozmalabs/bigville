# Fix simple village: founding ties on, and no proposals from a body that is down

## Summary

1. **Founding relationship seeding is on for the bigville pack.** A bare town100 (seed 305000) holds 845 directed
   ties. Seeding changes no simple-backend action, utterance or hunger value over 60 or 200 turns (checked per
   resident). Four existing tests asserted an empty town and now assert the founding ties.
2. **A resident who is asleep, passed out or collapsed now gets no proposal.** The premise did not reproduce as
   written. The Phase 056 figure of 305 `collapsed` refusals in 60 turns cannot be rebuilt from any commit, and the
   current tree gives 0 `collapsed` refusals in 60 turns. Over 200 turns it gives 15, all from a stored walk that the
   game replayed while the resident was down. The fix stops those replays. After it, `collapsed` refusals are 0 in
   200 turns, and `exhausted` refusals (Phase 049, kept) are unchanged at 1397.

Self-tests: bigville ERRORS (0), WARNINGS (0); test_hamlet ERRORS (0), WARNINGS (0).
Full suite on the final tree: 8 failed, 1758 passed, 3 skipped. The 8 failures are 3 Ocelot adapter tests (known),
4 TUI HTTP tests that also fail with seeding off on the live tree (another session's edits), and 1 test that failed
once from another session's in-progress edit and passes on re-run. See Validation.

## Changes

### Files

- `packs/bigville/world/persona.json` (only the two lines below changed; regenerated through
  `tools/export_pack.py --pack bigville --out /tmp/...`, and the exporter output is byte-identical to the file).
- `bigville/game.py` (shared, other sessions' edits present): one interrupt, 4 lines.
- `bigville/backends/cheap.py` (shared, other sessions' edits present): the move continuation, 3 lines.
- `tests/test_bigville_disposition_seed.py`, `tests/test_bigville_reporting.py`,
  `tests/test_bigville_topic_style_migrated.py`: the four tests listed under Tests changed.
- `tests/test_fix_simple_village.py` (new, 8 tests).
- `docs/phases/fix_simple_village/`: this report, measurement scripts and their outputs.

`packs/test_hamlet/world/persona.json` is unchanged: `enabled` stays false. Its self-test passes (ERRORS 0,
WARNINGS 0). `packs/bigville/pack.json` is not changed by me.

### Hunks (for rebuilding from HEAD)

1. `packs/bigville/world/persona.json`, `RELATIONSHIP_SEEDING`:
   - `_doc`: the sentence "The bigville default is false: four existing tests assert a town with no held ties ..."
     is now "The bigville default is true: the founding town holds its ties (845 directed records at seed 305000,
     Phase 058), and the tests that assumed a town with no ties now assert them (Phase fix_simple_village). The
     test_hamlet pack has no founding town and keeps it false." The sentence after it, "The stream and the
     thresholds are model choices.", is kept once.
   - `"enabled": false,` becomes `"enabled": true,`. Anchor: the line `"stream": 9058,` follows it.
2. `bigville/game.py`, `BigvilleGame._continuation_interrupt`. Inserted after the line
   `        interrupt_on = set(request.interrupt_on)` (preceded by `            return "poll_each_turn"`, followed by
   `        expected = set(request.expected_events)`):
   ```python
           # fix_simple_village: a continuation that names body_down stops once the resident is asleep, collapsed or
           # passed out. The backend then decides, and the world publishes no affordances to a down body.
           if "body_down" in interrupt_on and self.world._sleep_code(actor) is not None:
               return "body_down"
   ```
3. `bigville/backends/cheap.py`, `DeterministicBackend.decide`, the move continuation. The line
   `            continuation = ActorContinuation(destination=choice["destination"])` is replaced (preceded by the comment
   line `            # encounters, needs thresholds, and failed movement interrupt it.`, followed by
   `        return ActorResponse(`):
   ```python
               # fix_simple_village: body_down ends the walk when the resident falls asleep, collapses or passes out.
               continuation = ActorContinuation(destination=choice["destination"],
                                                interrupt_on=ActorContinuation.interrupt_on + ("body_down",))
   ```

No world file, no Ocelot file, and no refusal code changed. `ActorContinuation`'s default interrupts are unchanged,
so only the simple backend's walks name `body_down`.

### Why the change is in game.py

A walk is a continuation. `game.step()` replays a stored move without calling the backend while no interrupt
fires (`bigville/game.py`, `step`). The backend's `decide` therefore never sees a down resident on a replayed walk.
The affordances are already empty for a down resident (`actor_affordances` returns `[]` for an asleep, collapsed or
passed-out body), so `decide` already proposes nothing on its own turns. The only route to a proposal was the
replay, and an interrupt is the one hook the backend can reach. The observation dict has no body-state field, so
the backend cannot read the state from its context.

### Speech

`World.speak` does not check the body, so a down resident can still speak. The simple backend's speech path
(`_speech`) runs on blank turns too, as before. The speech behaviour is unchanged.

## Tests changed

Each change asserts the new truth and keeps the test's other intent. No assertion was deleted without a replacement.

| test | before | after | reason |
|---|---|---|---|
| `test_bigville_disposition_seed.py::test_seed_generated_relationships_not_auto_wired_into_from_town100` | `world._relationships == {}` | `len == 845` and every bond has `seeded == 1.0` | Founding ties are on by default. The intent (the workplace ring is not auto-wired) is kept: a bare town holds only founding ties. |
| `test_bigville_reporting.py::test_report_covers_physical_economy_and_recorded_social_activity` | `directed_bonds == 1` | `directed_bonds == founding + 1`, `founding = len(_relationships)` before the test's own tie | The report counts every bond on record, so the 845 founding ties count too. |
| `test_bigville_topic_style_migrated.py::test_a_bare_from_town100_still_seeds_zero_relationships` | renamed to `test_a_bare_from_town100_holds_the_founding_ties_by_kind`; `len == 0` | `len == 845` and kinds `{blood_kin 258, spouse 10, friend 200, neighbour 200, workmate 160, feud 17}` | Seeding on by default. Counts are the Phase 058 seed-305000 counts, re-measured here. |
| `test_bigville_topic_style_migrated.py::test_town100_workplace_relationships_are_sparse_not_all_pairs` | "at most 2 outgoing" over every bond | same assertion, over only the bonds this call wrote (bond identity changed) | The founding ties would add outgoing bonds to a resident and break the ring's bound. The ring's own bound is what the test checks. |

Not changed: every other existing test passes with seeding on (see Validation). The four listed were the only
tests that moved from the seeding switch on the live tree.

## Validation

All commands run in `/home/matt/ozmadev/bigville` unless stated. The live tree held other sessions' edits.

- `python3 domains/bigville_entities.py`: exit 0, `ERRORS (0)`, `WARNINGS (0)`. Info: `RELATIONSHIP_SEEDING ... enabled=True`.
- `python3 -m domains.check --pack test_hamlet`: exit 0, `ERRORS (0)`, `WARNINGS (0)`.
- `python3 tools/export_pack.py --pack bigville --out /tmp/fix_export`: `normalised 239 tables`; `persona.json` byte-identical to the edited file.
- Full suite, clean `git archive HEAD` copy (`/tmp/fix_head`, seeding off, no body_down): **1695 passed, 2 skipped, 0 failed** (23:42). The three Ocelot tests are not in HEAD's test tree.
- Full suite, live tree, seeding on, before the item 2 edits and before the test edits (`pytest_live_seed_on_before_tests.log`): 11 failed, 1747 passed, 3 skipped. Failures: the 3 Ocelot tests, the 4 named seeding tests, and 4 `test_phase057_tui.py` tests.
- Attribution of the 4 TUI tests:
  - live copy with HEAD's persona (seeding off) (`/tmp/live_seedoff`): the same 4 fail, so seeding does not cause them;
  - HEAD copy with seeding on (`/tmp/fix_head_seed`): all 48 pass, so they need the live tree's other edits (`bigville/server.py` and `bigville/game.py` have uncommitted changes from other sessions).
  - They are reported, not fixed.
- Full suite, final live tree (`pytest_live_final.log`, 26:38): **8 failed, 1758 passed, 3 skipped**. Failures:
  - 3 Ocelot tests (`No module named worlds.bigville_ocelot_adapter`), known;
  - 4 TUI tests, as above;
  - `tests/test_phase021_refusals.py::test_every_reason_code_the_world_uses_is_in_the_pack_table`: the world file's `_refuse` codes `holding`, `restrained`, `pinned`, `not_holding`, `not_restrained` were not yet in `refusal_reasons.json` when the run read them (another session's restraint edit). The file passes now (`20 passed`). None of my hunks adds a refusal code (`git diff` of my hunks: 0 `_refuse` lines).
- `tests/test_fix_simple_village.py`: 8 passed on the live tree (2 min 49 s). On the seed-only copy (HEAD plus the persona file, without the body_down hunks): the 3 down-state tests fail (`asleep`, `passed_out`, `collapsed`), and the founding, awake, default-interrupt and exhausted tests pass.
- `tests/test_bigville_disposition_seed.py`, `test_bigville_reporting.py`, `test_bigville_topic_style_migrated.py`, `test_phase058_persona.py`: 76 passed (after the test edits, before item 2).

### Behaviour: simple backend, town100, seed 305000, `PYTHONHASHSEED=0`

Sources: `behaviour_*.json` from `docs/phases/phase058/measure_behaviour.py`, and `probe_*.json` from `probe_refusals.py`.
"before" is the live tree before any edit of this report (seeding off). "seed only" is HEAD plus the persona file.
"after" is the final tree (seeding on and body_down).

**Seeding (Phase 058 claim, verified again):**

| run | arm | action counts | utterances | deaths | hunger mean at end | ties on record | residents whose action digest differs from before |
|---|---|---|---|---|---|---|---|
| 60 turns | before | eat 5, move 3526, none 1065, rest 1334, sleep 55, work 15 | 285 | 0 | 0.4442 | 0 | - |
| 60 turns | seed only | same | 285 | 0 | 0.4442 | 845 | 0 of 100 |
| 60 turns | after | same | 285 | 0 | 0.4442 | 845 | 0 of 100 |
| 200 turns | before | eat 276, fetch 279, move 8202, none 7748, rest 3204, sleep 276, work 15 | 1220 | 0 | 1.6110 | 0 | - |
| 200 turns | seed only | same | 1220 | 0 | 1.6110 | 845 | 0 of 100 |
| 200 turns | after | move 8187 (-15), none 7763 (+15), others same | 1222 (+2) | 0 | 1.6110 | 845 | 15 of 100 |

Phase 058's 200-turn numbers (97 deaths, hunger 0.8893, `move` 4904) do not reproduce on this tree. Other sessions'
and phases' changes since Phase 058 changed the simple village (0 deaths now). The comparison here is within the
current tree only.

**Refusals by reason (`probe_refusals.py`, per resident, read before and after each turn):**

| run | turns | refusals by reason | total | collapsed refusals, source |
|---|---|---|---|---|
| before (live = HEAD) | 60 | exhausted 528 | 528 | none |
| after | 60 | exhausted 528 | 528 | none |
| before (live = HEAD) | 200 | collapsed 15, exhausted 1397 | 1412 | all 15 from a replayed continuation |
| seed only | 200 | collapsed 15, exhausted 1397 | 1412 | all 15 from a replayed continuation |
| after | 200 | exhausted 1397 | 1397 | none |

The `exhausted` refusals are replays of a stored walk below e_low, which Phase 049 keeps. Their count is unchanged.
Over the 200 turns, 7799 resident-turns were asleep, collapsed or passed out (at most 65 at once), and 165 of them
were collapsed. In the 60-turn run, 1106 resident-turns were down and none were collapsed.

**Scenario check (`scenario_*.json`):** a resident holding a stored walk, set asleep before the next turn, gets a
refused `asleep` move on HEAD. On the live tree the same resident gets `interrupted: body_down`, no action and no
refusal. For `passed_out` and `collapsed`, HEAD records no refusal, and the replayed move is reported as applied. I did not
trace why (`docs/phases/fix_simple_village/scenario_head_stored_walk.json`).

### Ties after founding

From `tie_counts.py` (seed 305000, bare `from_town100`, switch on):

| kind | directed records |
|---|---|
| blood_kin | 258 |
| spouse | 10 |
| household (kind; housemates who were not kin) | 0 |
| friend | 200 |
| neighbour | 200 |
| workmate | 160 |
| feud | 17 |
| **total** | **845** |

- 206 records carry the `household` flag: 196 blood-kin and 10 spouse records. Phase 058's report text said 196, which
  counts blood-kin records only.
- 542 records are reciprocated (the other direction is also on record).
- Per resident, total ties: min 4, median 8, max 16. None has zero.
- Per resident, close ties (spouse, blood_kin, household, friend, feud): min 2, median 5, max 12.

### Workplace ring overlap (not called by the founding path)

`seed_workplace_relationships()` on a founding town mints 62 pairs (117 new directed keys) and overwrites 7 founding
bonds (directed keys that already held a founding tie). Only a test calls it.

## Limits

- The 305 figure is not reproduced. The Phase 056 commit (`56fb413`) run through the same `run_arm` gives 528
  `too_tired` refusals and digest `752cd821…`. The Phase 056 record has digest `056f43…` and 305 `collapsed`. The
  record came from a tree state I cannot rebuild from commits (`learning_eval_arm_check.json`).
- The 200-turn runs took about 8.5 minutes each under load. They are single runs with one seed.
- The body_down fix closes the decision-time case (a resident down when the walk is decided). A resident who collapses
  during the same turn's tick, after the decision, still has the stored walk applied once and refused `collapsed`. Not
  observed in the 200-turn run after the fix. The apply-time guard would be another hunk in `game.py`.
- `tests/test_fix_simple_village.py`'s 60-turn test takes about 2.5 minutes.
- I did not run the 100-resident village for longer than 200 turns.
- Phase numbers in old reports (`docs/phases/phase058`, `phase056`) are history and are not rewritten.

## Open questions

1. **Shared-file hunks.** The body_down hunks in `bigville/game.py` and `bigville/backends/cheap.py` touch files
   other sessions edit. Confirm they are kept, or choose the apply-time guard as well (see Limits).
2. **Speech by a down resident.** The world allows it, so blank turns can still speak (+2 utterances in 200 turns).
   Keep, or block speech while down?
3. **Workplace ring.** The opt-in `seed_workplace_relationships` overwrites 7 founding bonds. The fix belongs in
   `worlds/bigville_world.py`, which I was not allowed to edit. Should the ring skip reverse keys already on record?
4. **Phase 056 figure.** Should the Phase 056 report be annotated that its 305 `collapsed` count could not be
   reproduced from `56fb413` or from HEAD?
5. **Exhausted refusals.** They are now the only refusal class in the simple village (528 per 60 turns, 1397 per 200).
   Phase 049 keeps them on purpose. Say if you want them handled too.
