"""free_replies.py -- the free actions a reply carries (Phase 071c).

A reply's ``free_actions`` (reply_schema.to_wire) is a list of {action, target, params}. Each item names a row of the
pack's FREE_ACTIONS table. The world takes it as the same call a player's action makes (``world.free_action``), with
the reply's fields as its arguments. Free actions use no major action and no tick. The simple backends never produce
them.

    apply_all(game, actor, items) -> [outcome, ...]
    last_free(game, actor)        -> the actor's most recent free outcome, or None

An outcome is {turn, action, applied, reason, seen_major} and, for an applied glance, {sound, place}. ``reason`` is a
REFUSAL_REASONS code when the item is refused. ``seen_major`` is the resident's major outcome when the free action ran.
The newest outcome per resident is kept on the game object (it is not in the checkpoint). The agent view shows it as
``last`` when no major outcome has been published since it ran (see domains/agent_view.py).

ROUTES maps every FREE_ACTIONS name to the world's call. ``speak`` is also written as utterances, which go through the
game's speech path. ROUTES is the parity table the tests check: every FREE_ACTIONS name has a route here.
"""
from __future__ import annotations

from domains.pack import load_pack

# The world's free_action call for each FREE_ACTIONS name: (name, target, params) -> (world action, args, kwargs).
# The arguments are positional where the world's dispatcher reads args[0] or args[1] eagerly (reply, give_note,
# accept by request, decline); every route passes what the dispatcher reads.
ROUTES = {
    "speak": lambda target, params: ("speak", (target,), {"content": str(params.get("text", ""))}),
    "reply": lambda target, params: ("reply", (target, str(params.get("text", ""))), {}),
    "write_note": lambda target, params: ("write_note", (str(params.get("text", "")),), {}),
    "give_note": lambda target, params: ("give_note", (target, params.get("note")), {}),
    "accept": lambda target, params: (
        ("accept", (), {"item": params["item"], "giver": params.get("giver", target)})
        if params.get("item") is not None else ("accept", (target,), {})),
    "decline": lambda target, params: ("decline", (target,), {}),
    "set_intensity": lambda target, params: ("set_intensity", (), {"intensity": params.get("intensity")}),
    "stop": lambda target, params: ("stop", (), {}),
    "glance": lambda target, params: ("glance", (), {"target": target}),
}


def _store(game) -> dict:
    return vars(game).setdefault("free_outcomes", {})


def last_free(game, actor):
    """The actor's most recent free outcome (a copy), or None."""
    outcome = vars(game).get("free_outcomes", {}).get(actor)
    return None if outcome is None else dict(outcome)


def _sleep_code(world, actor):
    check = getattr(world, "_sleep_code", None)
    return check(actor) if callable(check) else None


def _glance_refusal(world, actor, target):
    """The reason a glance is refused before the world is asked, or None. The world refuses the rest (not_possible)."""
    body = world.body_of(actor)
    if body is None:
        return "wrong_target"
    if not isinstance(target, str) or body.signal_named(target) is None:
        return "unknown_target"
    return _sleep_code(world, actor)


def _glance_probe(world, actor, target):
    """The sound and place of the glanced feeling, as the body now resolves it (the glance is in place until the next
    tick). Reads the body's own rows; no state changes."""
    body = world.body_of(actor)
    source = body.signal_named(target)
    for row in body._derive()["sources"]:
        if row["source"] == source:
            return {"sound": row.get("sound") or None, "place": str(row.get("where", ""))}
    return {}


def _refuse(turn, action, code):
    return {"turn": turn, "action": action, "applied": False, "reason": code}


def apply_one(game, actor, item) -> dict:
    """Apply one free action item for ``actor`` now (no tick). Returns and stores its outcome."""
    world = game.world
    turn = int(world._turn)
    seen_major = world.last_outcome(actor)   # the major outcome at this moment (see agent_view: which is newer)
    name = str(item.get("action", ""))
    target = item.get("target") if isinstance(item.get("target"), str) else None
    params = dict(item.get("params") or {})
    table = load_pack(world.data_pack)["FREE_ACTIONS"]
    if name not in table or name not in ROUTES:
        outcome = _refuse(turn, name, "unsupported")
    elif name == "glance" and _glance_refusal(world, actor, target):
        outcome = _refuse(turn, name, _glance_refusal(world, actor, target))
    else:
        method, args, kwargs = ROUTES[name](target, params)
        try:
            result = world.free_action(actor, method, *args, **kwargs)
        except (KeyError, TypeError, ValueError):
            # The world rejects a malformed argument (for example a note that does not exist). The refusal is the
            # resident's outcome; the turn goes on.
            result = False
        applied = result is not None and result is not False
        outcome = {"turn": turn, "action": name, "applied": applied,
                   "reason": "" if applied else "not_possible"}
        if applied and name == "glance":
            outcome.update(_glance_probe(world, actor, target))
    outcome["seen_major"] = seen_major
    _store(game)[actor] = outcome
    return dict(outcome)


def apply_all(game, actor, items) -> list[dict]:
    """Apply each free action item in order. Items that are not dicts are skipped."""
    return [apply_one(game, actor, item) for item in items or [] if isinstance(item, dict)]

