# M11B report — Human-controlled sessions

## Base and environment

- Base commit: `fdc1f156f4e0b5fab24d73e2c2954b60a882720a`
- Python: 3.13.5
- pytest: 9.0.2
- Worktree was clean before implementation. No commit was created.

## Delivered

- Draft resolution now accepts `autonomous: false` only with a player present in the resolved authored or generated cast. Built-in `town100` membership is checked against the seeded real world cast. Autonomous drafts reject a player field.
- The selected resident is recorded as the `human` backend in canonical config and run assignments. Launch passes player and mode into `create_game`; player selection remains mutually exclusive with autonomous mode.
- Human backends are placed first in `BigvilleGame.backends` decision iteration. This prevents NPC decisions from being computed and discarded while the human backend waits. The engine's `turn_order` remains unchanged.
- Added run-scoped `GET /runs/{id}/player-prompt` and `POST /runs/{id}/player-input`. The prompt contains only the selected player's words-only agent view and current advertised action handles, or the engine's offered contest reactions. Input requires the current opaque token and turn. Action handles are re-resolved against the current filtered agent view and current engine affordances; arbitrary actors, params, stale tokens, and unoffered reactions are rejected.
- Human input uses `HumanBackend.submit` for actions and `submit_reaction` for contests, preserving the engine's suspended-turn behavior. Completed turns request the next prompt without auto-advancing the world. Turn limits complete the session without requesting another player action. If the selected player dies, the session ends as completed.
- Agent views in human runs are restricted to the configured player. The human run opens in resident perspective by default; referee inspection remains a separate explicit choice.
- Added run-mode/player selection, resolved-cast loading, review provenance, and agent-view action/reaction controls to the browser UI.

## Verification

Phase tests and the named follow-up human, run-view, contested-reaction, and server tests:

```text
python3 -m pytest -q tests/management/test_human_runs.py tests/management/test_human_runs_browser.py
7 passed in 4.48s

python3 -m pytest -q tests/management/test_human_runs.py tests/management/test_human_runs_browser.py tests/management/test_runs.py tests/management/test_run_views.py tests/management/test_run_views_browser.py tests/test_phase029_contest.py tests/test_bigville_server.py
43 passed in 23.41s

python3 -m pytest -q tests/management/test_human_runs.py tests/management/test_human_runs_browser.py tests/management/test_backends.py tests/management/test_cast_generation.py tests/management/test_templates.py
39 passed in 8.84s
```

`git diff --check` passed. The full repository suite was not run.

## Files

- `bigville/game.py`: wait-safe backend ordering.
- `bigville/management/drafts.py`, `runs.py`, `http.py`: human mode resolution, waiting/input lifecycle, and run-scoped endpoints.
- `bigville/management/static/index.html`, `management.js`, `management.css`: mode/player controls and player input UI.
- `tests/management/test_human_runs.py`, `test_human_runs_browser.py`: real human turns, stale/invalid input, restricted agent views, actual contested reaction, turn limit, NPC decision count, and browser flow.

## Limits

- The player UI submits only engine-advertised physical affordances and offered contest reactions. It does not expose free-text speech, arbitrary action parameters, or a general-purpose response object.
- This remains a local single-user management service. The referee perspective is an operator inspection view, not an authorization boundary.
