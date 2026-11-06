# Checkpoint prerequisite candidate report

## Provenance and scope

- Base commit: `1b3027495a9f075a091f1e5992aaf3934b2ed225` (`management-checkpoint-base`).
- Candidate worktree: `/home/matt/ozmadev/bigville-management-checkpoint`.
- Source snapshot: uncommitted persistence work in `/home/matt/ozmadev/bigville` at main `HEAD` `fb390cdc6b595024fbbdb3b5e164274703cb90bb`.
- Main was not edited or staged. This candidate is uncommitted and has no commit.
- Scope is limited to `bigville/game_persistence.py`, `bigville/world_persistence.py`, the three persistence tests listed below, and the checkpoint-only diff to `bigville/runtime.py`. No compatibility edits were needed.
- The copied files' hashes matched their source files in main when copied and were rechecked after testing.

## Snapshot hashes

SHA-256:

| File | Hash |
|---|---|
| `bigville/game_persistence.py` | `241aede4584e8ddcd2d4f57978bc3ba3ac8c7e713abe90f46b095ea0cc11973f` |
| `bigville/world_persistence.py` | `378f1ebd72c791f810c03e4f5046f88133b9eb536b2db4a0235a2051ae438c95` |
| `tests/test_bigville_graph_persistence.py` | `16ff3d80fee4725acc987916b0d8d12d784bea957291248f9ad4ca644b4c8b21` |
| `tests/test_bigville_world_persistence.py` | `97160ba8a682c056fcdbd17d54ded95d9ffc8b739d6e4cc923ca048f224eaa4c` |
| `tests/test_bigville_game_persistence.py` | `2f98feb2ccadd104ade26d7d8752ff198890415b4a4d661a85884b2ebc6bf423` |
| `bigville/runtime.py` (candidate full file) | `48656a989ccc16602b3ddcf96c40e7e53889f9bd9a99df5679decc7df0301df7` |

The applied `bigville/runtime.py` patch hash is `64f11ee7853cc7d9397d374830044a7b3f80243d762848baecb739edfb3c24e0`. It adds typed checkpoint encode/decode helpers and strict `BigvilleGraph` serialization/deserialization.

## Verification

- `python3 -m pytest -q tests/test_bigville_graph_persistence.py tests/test_bigville_world_persistence.py tests/test_bigville_game_persistence.py tests/test_phase052_agent_view.py` — **41 passed, 1 skipped**.
- `python3 -m pytest -q tests/test_phase057_tui.py` — **48 passed**.
- `git diff --check` — clean.

The skipped case uses `pytest.importorskip` for `worlds.bigville_ocelot_adapter`; the Ocelot checkout is unavailable in this environment. `tests/test_mixed_ocelot_checkpoint_parity.py` was not included in this bounded snapshot and was not run. The core persistence and agent-view tests pass without compatibility changes.

## Limitations and handoff

This is a reviewed prerequisite candidate, not an integration commit. The persistence code captures broad `BigvilleWorld` state, so review and regression testing remain necessary when it is integrated with later world changes. Ocelot provider checkpoint parity still requires an environment with the adapter installed. Do not treat this candidate as satisfying the M08 committed-prerequisite gate until the supervisor reviews and commits the integration.
