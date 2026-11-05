# Package 5: movement and access

The focused fixture runs proposed actions through actual `BigvilleGame.step()`
turns. A walker routes around a removed walkable tile, then receives a visible
failed result when its destination is blocked. The test also checks that the
actor's observed starting position is the pre-action position. Object movement
now requires the source to be accessible, the destination to exist, and rejects
container self/descendant cycles before changing either object-location index.

The object fixture uses the closed Monopoly box: its contents cannot be moved
until the container is opened, and failed attempts preserve every location.
Existing turn-level physical-object behavior, including moving the accessible
box to an actor, remains covered by the adjacent board-game regression tests.

Focused verification:

```sh
PYTHONPATH=. pytest -q tests/test_simple_movement_access.py tests/test_bigville_board_games.py
```

Result: 11 passed. Map routing is currently represented by walkable-cell
membership; the test removes one cell from that graph to model an obstacle.
Reachability for generic objects is currently container/access based because
authored object locations are labels such as `table`, `world`, actor IDs, or
container IDs rather than map coordinates. Coordinate-backed objects may now
opt in with `cell: [x, y]` or `x`/`y`; those objects are visible and movable
only within one walkable step. Direct handovers to another resident also
require the residents to be within one walkable step, and impossible handovers
are omitted from affordances. Legacy `table` and `world` objects without
coordinates remain shared room fixtures. The Monopoly regression now places
the receiver next to the actor before checking a direct handover.

Held objects inherit the current holder's cell, and objects inside containers
inherit the container's current cell. Opening a placed container checks its
reach. Affordances omit distant actor targets, inaccessible containers, closed
containers, and containment cycles. Regression coverage includes a remote open
attempt, pickup followed by movement, and placement into a nearby open
container. A turn-level pickup, actor move, and drop sequence persists the
dropper's final cell on the object, so later observations use the dropped
position rather than its initial authored cell.
