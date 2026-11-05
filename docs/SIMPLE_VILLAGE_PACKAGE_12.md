# Package 12: exchange and consent audit

## Focused fixture

`tests/test_package12_exchange_consent.py` uses two residents, one apple, and
two coins. It checks physical reach and possession controls, backend-driven
acceptance/refusal and handover, an unattended-object control, and the legacy
purchase gate. Run it with:

```sh
PYTHONPATH=. pytest -q tests/test_package12_exchange_consent.py
```

Current result: 6 passed. The fixture runs the same offer with two seller
backend policies: one says accept and transfers the apple, the other says
refuse and leaves physical state unchanged. Both start with `sell_willing=0`
and the buyer's two coins remain unchanged, so neither price nor the hidden
seller willingness field governs the new handover path.

## Findings

* A physical `major_action("give", ...)` between co-located actors conserves
  inventory and works without an offer, price, payment, or recipient decision.
  It rejects actors in different cells and rejects a giver who lacks the item.
  This is a useful physical handover primitive, but its current API direction
  makes it look like a voluntary gift.
* Paid person-to-person purchase uses `_purchase_utterances` and the seller's
  `sell_willing` attribute as world-side gates in `_person_purchase`
  (`worlds/bigville_world.py`, around line 3220). `_actor_options` also reads
  `sell_willing` to decide whether a buyer can see the trade option. That is
  hidden commercial intent controlling both cognition inputs and transfer
  resolution.
* The neutral backend `transfer(source, recipient, kind, amount)` now performs
  a physical actor-to-actor handover with reach, source possession, and
  recipient capacity checks. It does not consult `sell_willing`, price, or
  speech agreement. `enact_plan(action='give')` still maps the legacy buyer
  affordance to a purchase wrapper; the new cognition-owned exchange fixture
  uses `transfer` explicitly.
* The test runs actual game turns: Ada offers; Ben hears it and his backend
  chooses either acceptance plus transfer or refusal with no transfer. This
  covers an agent-held policy causing an observable action. The norm-violation
  control uses `move_object` to move an accessible unattended object into Ben's
  physical custody. It does not pretend that an agent can silently take
  another resident's carried inventory.
* Held-inventory taking remains unsupported: `take` returns false because the
  physical model has no contested resistance mechanism. That is a limitation
  of this scenario, not a world enforcement of property rights. A future
  contested-action model can make taking physically possible and let agents
  interpret it under their own norms.

## Minimal design dependency

Keep trade policy in cognition: buyer proposes; seller observes and chooses
accept or refuse; acceptance can cause the ordinary handover action. A taking
policy can choose an applicable physical action without consent; observers can
interpret the observed result under their own norms. Remove purchase speech,
`sell_willing`, and price from physical transfer resolution. Price and
agreement may remain as agent-held beliefs and speech content. The new
`transfer` path satisfies this physical requirement; the older `give` purchase
wrapper and its affordance derivation still need separation from it.

The world need not know that an offer was accepted. A trace can record
observable proposal/response utterances, selected physical action, transfer
result, and inventory/coin deltas. The fixture compares accepting and refusing
backend policies on identical physical state. It also exercises moving an
accessible unattended object into Ben's custody; it does not claim held-item
theft works without a resistance mechanism.
