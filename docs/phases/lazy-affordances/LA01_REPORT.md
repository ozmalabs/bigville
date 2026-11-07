# LA01 — Mode flag, measurement and baseline

Status: complete. Phase LA01 of the lazy-affordances plan.
Base commit: `18f15f500a036f6bb1fba0f5d386b0bf634aec2c` (branch `lazy-affordances`).
No gameplay behaviour changed.

## What was added

### `BigvilleGame.affordance_mode`

- New keyword-only constructor option `affordance_mode: str = "menu"`.
- Validated against `{"menu", "lazy"}` by a property setter; any other value
  raises `ValueError` at construction (and on later assignment).
- Exposed as the read/write property `BigvilleGame.affordance_mode`.
- `create_game(..., affordance_mode="menu")` forwards the value to
  `BigvilleGame`; every existing argument and default is unchanged.
- The default remains `"menu"`, and the menu path is untouched.

### Lazy mode in LA01 is a placeholder

In LA01 `affordance_mode="lazy"` **still builds the full menu**. The flag only
selects the seam; `_context()` does not branch on it and `_build_contexts()` /
`step()` are unchanged. This is intentional: LA01 is the measurement and
seam phase, and the plan only makes lazy real in LA03–LA04. The report and the
mode docstring state this so the flag is not mistaken for an acceleration.

### Measurement seam on `_context`

```python
def _context(self, actor, *, practice_window=None,
             snapshot=None, skip_affordances=False) -> ActorContext:
```

When `skip_affordances=True`:

- `world.actor_affordances(actor)` is **not** called;
- `context.affordances` is `[]`;
- `world._actor_targets[actor]` is not populated by this call (the world
  entries created at actor setup are left as they were).

Normal calls (including every call from `step()` / `_build_contexts()`) do not
pass the flag and are byte-for-byte the old behaviour. The seam is used only by
`tools/benchmark_affordances.py` and `tests/test_lazy_affordances.py`; routing
the game step through it is deliberately deferred.

## Benchmark

Command (construction excluded, `time.perf_counter`, one pass per path and
size, scenario physical subsystems already disabled by the TG07 builder):

```bash
python3 tools/benchmark_affordances.py --sizes 50,100,200 --repeats 1
```

| size | actors | menu total ms | menu ms/actor | observe total ms | observe ms/actor | ratio |
|---|---|---|---|---|---|---|
| 50 | 50 | 454.726 | 9.095 | 17.874 | 0.357 | 25.441x |
| 100 | 100 | 961.02 | 9.61 | 63.58 | 0.636 | 15.115x |
| 200 | 200 | 2230.773 | 11.154 | 212.974 | 1.065 | 10.474x |

`observe_only` is `_context(actor, skip_affordances=True)`. It is a local
measurement helper in LA01, **not** the lazy play path. Each pass clears
`game._published_practice` first so both paths see the same practice window.

The first `--sizes 50,100` run on the same host produced 434.544 ms / 8.691 ms
per actor (menu) vs 28.147 ms / 0.563 ms per actor (observe-only), ratio
15.438x, and 959.496 ms / 9.595 ms vs 66.943 ms / 0.669 ms, ratio 14.333x.
The menu cost is stable at roughly 9–11 ms per actor; the observe-only
denominator is small (sub-millisecond to ~1 ms per actor) and therefore the
ratio is noisy. Even the most conservative reading puts menu construction at
more than 10x the observation-only context.

## Tests

Executed in this worktree:

```bash
python3 -m pytest -q tests/test_lazy_affordances.py -p no:cacheprovider
# 7 passed in 1.34s

python3 -m pytest -q tests/test_tick_trace.py tests/test_tick_snapshot.py -p no:cacheprovider
# 14 passed in 82.82s
```

`tests/test_lazy_affordances.py` covers:

- default `"menu"` and rejection of unknown values for both `create_game` and
  `BigvilleGame`;
- `create_game(..., affordance_mode="lazy")` exposing `"lazy"`;
- identical default menu-mode `TurnTrace` digests across two 2-turn runs on the
  small TG01 scenario;
- `skip_affordances=True` never calling `world.actor_affordances`, returning
  `context.affordances == []`, and leaving `_actor_targets` untouched, while a
  normal call returns a non-empty town menu;
- importing `tools.benchmark_affordances`, and `build_scenario(5)` returning a
  scenario without constructing a world or game.

## Host-contention caveat

A full `pytest` run was already active in this worktree during the phase. Load
average was about 7.8 on 16 CPUs. The wall-clock numbers above include that
contention and should be read as same-host relative measurements, not absolute
throughput. The 200-resident cell was run because load stayed below the core
count; its exact numbers are recorded above either way. Re-run the benchmark on
an idle host before quoting absolute milliseconds in LA06.

## Limitations

- `"lazy"` does not yet skip the menu; it is a validated placeholder.
- `skip_affordances` is only a benchmark/test seam. It suppresses the menu but
  leaves `_actor_targets` at whatever earlier calls left there; it does not
  rebuild a proposal path.
- The benchmark measures context construction only: no backend decisions,
  world tick, enactment or commit, and no threading.
- Only the synthetic TG07 scenario is measured; real town scenarios may have
  a different menu mix.

## Handoff to LA02

LA02 (target resolution) owns the next removal:

- add `world.resolve_targets(actor, action, params)` and use it in
  `_enact_plan()`, so enactment no longer rebuilds the hidden full menu;
- keep `_actor_targets` compatibility for `target:N` proposals, but populate
  only the selected action's candidates;
- leave `affordance_mode` and this measurement seam in place, and keep the
  menu-mode trace as the equivalence oracle.

No change in LA01 should be reverted by LA02; the seam is additive.
