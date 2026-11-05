# Package 13: norms and enforcement boundary

Fixture: `scenarios/norms_property_sharing.json`; focused checks:
`tests/test_simple_norms_enforcement.py`.

Run with:

```sh
PYTHONPATH=. pytest -q tests/test_simple_norms_enforcement.py
```

The package uses two real residents in the same compact room, one visible cup
on the shared table, and identical initial physical state in paired runs. Ada's
backend holds either a `communal` policy (leave the cup in the shared location)
or a `private` policy (move it into her own physical holding). The physical
object and movement affordances are the same under both policies. In the
private run, Ben's backend reacts only after its context contains the situated
physical event naming Ada and the cup's table-to-Ada movement. Ben asks Ada to
return the cup; Ada's backend hears the request and chooses a real move-object
action back to the table. The world does not compel or adjudicate the return.

The unseen-action control moves Ben beyond witnessing range. Ada still has
the same physical option and moves the cup. Ben receives no event and issues
no request; arriving later exposes only the current physical scene and does
not reconstruct or sanction the earlier action. Failed object movement also
creates no observation event. Context reads are checked to be observational,
and physical object movement remains a location change rather than a minted
or destroyed item.

Generic physical object affordances now enter the normal actor affordance
boundary. `SimplePolicy.allow_object_moves` defaults to false so publishing
ordinary object movement does not make the default resident policy rearrange
room objects spontaneously; scenario policies can opt in. The world reports
only movement and endpoints. Norm interpretation and the social request remain
backend-held.

Reproduce the focused gate with:

```sh
PYTHONPATH=. pytest -q tests/test_simple_norms_enforcement.py
```

The test demonstrates a bounded policy contrast and a voluntary, requested
physical return. It does not establish that enforcement is coercive or that
either norm is fair, lawful, or generally accepted; those meanings remain with
the agents.
