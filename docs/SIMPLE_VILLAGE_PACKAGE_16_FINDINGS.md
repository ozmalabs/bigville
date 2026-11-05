# Package 16: room-scale restaurant policy adaptation

Run the focused fixture with:

```sh
PYTHONPATH=. pytest -q tests/test_simple_room_policy.py
```

The fixture starts two identical unattended restaurant rooms. Each has Ruth,
Nell, a water cup and a menu card on the same table. Ruth uses the simple
backend in both runs. One scenario profile interprets moving the cup into her
physical custody as a preferred action; the other keeps the bounded default,
which does not select room-object movement. After one real game turn, the cup
is held by Ruth in the first room and remains on the table in the second.
The selected object and destination, action result and resulting physical
location are asserted. Both objects are ordinary physical objects.

No restaurant service protocol is encoded in the world: there are no laws,
policies or charters in the fixture, and moving the cup does not claim an
order, agreement, payment or completed service. The different interpretation
is expressed only as a simple policy preference over an existing affordance.

Focused result: 2 passed.

## Limitation

This fixture covers a bounded room-scale action and a refusal to act. It does
not model menus, orders, serving, payment, consent or social response. Those
would require additional actor-held policies and observable actions; the test
makes no claims about them.
