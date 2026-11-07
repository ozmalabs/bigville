# M06 implementation report

Base: `f090e27` (with committed agent-view prerequisite `387f46b`). No commit created.

## Delivered

- Added run-scoped referee and agent view endpoints. `RunRegistry.get_run_view` serializes access with the run runtime lock. Referee requests call `game.snapshot()`; agent requests call only `game.agent_view(actor, mode="agent")` and return the selected run metadata and that view.
- Added a live run panel with current state, legal lifecycle commands, agent selection, explicit perspective selector, population list, and resident detail. The UI polls the selected run and ignores responses after a view revision changes.
- Reused the existing Phaser renderer inside a read-only management iframe. It receives referee snapshots from the parent and suppresses game mutations. The standalone `/game` route and its state/turn flow are unchanged; `game.js` has only a small snapshot update hook.
- Added safe static serving for the renderer's existing game assets. Mapless runs show a clear fallback.
- Added a delayed-response browser regression: while a referee request is held in flight, switching to agent aborts it, removes the iframe and clears resident data synchronously; releasing the stale response does not expose its sentinel in the page.
- Added a real HTTP endpoint test with two stepped runs. It verifies each referee endpoint remains scoped to its run and the agent response contains no other run's sentinel.
- Browser coverage confirms created, running, paused and stopped states expose the appropriate controls; paused stepping advances the displayed turn. It also confirms the reused Phaser iframe creates a visible canvas, the mapless fallback is shown for an empty map response, and active polling requests no referee view after switching to agent.
- Browser-aborted requests are handled quietly by the HTTP JSON writer.

## Verification

Ran the requested targeted command:

```text
python3 -m pytest -q tests/management/test_run_views.py tests/management/test_run_views_browser.py tests/test_bigville_server.py
7 passed in 14.00s
```

The agent boundary test confirms referee snapshots contain a sentinel while agent responses neither invoke `snapshot()` nor include that sentinel or world/character snapshot fields. It also checks that a newly created run has no available snapshot until stepped. The mapless fallback browser check supplies an empty map in the run-scoped referee response to exercise the fallback branch.

## Scope notes

The management UI is still local single-user only; perspective selection is a view boundary, not multi-user authorization. Lifecycle semantics continue to come from M04. The management renderer is read-only and loads the existing Phaser CDN dependency used by the game page.
