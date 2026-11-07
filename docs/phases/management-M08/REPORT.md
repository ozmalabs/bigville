# Management M08 report: checkpoints and forks

## Baseline

- Base: `43869d5d96241f34fd2f2d60868781752cbd3aec` (`Update backend and checkpoint phase status`).
- Game checkpoint prerequisite `e5789fe2c80b1c8b02ad7bfbc15a927f94b3529e` is an ancestor of the base.
- Initial worktree status was clean. Python 3.13.5, pytest 9.0.2, NumPy 2.4.4, and Playwright were available.
- Before edits, `python3 -m pytest -q tests/test_bigville_game_persistence.py tests/management/test_runs.py tests/management/test_lifecycle.py tests/management/test_reports.py` passed: 27 passed, 1 skipped.

## Changes

- Added checkpoint creation under each run's serialized runtime lock. A checkpoint waits for any current step to finish, then saves the complete game with `save_game_checkpoint`; it never saves only world state. Runs without an initialized game and runs at `starting` or `waiting` return an explicit unavailable error.
- Checkpoints are stored under `DATA_DIR/checkpoints/<run-id>/<checkpoint-id>`. Public immutable metadata records schema, timestamp, turn, config hash and resolved backend profile IDs/revisions, without exposing filesystem paths or credentials. Registry loading validates checkpoint metadata before use.
- Added `GET`/`POST /runs/{id}/checkpoints` and `POST /runs/{id}/checkpoints/{checkpoint-id}/fork`. Fork verifies/restores the checkpoint before creating a distinct run, retains config and checkpoint provenance, and starts paused (or completed when the inherited turn limit is already reached). Parent and child game state are independent. A restarted run remains failed; saved checkpoints remain available for verified forks.
- Checkpoint and run IDs are validated as opaque generated identifiers before filesystem paths are constructed. Corrupt artifacts, invalid IDs, persistence failures, and restoration failures return explicit errors without creating a child. Provider-owned resident minds are rejected before any artifact is written because this service does not configure the Ocelot resident restore loader. LLM/Ocelot and any other unsupported backend classes are rejected before saving; the UI disables capture for these profiles and explains the limitation. Built-in simple backend runs use the engine's game checkpoint serializer.
- Save and restore exception details are not returned to the management API. Errors retain the exception class and generic context, while suppressing raw provider text and artifact paths. Registry validation rejects malformed persisted run IDs and checkpoint IDs before they can affect artifact paths.
- Added run-page checkpoint listing, create and fork controls, responsive styling, and README documentation for storage, restart and provider limitations.

## Verification

Final phase-targeted checks:

```text
python3 -m pytest -q tests/management/test_checkpoints.py tests/management/test_checkpoints_browser.py tests/test_bigville_game_persistence.py
15 passed, 1 skipped in 7.26s
```

The final full management and game-persistence gate passed:

```text
python3 -m pytest -q tests/management tests/test_bigville_game_persistence.py
116 passed, 1 skipped in 58.54s
```

Coverage includes real save/restore parity, fork independence, concurrent step/checkpoint serialization, provider-owned mind rejection before save, unsupported backend rejection (including an M10 LLM profile), corrupt artifacts, malformed metadata and run IDs, restart recovery, sanitized HTTP errors, and traversal denial. Playwright verified checkpoint creation and forking through the UI. The skipped test is the existing optional persistence test. `git diff --check` passed.

The shared worktree also contains a supervisor-applied correction to `tests/management/test_shell_browser.py`; it is unrelated to M08 and should not be included with M08 changes.
