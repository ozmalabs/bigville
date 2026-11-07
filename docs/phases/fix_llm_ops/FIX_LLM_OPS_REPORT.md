# FIX_LLM_OPS report

Supervisor follow-up, not a numbered phase. Two user decisions:

- (A) A game with an LLM resident can be checkpointed and loaded.
- (B) An LLM game attaches the complete log (the Phase 066 `LLMLog`) by default.

## Summary

- A game with LLM residents now saves and loads. The backend state goes through `bigville/llm_checkpoint.py`
  (new, committed). The untracked `bigville/game_persistence.py` has a small `kind == "llm"` hook. The provider is
  passed to `load_game_checkpoint(..., llm_provider=...)`. A load without a provider fails with a message that says so.
- `create_game` and `build_llm_town` attach one gzip `LLMLog` for all LLM residents of a game. The log goes to
  `llm_log_dir=`, else `BIGVILLE_LLM_LOG_DIR`, else `runs/llm_logs/<run id>.jsonl.gz` under the working directory.
  `llm_log=False` turns it off. A game with no LLM residents creates no file and no directory.
- Existing tests that build LLM games pass `llm_log=False`, because no `tests/conftest.py` exists.
- A game saved and resumed mid-run gives the same run digest as the uninterrupted run (test added, 2 residents plus
  simple residents, 6 turns, stop at turn 3).
- The simple-backend 60-turn run is unchanged: HEAD with only this change's files gives the HEAD digest.

## Changes

### New, committed (untracked until the supervisor commits)

- `bigville/llm_checkpoint.py`
  - `checkpoint_llm_backend(backend) -> dict`: JSON-safe. Schema `bigville/llm-checkpoint/1`, kind `llm`. Holds
    `LLMBackend.to_dict()` plus the settings the state does not hold (prompt pack, gate pack, autopilot on/off,
    the autopilot's `SimplePolicy` without a hook, thread size, full-packet interval, concurrency, and the budget caps).
    Refuses a policy with a hook callback, a custom policy class, or a custom prompt schema. It does not store the
    provider, the character, or the log.
  - `restore_llm_backend(data, character, provider=None, *, budget=None) -> LLMBackend`: a missing provider raises
    `ValueError("the LLM resident ... needs a provider to resume ...: pass llm_provider=...")`. A checkpoint for
    another resident, another kind, or another schema is refused.
  - `llm_budget_for(checkpoints) -> CallBudget | None`: one budget for all LLM entries of a checkpoint. Day counts
    are merged by union, spend by maximum (see Limits).
- `tests/test_fix_llm_checkpoint.py`: 16 tests. 8 call `llm_checkpoint` directly. 4 test functions (5 cases) use
  `game_persistence` and skip through `pytest.importorskip` if it cannot be imported. 4 test the default log.

### Committed-tree files (edited)

- `bigville/llm_log.py` (additive): imports `time`, `uuid`; constants `DEFAULT_LOG_DIR = "runs/llm_logs"`,
  `LOG_DIR_ENV = "BIGVILLE_LLM_LOG_DIR"`; functions `new_run_id()` and `attach_default(backends, *, enabled, log_dir,
  run_id)`. `attach_default` creates the log only when an LLM backend is in `backends`. Its redaction is the first
  LLM provider's `redact`. Each backend also redacts with its own provider, as before.
- `bigville/api.py` (3 hunks, file had no other-session edits):
  1. Anchor `from .backends.ocelot import ocelot_resident_class` (line 6): added
     `from .llm_log import attach_default as attach_default_llm_log`.
  2. Anchor `create_game(` signature line `                llm_provider=None):`: now
     `                llm_provider=None, llm_log=True, llm_log_dir=None):`, and three lines appended to the docstring
     describing the log.
  3. Anchor `    return game` followed by `def create_board_game(`: added
     `    game.llm_log = attach_default_llm_log(game.backends, enabled=llm_log, log_dir=llm_log_dir)` before
     `return game`.
- `bigville/llm_scenario.py` (3 hunks, file had no other-session edits):
  1. Anchor `from .backends.llm import LLMBackend`: added `from .llm_log import attach_default as attach_default_llm_log`.
  2. Anchor `pack: str = DEFAULT_PACK, settings: Any = None):`: now adds `llm_log: bool = True, llm_log_dir: str | None = None`
     and a docstring sentence.
  3. Anchor `    game.llm_residents = tuple(chosen)`: added the same `game.llm_log = attach_default_llm_log(...)` line
     before `return game`.
- `.gitignore`: added `runs/` as the last line (after `.env`). `docs/runs/` is not ignored and was not touched.

### Untracked file owned by the Ocelot persistence session: `bigville/game_persistence.py`

This file is not committed. The owner should see these exact hunks. Everything else in the file is unchanged.
Hunks as `diff -u` against the copy taken before this work:

```diff
 from .world_persistence import load_world_checkpoint, save_world_checkpoint
+from .backends.llm import LLMBackend
+from .llm_checkpoint import checkpoint_llm_backend, llm_budget_for, restore_llm_backend
+from .llm_log import attach_default as attach_default_llm_log
```

```diff
             "time_band": backend.time_band,
         }
+    if isinstance(backend, LLMBackend):
+        return checkpoint_llm_backend(backend)
     raise TypeError(
         f"unsupported backend {type(backend).__name__}; supply an explicit backend checkpoint adapter"
```

```diff
-def _build_backend(kind_state, world, character):
+def _build_backend(kind_state, world, character, llm_provider=None, llm_budget=None):
```

```diff
         backend.time_band = str(kind_state["time_band"])
         return backend
+    if kind == "llm":
+        return restore_llm_backend(kind_state, character, llm_provider, budget=llm_budget)
     raise ValueError(f"unknown checkpoint backend kind: {kind!r}")
```

```diff
 def load_game_checkpoint(path: str | Path, *, resident_loader: Callable | None = None,
                          physical_subsystem_extensions: dict | None = None,
-                         cognition_factory=None):
-    """Restore a supported game session and rebind world/resident backends."""
+                         cognition_factory=None, llm_provider=None, llm_log: bool = True,
+                         llm_log_dir: str | None = None):
+    """Restore a supported game session and rebind world/resident backends.
+
+    ``llm_provider`` is required when the checkpoint has LLM residents (the provider is not saved). ``llm_log`` and
+    ``llm_log_dir`` set the complete log of the restored LLM residents, as in ``create_game``."""
```

```diff
         if set(backend_states) != set(characters):
             raise ValueError("backend and character names do not match")
-        backends = {name: _build_backend(backend_states[name], world, character)
+        llm_budget = llm_budget_for(backend_states.values())
+        backends = {name: _build_backend(backend_states[name], world, character, llm_provider, llm_budget)
                     for name, character in characters.items()}
```

```diff
         game._sync_backend_metadata()
+        game.llm_log = attach_default_llm_log(game.backends, enabled=llm_log, log_dir=llm_log_dir)
         return game
```

`save_game_checkpoint` has no new parameter. Saving needs no provider.

### Existing tests (argument added, no assertion changed)

Each of these LLM-game constructions now passes `llm_log=False`. Without it, the default would write logs into the
working directory during the suite. Call sites: `tests/test_phase031_llm_backend.py` (3),
`tests/test_phase055_mixed_town.py` (1), `tests/test_phase055_transcript_replay.py` (5),
`tests/test_phase055_providers.py` (1), `tests/test_phase055_concurrency.py` (5), `tests/test_phase066_session_log.py`
(13). The two `create_game` calls in `test_phase031` that raise before building any backend were left alone.
No test number or expectation changed.

## Validation

Commands run in `/home/matt/ozmadev/bigville`:

| Check | Command | Result |
|---|---|---|
| Entity self-test | `python3 domains/bigville_entities.py` | exit 0, ERRORS (0), WARNINGS (0) |
| Pack self-test | `python3 -m domains.check` | exit 0, ERRORS (0), WARNINGS (0). `python3 domains/check.py` fails with `ModuleNotFoundError` on HEAD too, so run it as a module |
| New tests | `pytest tests/test_fix_llm_checkpoint.py` | 16 passed (2:30), run alone after the final edits. The final full run also has this file passing |
| Full suite, final | `timeout 5400 python3 -m pytest -q -p no:cacheprovider -rfEs` | 15 failed, 1722 passed, 3 skipped (25:45). Log: `full_suite_final.log` |
| Full suite, first | same command, before the resume-test ordering fix | 8 failed, 1729 passed, 3 skipped. Log: `full_suite_first_run.log` |
| 60-turn simple run | `create_game(scenario="town100", seed=305000, default_backend="cheap", autonomous=True)`, 60 `step()` calls, `RunDigest` | HEAD archive: `1ad861aa…47b`. HEAD with this change's files: `1ad861aa…47b` (identical) |
| Repo state | `git status --short`, `ls runs` | no `runs/` directory after the full run |

Final full-run failures, and what each one is:

- Ocelot (3): `test_bigville_ocelot_communication`, `test_mixed_ocelot_checkpoint_parity`,
  `test_mixed_ocelot_village`. They fail with `No module named 'worlds.bigville_ocelot_adapter'`, the known HEAD
  failure. The module is absent in this tree.
- TUI over HTTP (4): `test_phase057_tui.py`, four `test_over_http_*` and `test_the_server_refuses_*` cases. They pass on
  pure HEAD (48 of 48) and on HEAD with this change's files (48 of 48). They fail on the live tree (4 failed, 44 passed,
  twice). They still fail on a copy of the live tree with `api.py`, `llm_scenario.py` and `llm_log.py` restored to
  HEAD. The cause is the other session's uncommitted edits to `bigville/server.py` / `game.py` / related files.
- Intoxication (5), scenario runner (1), simple life (1): failed once in the final run. They passed on rerun on the live
  tree (44 of 44 in the three files together) and on HEAD-plus-this-change (44 of 44). Not reproduced, so treated as
  transient.
- Concurrency speed (1): `test_a_slow_provider_is_faster_when_decided_concurrently...` also fails on pure HEAD
  (speedup ratio 0.76 against a 0.75 limit, under current machine load). It is timing-sensitive, not caused here.

Bugs in my own tests found and fixed during this work:

- The loaded-game log test expected calls from three turns, but the consult gate made none, in the uninterrupted run
  too. The test now clears the gate's last consult turn before each step, as the other resume test does.
- The resume test compared the provider's global call list. Residents are decided in a thread pool, so the order varies.
  The test now compares calls per resident. The thread-continues assertion now checks each resident's first call after
  the stop, where it had checked the last call of one resident (that call can be a thread's first).
- The default-path test compared a relative path with an absolute one. It now compares resolved paths.

## Limits

- All LLM tests use `FakeProvider` (in `tests/llm_stub.py`) or the loopback stub. No live provider and no network.
- The game save and resume test runs 6 turns with 2 LLM residents. A long run was not run. Nothing is claimed about
  performance or balance.
- `llm_budget_for` merges spend by maximum. It is exact when the residents share one budget (`build_llm_town`). With
  separate budgets (`create_game` gives each LLM resident its own), the day counts are exact, but spend is the largest
  single resident's spend, not the total. `create_game` sets no spend cap, so nothing is decided from that number there.
- A loaded game gets a new log file with a new run id. It does not continue the log file of the run that was stopped.
  The chain of the stopped run is not linked to the new one.
- The restored backend's log is not part of the checkpoint. Loading attaches a new log (see `llm_log`, `llm_log_dir`).
- `pack` for an LLM backend without an autopilot is not stored (it has no gate). This has no effect on decisions.
- The untracked `game_persistence.py` carries the LLM branch. If that file is rewritten without the hook, LLM games
  cannot be saved again, and the game-level tests skip or fail.
- The concurrency level is stored in the checkpoint. The thread pool's scheduling is not part of the state.

## Open questions

1. Owner of `bigville/game_persistence.py`: accept the hook above, and commit the file or move the hook into a committed
   module. Until then the LLM branch exists only in the untracked file.
2. `bigville/learning_eval.py` builds its LLM arm with an explicit `log_path` (default `None`, so no log). It does not
   go through `create_game` or `build_llm_town`, so the default does not reach it. Should its LLM arm use `attach_default`?
3. A loaded game starts a new log file. Should a resumed run instead continue the stopped run's file (the chain
   verifies, and the file keeps one record sequence)? That needs the log path in the checkpoint.
4. Is "spend by maximum" in `llm_budget_for` acceptable for separate budgets, or should `create_game` share one budget
   for its LLM residents?
