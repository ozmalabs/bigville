# Bigville and Ocelot integration

This guide covers the supported source-checkout integration, what the current
resident adapter can communicate, checkpoint save/restore, and focused
acceptance commands. It includes a real-resident smoke example. The smoke
example proves resident construction, one cognition decision, one accepted
world action, and a checkpoint continuation. Separate bounded hunger and
20-resident scale smokes are documented below; neither evaluates town100.

## Supported setup

Bigville supports Python 3.11 or newer. Ocelot must also be available as a
source checkout and its `substrate_rs` native extension must be built for the
Python environment running Bigville. These projects are not installed as a
single package, so put both roots and Ocelot's native Python package directory
on `PYTHONPATH`. Set `BIGVILLE_ROOT` to the Bigville checkout. Either order of
the two repository roots is supported, and construction works from a neutral
working directory such as `/tmp`.

For example, from sibling checkouts:

```bash
export BIGVILLE_ROOT="$HOME/ozmadev/bigville"
export OCELOT_ROOT="$HOME/ozmadev/ocelot"
export PYTHONPATH="$BIGVILLE_ROOT:$OCELOT_ROOT:$OCELOT_ROOT/runners/dsl/python"
```

If the Ocelot extension has not been built, use Ocelot's build instructions.
With Rust and maturin installed in the active Python environment, the direct
extension build is:

```bash
cd "$OCELOT_ROOT/runners/dsl"
python3 -m pip install 'maturin>=1.4,<2'
maturin develop --release
```

Ocelot also provides `bash "$OCELOT_ROOT/scripts/engine_build.sh"` for its
full engine build. A Bigville-only install does not include or silently replace
Ocelot: selecting the `ocelot` backend without the adapter or native extension
raises `OcelotUnavailableError` with the import cause.

The fresh-process acceptance tests verify both repository import orders,
construct real Ocelot residents beside human and simple residents from a
temporary working directory, and check the missing-extension diagnostic.

## Real resident, turn, and checkpoint example

Run this from a shell with the environment above. It starts in `/tmp`, builds a
small supplied scenario with a real Ocelot resident, advances one turn, saves
the game at the step boundary, restores it, then advances both branches and
compares their physical world checkpoint representation.

```bash
cd /tmp
python3 - <<'PY'
import json
from pathlib import Path

from bigville import create_game
from bigville.game_persistence import load_game_checkpoint, save_game_checkpoint
from worlds.bigville_ocelot_adapter import BigvilleOcelotResident

root = Path(__import__('os').environ['BIGVILLE_ROOT'])
scenario = json.loads((root / 'scenarios/simple_resident_food.json').read_text())
scenario['actors'][0]['backend'] = 'ocelot'

game = create_game(scenario=scenario, seed=305000, default_backend='simple',
                   autonomous=True, ticks_per_period=None)
resident_name = next(iter(game.characters))
mind = game.world.actor_mind(resident_name)
assert isinstance(mind, BigvilleOcelotResident)
first = game.step()
assert first['status'] == 'advanced'
print('resident:', resident_name, type(mind).__module__ + '.' + type(mind).__name__)
print('turn:', first['turn'], 'accepted:', first['results'][resident_name])

checkpoint = Path('/tmp/bigville-ocelot-checkpoint')
save_game_checkpoint(game, checkpoint)
restored = load_game_checkpoint(
    checkpoint,
    resident_loader=lambda _name, path: BigvilleOcelotResident.load(path),
)
assert isinstance(restored.world.actor_mind(resident_name), BigvilleOcelotResident)

expected = game.step()
actual = restored.step()
assert expected['status'] == actual['status'] == 'advanced'
assert game.world.eng.to_checkpoint_dict() == restored.world.eng.to_checkpoint_dict()
print('restored turn:', actual['turn'], 'world state matches uninterrupted branch')
PY
```

`save_game_checkpoint(game, path)` and `load_game_checkpoint(path, ...)` are
available from `bigville.game_persistence`. A checkpoint captures a committed
generation with checksummed files and a manifest written last. Save only
between game steps, when no world actor tick or major-action dispatch is
active. `load_game_checkpoint` accepts the same optional callbacks as world
restore: `resident_loader(name, path)`,
`physical_subsystem_extensions={...}`, and `cognition_factory=...`.
Provider-owned residents must be restored by their provider's loader; for
Ocelot use `BigvilleOcelotResident.load(path)`. External physical subsystem
extension callbacks must be supplied again with matching names. Callback code
itself is not serialized or fingerprinted.

World-only checkpoints are available as
`bigville.world_persistence.save_world_checkpoint(world, path)` and
`load_world_checkpoint(path, ...)`. They restore the canonical typed graph,
supported world state, random generator state, data-pack identity, and each
resident's own state. Unsupported values, missing resident checkpoints,
schema mismatches, integrity failures, and incompatible packs fail closed.

The current game checkpoint implementation supports built-in Ocelot, simple,
and Human backends, built-in animal backends, the built-in template
conversation interface, and the typed Bigville graph value set. It rejects
custom backends/policies and callback hooks without an explicit checkpoint
adapter, Human chooser callbacks, and custom conversation interfaces. It is a
versioned source API (`.../1` schemas), not a promise of compatibility across
future schema changes.

## Communication capabilities and limits

The ordinary Ocelot backend currently advertises `mode="templated"`,
`supports_free_text=false`, `understands_raw_speech=false`, and
`requires_conversational_interface=true`. The resident does not provide the
free-text proposal hook called by the ordinary Bigville game path. Ocelot has a
separate full-text goal-utterance renderer, but the ordinary backend does not
call it; Bigville therefore does not fabricate cognition-owned speech.

Bigville makes received utterances available in the observation context, but
the ordinary loop does not route their raw payloads through a resident
speech-ingestion hook. Payload transport is not comprehension. Those
capability flags remain false until an end-to-end route is implemented and
tested. These facts are checked by
`tests/test_bigville_ocelot_communication.py`.

## Focused acceptance commands

With `BIGVILLE_ROOT`, `OCELOT_ROOT`, and `PYTHONPATH` set as above, run from
the Ocelot checkout. These commands cover fresh-process setup and import-order
behavior, communication claims, graph/world/game checkpoint round trips,
real resident checkpointing, and the small mixed-village midpoint parity
exercise:

```bash
cd "$OCELOT_ROOT"
python3 -m pytest -q \
  "$BIGVILLE_ROOT/tests/test_bigville_ocelot_fresh_process.py" \
  "$BIGVILLE_ROOT/tests/test_bigville_ocelot_communication.py" \
  "$BIGVILLE_ROOT/tests/test_bigville_graph_persistence.py" \
  "$BIGVILLE_ROOT/tests/test_bigville_world_persistence.py" \
  "$BIGVILLE_ROOT/tests/test_bigville_game_persistence.py" \
  "$BIGVILLE_ROOT/tests/test_mixed_ocelot_village.py" \
  "$BIGVILLE_ROOT/tests/test_mixed_ocelot_checkpoint_parity.py" \
  "$OCELOT_ROOT/tests/test_bigville_resident_persistence.py"
```

Observed on Python 3.13.5 with the built native extension: **28 passed in
9.86s**. This command includes the four-resident, eight-turn mixed-village
hunger behavior test. It does not establish long-run food access or survival,
and it does not include town100-scale acceptance. Those gates remain pending.

The bounded hunger evidence is that two real Ocelot residents choose fetch
when hungry without carried food, eat when food is carried, and stop fetching
when sated; in the eight-turn synthetic mixed run they reached zero hunger and
had no rejected actions. See
[`docs/MIXED_OCELOT_VILLAGE_RUN_20261105.md`](MIXED_OCELOT_VILLAGE_RUN_20261105.md)
for the run setup and limits. This does not establish survival under ongoing
metabolism, depleted or contested food, seasonal production, or longer runs.

The mixed checkpoint parity test compares Bigville's physical graph, actions,
results, and continuations exactly across the resumed and uninterrupted
branches. For each Ocelot resident it compares the typed/attributed node and
edge multisets plus held decision/identity/personality state; transient
internal Ocelot graph IDs can differ after restore. This is a bounded
continuation check, not a claim that every internal provider detail is
byte-identical.

## 20-resident mixed-backend scale smoke

The standalone harness `tools/run_mixed_ocelot_scale.py` constructs a
synthetic 8×8 floor layout with ten Ocelot and ten simple residents, seeds a
shared pantry and hunger, and runs eight autonomous turns. It uses the
`resource_social_stress` physical rules with metabolism, ecology, and decay
disabled. Run it from the Ocelot checkout with its native virtual environment:

```bash
cd "$OCELOT_ROOT"
BIGVILLE_ROOT="$BIGVILLE_ROOT" \
PYTHONPATH="$OCELOT_ROOT:$BIGVILLE_ROOT" \
  "$OCELOT_ROOT/.venv/bin/python" \
  "$BIGVILLE_ROOT/tools/run_mixed_ocelot_scale.py"
```

The harness reports its budgets (5 seconds and 1,024 MiB peak RSS) alongside
the measurement and per-backend action counts. Two runs on the current tree
with Python 3.13.5 completed eight turns in **2.02 seconds** and **1.93
seconds**. The first created 1,471 world nodes, recorded zero errors or
rejected actions, and reported live RSS of **79.9 MiB** at the end (**78.4
MiB** after setup). Across the two runs, process `ru_maxrss` varied from
**645.2 MiB** to **785 MiB**. The latest **785 MiB** result is below the
revised 1,024-MiB budget; both observed runtimes are below five seconds. The
gap between live RSS and the high-water mark is why the harness reports both
values; these measurements do not establish a cause for the transient peak.

This is a local, synthetic workload with two observed runs. The layout,
resident count, disabled physical subsystems, and eight-turn duration do not
represent the full town100 simulation, longer-term food access, or resident
survival. Treat the numbers as reproducible smoke measurements, not a
production capacity guarantee. The harness currently reports whether the
peak RSS budget passes; it raises on a runtime overrun.

## Recorded smoke baseline

The original one-resident smoke used Bigville `53132e2587d950dc693cbdbe8172d1e5fd6b7837`,
Ocelot `173be37c48b64ea03255e529e83f772a593accb4`, and Python 3.13.5. It
reported `BigvilleOcelotResident`, turn 1 `advanced`, action accepted, and 804
resident graph nodes. The acceptance commands above were rerun against the
current working tree; concurrent uncommitted changes were present during that
run, so the result is a source-tree baseline rather than a clean-commit CI
result.
