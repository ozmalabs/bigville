# Learning evaluation: town100, seed 305000

Schema `bigville/learning-eval/1`. Scenario `town100`, seed `305000`, pack `bigville`, pack hash `6f8a636fef373804b3ee3e87fae524c3e47e9554bfd737b9934bd4dc257e1ac5`, prompt schema `bigville/prompt/3`.

Providers are scripted fakes (no network, no model). A VOID arm is reported with its metrics but its numbers do not count.

## Control: learner against non-learner

Same residents, every turn a consult, 30 turns, no call cap.

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

## Backends on one scenario and seed

Failures are learning failures (body-state refusals excluded; see the method note).

| arm | kind | void | survived (subjects) | failures | repeat-mistake rate | deviation rate | work (subjects) | ties (subjects) | body-state refusals (subjects) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocelot | ocelot | skipped: ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter' | | | | | | | |
| scripted_learner | llm | no | 3/3 | 6 | 0.000 | 0.294 | 0 | 0 | 9 |
| scripted_nonlearner | llm | no | 3/3 | 36 | 0.917 | 1.000 | 1 | 0 | 6 |
| simple | simple | no | 3/3 | 0 | n/a | n/a | 1 | 0 | 9 |

## Marginal effect: scripted_learner against simple

Deviation is the share of consulted replies that departed from the autopilot's would-be choice (mean over residents: 0.294). Outcomes are the same resident's in the pure-simple run on the same seed.

| resident | deviation | survived (model / simple) | food end (model / simple) | work (model / simple) | ties (model / simple) |
| --- | --- | --- | --- | --- | --- |
| Adelina Gorse | 0.250 | yes / yes | 0.000 / 0.000 | 0 / 0 | 0 / 0 |
| Adelina Norbisham | 0.300 | yes / yes | 0.000 / 0.000 | 0 / 1 | 0 / 0 |
| Adelina Sputterfield | 0.333 | yes / yes | 0.000 / 0.000 | 0 / 0 | 0 / 0 |

## Whole town, per arm

All residents, not only the subjects. Body-state refusals are counted here and kept out of the learning failures.

| arm | alive at end | learning failures | body-state refusals | refusals by reason | accidents | breakages |
| --- | --- | --- | --- | --- | --- | --- |
| scripted_learner | 100 | 6 | 305 | collapsed 305, malformed 6 | 0 | 0 |
| scripted_nonlearner | 100 | 36 | 302 | collapsed 302, malformed 36 | 0 | 0 |
| simple | 100 | 0 | 305 | collapsed 305 | 0 | 0 |

## Leak guard

| arm | prompts checked | violations | void |
| --- | --- | --- | --- |
| scripted_learner | 209 | 0 | no |
| scripted_nonlearner | 270 | 0 | no |

## Method

Every metric is read from the engine's records (see `bigville/learning_eval.py`). A body-state refusal (asleep, collapsed, passed out) is counted as a refusal and kept out of the learning failures. The arms share the seed, so the residents and the first turn are the same in each arm. The digest of each arm is the SHA-256 of its per-turn proposals and results: `14c509706f10b2b5233e981ae7e6bfa12d0a3f5904fdc12702781a19da94a6fb`.
