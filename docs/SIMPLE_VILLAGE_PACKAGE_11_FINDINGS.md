# Package 11: observation and communication

Fixture: `tests/test_simple_observation_communication.py`, fixed setup in code
(Ada at `(1, 1)`, Ben initially at `(2, 1)`, Cy at `(1, 2)`). The three actors
use deterministic simple-backend policies. Ada sends the same structured
request twice; the first is out of range, then Ben moves into Ada's cell and
the second is delivered. Ben responds from the delivered observation on the
following turn. Cy is not a recipient and receives no record. The test checks
actor-context privacy and inventory/major-action invariants.

Reproduce with:

```sh
python -m pytest -q tests/test_simple_observation_communication.py
```

Result: 2 tests pass. Speech is stored as a communication record; the world
does not act on the request or transfer an object. Delivery currently requires
co-location (`speak` sets `heard` from exact position equality), so “in range”
in this package is the same map cell. A targeted event outside that range is
retained but is not included in `heard_utterances`. The recipient's simple
policy sees delivered speech at its next decision boundary; same-turn delivery
does not change an already gathered context. The private-state check confirms
that an arbitrary actor attribute is not copied into another actor's context.

Scope limitation: the secret check covers the actor-context observation
projection, not every exported/debug view. No change to shared implementation
was needed for this package.
