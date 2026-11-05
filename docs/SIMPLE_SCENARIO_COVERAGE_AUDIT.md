# Independent scenario coverage audit: packages 5–16

Reviewed the current working tree against `SIMPLE_VILLAGE_TEST_PLAN.md`, the
package findings, scenario JSON, and the focused tests. I also ran a bounded
verification subset (not the full suite):

```sh
PYTHONPATH=. pytest -q tests/test_simple_animals.py \
  tests/test_simple_storage_decay_construction.py \
  tests/test_simple_work_food_exchange.py \
  tests/test_package15_resource_social_stress.py \
  tests/test_simple_room_policy.py
```

Current result: **15 passed in 1.91s**. This verifies the focused current
package 9, 10, 14, 15 and 16 tests only. It does not validate the full suite or
all gates below.

## Prioritized findings

### P0 — Correct stale package result notes before using them as gate evidence

Several notes describe tests and behavior that do not match the checked-in
current tests:

* `SIMPLE_VILLAGE_PACKAGE_9_FINDINGS.md` says Daisy chooses `graze`, grass falls
  from 8 to 0, and hunger stays at zero. `tests/test_simple_animals.py` now
  asserts `stay`, unchanged grass, and hunger rising to 2; the package note's
  narrative is contradicted by the test and by `SIMPLE_BOUNDARY_REMAINING.md`.
  The current animal test passes in the focused run above.
* `SIMPLE_VILLAGE_PACKAGE_10_FINDINGS.md` calls construction an intentionally
  failing test and predicts 3 passed/1 failed, fractional input consumption,
  and `False` intermediate actions. The current test asserts 10 successful
  build turns, progress 1–10, and exact exhaustion of the declared inputs. Its
  current focused test passes. Reproduce with the package 10 command below.
* `SIMPLE_VILLAGE_PACKAGE_15_FINDINGS.md` says package 14 currently has two
  failures, including an expected grain-stock decrease of 4 and no-carrier
  stock of 8. The checked-in `tests/test_simple_work_food_exchange.py` instead
  asserts grain-stock decrease 7 and no-carrier grain stock 8 only in the
  separate control; the regular scenario's final grain stock is 1. Both package
  14 tests pass in the focused run above. Update the stale dependency/failure
  claims and rerun the package command before citing them.

These are documentation/evidence integrity defects rather than currently
reproduced red tests. Do not treat old result tables as proof of current code.

### P1 — Package 14 is a manually staged workflow, not independent role cognition

The real-turn trace and mass accounting are useful, but `_RoleChoice` in
`tests/test_simple_work_food_exchange.py` encodes the full ordered workflow:
role-specific action priorities, delivery flags, a bread-carry phase, and
runtime mutation of carrier profile settings. The carrier changes its allowed
fetch kinds and travel setting based on its own previous scripted choices.
This is permitted as a narrow stateful fixture hook by the plan, but it does
not show that agents infer role, provenance, or goals from ordinary observation
and then coordinate. Phrase the result as a successful scripted backend-policy
integration trace. If package 14 is used to satisfy a cognition/coordination
claim, add a separately gated variant where role goals are declared in the
profile, no test hook advances hidden phases, and decisions are made from
observed state/affordances; preserve the existing negative input/participant
control.

Reproduce current gate:

```sh
PYTHONPATH=. pytest -q tests/test_simple_work_food_exchange.py
```

### P1 — Package 9 in-game feeding gap (closed in current checkout)

The original animal caregiver game-turn test has Daisy stay, consume no grass,
and gain hunger; previously the explicit `eat` test called `world.animal_tick()`
directly. The current checkout adds
`test_game_turn_animal_backend_eats_located_feed_and_conserves_stock`, which
steps the actual game with a hungry animal and a feed stock located at its map
cell, verifies `AnimalNPCBackend` chooses `eat`, checks the physical four-unit
consumption and hunger reset, and uses the same game-turn path for a distant
feed control. `PYTHONPATH=. pytest -q tests/test_simple_animals.py` now passes
**6 tests**. This closes the in-game store-feed action gap; it does not model
grazing, forage regrowth, or natural grass consumption. Avoid describing the
caregiver trace's unchanged grass as grazing.

### P1 — Package 12's main acceptance path uses hand-authored backend classes

The test does verify a good physical boundary: seller policy receives an offer,
accept/refuse differs, and transfer checks possession/reach without price or
`sell_willing`. However, `_SellerDecisionBackend` recognizes a literal text
substring and returns a fixed answer from a constructor boolean; `_OfferBackend`
always emits the same offer. This is a valid controlled contrast, not evidence
that a general simple profile interprets offer terms or forms consent. Keep
that scope explicit. The legacy purchase affordance/world wrapper remains a
separate migration item as the package note itself acknowledges. To close the
full gate, exercise `SimplePolicy` profiles on the same visible offer, with
accept/refuse decisions keyed to observed offer content, and test an attempted
unconsented transfer or explicitly state that the current action model has no
contested held-property path.

Reproduce current gate:

```sh
PYTHONPATH=. pytest -q tests/test_package12_exchange_consent.py
```

### P1 — Package 13 norm contrast is narrow and non-coercive

The paired physical-options and witnessed/unwitnessed tests are useful and
avoid omniscience. The actual norm choices and witness response are custom
scripted test backends (`_RoomPolicy`, witness/return logic), and enforcement
is a request followed by voluntary return. That meets a bounded actor-action
example, not a coercive enforcement model or evidence that policy interpretation
is learned from world law. Keep the documented limitation attached to any
summary; add a separate actor-held policy test for a physical consequence only
if the intended claim includes coercion or competing enforcement choices.

### P2 — Package 16 only adapts one cup movement affordance

The fixture is honest about its limit: it tests a one-turn scoring preference
versus refusal on the same room objects. The `MoveCupToSelf` hook contributes
a fixed bonus for one exact object/destination; there is no observation of a
menu/order, alternate service interpretation, or response by Nell. This passes
the narrow physical adaptation/refusal check but only partially covers the
plan's alternate interpretation/refusal gate. Do not call it restaurant
service cognition. For that stronger claim, add an observed request or menu
context and a second actor choice/refusal with no automatic setup or completion.

Reproduce current gate:

```sh
PYTHONPATH=. pytest -q tests/test_simple_room_policy.py
```

### P2 — Trace and fixture gaps remain despite strong local assertions

* Package 5's main actor movement test intentionally supplies a predetermined
  `ActionBackend`; this is a physical movement/access regression, not a test of
  cognition choosing a route. Coordinate-backed object reach is tested mostly
  through direct world calls, with one turn-level pickup/move/drop path.
* Package 6's absent-food control demonstrates starvation and metabolism-off
  control, but the food-present fixture stocks ten apples and only eats two in
  18 turns. It proves a short hunger-response loop, not sustained nutrition;
  the note correctly limits long-run claims.
* Package 7 has real game-turn success and missing-tool/material controls, but
  tool loss during a timed job and direct world start/retry assertions are
  separate from the actor-turn trace. The test-specific trace also supplements
  the general runner because bulk stocks/tool condition are omitted there.
* Package 8's repeated replay is deterministic but the helper hardcodes one
  seed; its water/no-water/season cases are single-seed scenario controls, not
  robustness evidence.
* Package 11's listener recognizes a literal substring and always replies; its
  test confirms situated delivery/privacy and no compelled action, but not
  semantic message interpretation. Delivery currently requires same-cell
  co-location, as documented.
* Package 15 declares three seeds but the same small rule-based fixture gives
  identical outcomes for every seed, disables metabolism, and uses one binary
  sharing transfer. It is a shock/accounting/policy-choice harness, not a
  survival-under-scarcity or fairness/cooperation test. The findings note most
  of these limits; keep them beside any aggregate claim.

These are scope/claim limits, not grounds to discard the focused physical
regressions. Reproduction commands for package 5–11 are in their corresponding
`SIMPLE_VILLAGE_PACKAGE_*_FINDINGS.md` files; the tests are
`tests/test_simple_movement_access.py`, `test_simple_body_food.py`,
`test_simple_tools_materials_job.py`, `test_simple_crop_water.py`,
`test_simple_animals.py`, `test_simple_storage_decay_construction.py`,
`test_simple_observation_communication.py`, and
`test_simple_norms_enforcement.py`.

## Gate status snapshot

| Package | Current evidence reviewed | Audit disposition |
| --- | --- | --- |
| 5 | Turn-level movement/failure plus direct object access controls | Physical path covered; predetermined action, limited movement-choice evidence |
| 6 | Real fetch/eat/rest and starvation/metabolism-off controls | Short configured loop covered; no long-run nutrition claim |
| 7 | Timed work, finite input, missing material/tool, wear/recovery | Focused mechanics covered; keep direct helper controls distinct from actor turns |
| 8 | Watered/dry/season controls and fixed-seed replay | Bounded single-seed crop loop covered |
| 9 | Current test asserts stay/no grass use; direct-call feed test | Stale findings note; planned in-game feeding gate not demonstrated |
| 10 | Current construction test asserts 10 successful turns/exact inputs | Stale findings note; focused current test passes |
| 11 | Situated speech delivery, reply, non-recipient/privacy controls | Bounded scripted communication fixture |
| 12 | Backend acceptance/refusal and physical transfer | Controlled boundary fixture; general term interpretation/legacy path gap |
| 13 | Same physical affordance, witnessed request/return, unseen control | Bounded voluntary norm response; no coercive enforcement claim |
| 14 | Multi-role real-turn provenance and shortage control | Focused tests pass; scripted workflow; only integration-path evidence |
| 15 | Three-seed shock accounting and policy transfer contrast | Narrow deterministic allocation stress; not scarce-food survival evidence |
| 16 | Same room objects, one-step move/refusal | Narrow affordance preference; no service protocol or second-actor response |

