# Phase 014: world mechanics parameters in the pack

## Summary

The mechanics constants that were hardcoded in `worlds/bigville_world.py` now come from the data
pack. The moved values are: the clock (tick length, day length, year, season starts), the town's
starting state, the resident defaults used by `add_actor`, injury and care amounts, the starvation
limit, default shop, stock, and wage prices, the literacy gate for each written document kind, the
engine and resident seed lists, and the townspeople relationship map. Each value is a named table in
`packs/bigville` (and an identical copy in `packs/test_hamlet`), bound in `world_affordances.py` or
`shared_frames.py`, and checked by new self-test checks.

Defaults are unchanged. The self-test output is byte-identical to before. Two behaviour digests (one
for the default world, one for the 100-resident town's build and three periods) match HEAD exactly.
The full suite has 351 passing tests: the 340 existing tests, with no assertion or number changed,
plus 11 new tests in `tests/test_phase014_parameters.py`. A child pack that extends bigville changes
the coin of a new resident, the duration of a forge job, and the length of a calendar day.

Initial `git status --short` was empty (HEAD `c2d2161`).

## Changes

### Moved constants

Each row gives the old literal, where it was, and the pack key that replaces it.

| Old literal (location) | Now read from |
|---|---|
| `MINUTES_PER_TICK = 15.0` (module); `math.ceil(mins / ...)` in `start()` | `TIME.minutes_per_tick` |
| `96` ticks a day, `0.25` hours a tick, `% 24`, `6.0` dawn (`_advance_calendar`) | `TIME.ticks_per_day`, `hours_per_day`, `start_hour` |
| `% 360`, `// 360`, `// 7`, season cut-offs `90/180/270` (`_advance_calendar`) | `TIME.days_per_year`, `days_per_week`, `season_start_day` |
| `ticks_per_period=96` (`run_village`) | `TIME.ticks_per_period` (argument default is now `None`) |
| `1.0 / 360.0` age step (`_daily_life_tick`) | `TIME.days_per_year` |
| Town node defaults: clock, period, day, hour 6.0, week, year 1.0, season, observed_*, weather, rain, temperature 15.0, cold, wet, firewood_demand 1.0 (`__init__`) | `TOWN_INITIAL`. A scenario `initial` still overrides it. The town name stays in code. |
| `add_actor` defaults: skill 0.7, station "educated", learn 1.0, age 30.0, life_stage "adult" (signature) | `ACTOR_DEFAULTS`. Signature defaults are now `None` sentinels. |
| `add_actor` coin 10.0, reputation 0.5, aptitude 1.0, health_value 1.0, injury 0.0 | `ACTOR_DEFAULTS` |
| `add_actor` inventory carrier max_load 50.0, capacity 50.0 | `ACTOR_DEFAULTS.inventory_max_load`, `inventory_capacity` |
| `add_actor` Body health 1.0, mood 0.5, str_base 1.0, sta_base 1.0, stamina_reserve 1.0 | `ACTOR_DEFAULTS.body` |
| `add_actor` starve_limit 4.0 | `CARE.starve_limit` |
| `add_tradesperson` station "educated" and base_skill fallback 0.7 | `ACTOR_DEFAULTS.station`, `skill` |
| `injure` severity 0.25 (signature) | `CARE.injury_severity` (signature default is now `None`) |
| `treat` health +0.25, fallback health 0.5 | `CARE.treat_health_gain`, `treat_health_base` |
| `care_for` injury -0.2, health +0.1, need when hunger < 2.0 | `CARE.care_injury_relief`, `care_health_gain`, `care_hunger_need` |
| `_actor_options` need check (`hunger >= 2.0`, the mirror of `care_for`, line 5742) | `CARE.care_hunger_need` |
| `_daily_life_tick`: injury -0.05, health +0.02, healed at injury <= 0.05, malnourished at hunger >= 2.0, disease -0.05 | `CARE.daily_injury_recovery`, `daily_health_recovery`, `recovered_injury_below`, `malnourished_hunger`, `disease_health_loss` |
| `_death_cause` fallback 4.0; metabolism loop fallback for residents 4.0 | `CARE.starve_limit` |
| `add_shop` price 2.0, is_open 1 (signature) | `PRICE_DEFAULTS.shop_price`, `shop_is_open` (signature defaults are now `None`) |
| `stock_person` price 1.0 (signature) | `PRICE_DEFAULTS.stock_price` |
| `sell_labor` wage 2.0 (signature, retired method) | `PRICE_DEFAULTS.labour_wage` |
| `write_document` / `read_document` literacy gate: `law`/`charter` need `can_read_law`, `policy` needs `can_read` | `DOCUMENT_LITERACY`, read through `_can_meet_document_literacy` |
| Engine seed loads in `__init__` (ten ids, in order) | `ENGINE_SEEDS`. Scenario seeds still load after them. |
| `BigvilleOcelotActor` seed loads (three decision and speech seeds, plus `conversation`) | `RESIDENT_SEEDS`, `RESIDENT_CONCEPT_SEEDS` |
| `TOWNSPEOPLE_50_RELATIONSHIP_KIND` and its fallback `("acquaintance", 0.5)` | `RELATIONSHIP_KINDS`, `RELATIONSHIP_DEFAULT` (in `shared_frames.py`) |

Other interface changes:
- `BigvilleOcelotActor(name, data_pack=None)`. `None` is the default pack, so the no-world path still works.
  `add_actor` passes the world's pack to the mind.
- `from_townspeople_50` reads the relationship map from the world's pack (`world.E`), because it is a
  classmethod.

### New pack tables

Files (new, in both `packs/bigville` and `packs/test_hamlet`, with identical content):
- `world/time.json` (TIME), `world/town_initial.json` (TOWN_INITIAL), `world/actor_defaults.json`
  (ACTOR_DEFAULTS), `world/care.json` (CARE), `world/prices.json` (PRICE_DEFAULTS),
  `world/document_literacy.json` (DOCUMENT_LITERACY), `world/engine_seeds.json` (ENGINE_SEEDS,
  RESIDENT_SEEDS, RESIDENT_CONCEPT_SEEDS), `frames/relationship_kinds.json` (RELATIONSHIP_KINDS,
  RELATIONSHIP_DEFAULT).
- Both `pack.json` manifests gained 11 entries each (130 table names, from 119).
- The values are the old literals exactly. The hamlet copies are not hamlet-specific values. They are
  the same mechanics, which the hamlet needs to boot. The hamlet's own values are a later choice.
- Every file is in the exporter's format (`json.dumps(indent=2)`), so the export round-trip test
  holds.

### Self-test checks (`domains/bigville_entities.py`, inside `check_consistency`)

- TIME: tick length positive; the four counts positive whole numbers; `start_hour` inside the day;
  `season_start_day` names equal SEASONS, begin at 0, rise, and stay inside the year.
- TOWN_INITIAL: `season` is a SEASONS key and matches day 0; `weather` is a WEATHER key; `hour`
  equals `TIME.start_hour`.
- ACTOR_DEFAULTS: `station` is a STATION_EDUCATION key; `life_stage` is a LIFE_STAGES key; skill,
  reputation, and health in [0, 1]; coin, age, and inventory limits valid.
- CARE: the fractions in [0, 1]; `starve_limit` positive.
- PRICE_DEFAULTS: prices and wage valid; `shop_is_open` is 0 or 1.
- DOCUMENT_LITERACY: keys are policy, law, or charter; values are functional or educated.
- ENGINE_SEEDS, RESIDENT_SEEDS, RESIDENT_CONCEPT_SEEDS: no duplicates; each id has a file in
  `seeds/` or `bigville/seeds/`.
- RELATIONSHIP_KINDS and RELATIONSHIP_DEFAULT: a kind is named; strength in [-1, 1].

The checks print nothing when they pass, so the self-test output did not change.

### Files changed

- `worlds/bigville_world.py`: the moved reads (above). No other behaviour change.
- `domains/world_affordances.py`: bindings for TIME, TOWN_INITIAL, ACTOR_DEFAULTS, CARE,
  PRICE_DEFAULTS, DOCUMENT_LITERACY, ENGINE_SEEDS, RESIDENT_SEEDS, RESIDENT_CONCEPT_SEEDS.
- `domains/shared_frames.py`: bindings for RELATIONSHIP_KINDS and RELATIONSHIP_DEFAULT.
- `domains/bigville_entities.py`: the new checks.
- `packs/bigville/pack.json`, `packs/test_hamlet/pack.json`: manifest entries.
- New pack files: `packs/bigville/{world/time,world/town_initial,world/actor_defaults,world/care,world/prices,world/document_literacy,world/engine_seeds}.json`, `packs/bigville/frames/relationship_kinds.json`, and the same eight under `packs/test_hamlet/`.
- New test: `tests/test_phase014_parameters.py` (11 tests).
- New report directory `docs/phases/phase014/`: this report, `behaviour_digest.py` and its
  before/after outputs, and the self-test and test outputs.

## Validation

| Command | Result |
|---|---|
| `git status --short` (start) | empty |
| `python3 domains/bigville_entities.py` | exit 0; ERRORS (0), WARNINGS (0). Output identical to the baseline (`diff docs/phases/phase014/before_selftest.txt docs/phases/phase014/after_selftest.txt` is empty). |
| `python3 -m domains.check --pack test_hamlet` | exit 0; ERRORS (0), WARNINGS (0) (`after_selftest_hamlet.txt`) |
| `PYTHONHASHSEED=0 python3 docs/phases/phase014/behaviour_digest.py`, run on `git archive HEAD` and on the working tree | identical (`before_behaviour.json`, `after_behaviour.json`). The digest covers resident defaults and inventory limits, injury, treatment, care, starvation cause, the document literacy gate for a policy and a law, a shop's price, a stock price, the calendar after 100 ticks, and a tradesperson's defaults. |
| `PYTHONHASHSEED=0 python3 docs/phases/phase013b/default_digest.py`, HEAD and working tree | identical (`cmp`). This covers the 100-resident town built with `from_town100()` and three periods. |
| Townspeople relationships (`from_townspeople_50(305000)`), HEAD and working tree | identical kind and strength for all 22 ties (checked with a throwaway script, not kept) |
| `timeout 1500 python3 -m pytest -q -p no:cacheprovider tests/test_phase014_parameters.py` | 11 passed |
| `timeout 1500 python3 -m pytest -q -p no:cacheprovider tests/test_phase013a_packs.py` | 8 passed (after the file format fix described under Deviations) |
| `timeout 1500 python3 -m pytest -q -p no:cacheprovider` (baseline, before changes) | 340 passed (`before_pytest.txt`) |
| `timeout 1500 python3 -m pytest -q -p no:cacheprovider` (final) | 351 passed in 74.63 s (`after_pytest.txt`) |

The 11 new tests:
- The default values equal the old literals.
- The default world reads the default pack, and its defaults match.
- The hamlet carries the same mechanics tables, and its check has no errors.
- A child pack (`extends` bigville) that merges `ACTOR_DEFAULTS.coin` = 25.0 and `TIME.minutes_per_tick` = 7.5
  gives a 25-coin resident, and a 90-minute forge job takes 12 ticks (6 in the default world).
- A child pack with `TIME.ticks_per_day` = 48 gives day 2 and hour 8.0 after 100 ticks (default: day 1, hour 7.0).
- A child pack with `CARE.starve_limit` = 2.0, `TOWN_INITIAL.firewood_demand` = 2.0,
  `PRICE_DEFAULTS.shop_price` = 3.5, and `DOCUMENT_LITERACY.law` = functional changes starvation,
  firewood, a shop's price, and whether a functional reader can write a law. A policy keeps its gate.
- A child pack with injury and care amounts changes the injury and health numbers, which match the arithmetic.
- A child pack with `ENGINE_SEEDS` and `RESIDENT_SEEDS` changes the seeds recorded for the world and for a mind.
  A mind with no pack still loads its default seeds.
- A scenario's `initial` value still overrides `TOWN_INITIAL`.
- A child pack with an unknown station and an unknown engine seed fails the self-test with those named errors.
- The townspeople map loads from the pack and yields feud and friend ties.

## Limits

- The digests cover only the default world. The child-pack behaviour is tested in the new file. The
  100-resident village run (`run_village`) was not run. The digest runs `from_town100` for three periods.
- `from_townspeople_50` is classmethod-bound to the pack it builds. A child pack cannot select a pack
  for it, so the relationship map is tested through the default pack only.
- The child packs are built in `tmp_path` in the test. Nothing is committed to `packs/`.
- The hamlet copies carry bigville's mechanics values, not hamlet-specific ones.
- The "clear" and "spring" reads in weather and season lookups (`_set_daily_weather`, the observation
  records) remain literals as fallbacks. Each reads a value the town node always has.

## Deviations

- The first full run failed `tests/test_phase013a_packs.py::test_export_rerun_is_byte_identical`. My
  hand-written JSON used inline objects for relationship kinds, and the exporter writes every object
  expanded (`json.dumps(indent=2)`). I re-serialised the eight new files in the exporter's format. The
  content and key order did not change. The test then passed.
- Beyond the brief's list, `add_tradesperson` (station and base skill default) and the metabolism check
  in `_actor_options` (`hunger >= 2.0`, the mirror of `care_for`) also read the pack. They use the
  same constants and keep the behaviour of the defaults.

## Left in code (deliberately)

- Option scores. Every score in `_actor_options` is 0.0, and the brief says scores belong to backends.
  The one literal 1.0 is the `open_object` score in `physical_object_affordances` (line 776); it stays.
- Founding-town content, moved in Phase 016: `populate_town100` passes `skill=0.7` explicitly, has the
  station map `{"low","middle","high"}`, and places the two spring water sources. `_village_work_tick`
  is untouched (Phase 015).
- Animal starvation: the fallback `starve_limit` 3.0 in the animal metabolism loop, and the animal
  spec default of 3 in `add_animal`. These are animal data, not resident data.
- Per-item and per-event fallbacks and magnitudes not in the brief: tool wear 0.02 and 0.1 (line 1044,
  1160, 6768), stamina recovery 0.1 (1132), infrastructure decay 0.25 (4081), public observation
  severities 0.05, 0.02, 0.15 (4654, 4662, 4965, 5410, 6506, 6515, 6523, 6716), salience (6014).
- `add_shop` `recipe_in` and `recipe_out` 1.0 (conversion ratios, not prices).
- Initial bookkeeping: Body strength and stamina 1.0 (derived from the base values), role identity 0.0,
  available time 1.0, empty klass and group strings, and the container and lock flags.
- Literacy reads: the newspaper gate (`LIT_FUNCTIONAL`, line 2412) and `can_account` (`LIT_EDUCATED`).
  These are action gates, not document kinds. The tiers are already in the data.
- Outside the write scope, so unchanged:
  - `bigville/game.py` (`ticks_per_period=96` default), `bigville/scenario_runner.py` (`run_scenario`
    and the CLI default 96), and `bigville/village_eval.py` (`TICKS_PER_PERIOD = 96`, preregistered).
    None imports a moved name.
  - `worlds/bigville_social_seed.py:143` names the old `TOWNSPEOPLE_50_RELATIONSHIP_KIND` in a docstring.
  - `worlds/bigville_town100_world.py` reads none of the moved values, so it is unchanged.

## Observations

- `TOWN_INITIAL.temperature` is 15.0, which the code had. The weather table's temperature is on a 0 to 1
  scale (clear = 0.6). The first daily weather overwrites the town's temperature, so the 15.0 never
  affects a weather check. This mismatch predates the phase, and I kept the value.
- `TOWN_INITIAL.hour` (6.0) and `TIME.start_hour` (6.0) are two keys for one fact. The self-test requires
  them to match.

## Open questions

1. `bigville/game.py`, `bigville/scenario_runner.py`, and `bigville/village_eval.py` still hold 96
   ticks per period. A child pack that changes `TIME.ticks_per_period` changes `run_village`, but not those
   runners. Should the runners read the pack, or should they stay fixed?
2. Should `TOWN_INITIAL.temperature` use the weather scale (for example, 0.6 for clear), or stay at 15.0?
3. Should the two copies of the 96-tick day in the runners and in `TIME` be merged into one source?
