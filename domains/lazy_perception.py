"""Phase 065c: the lazy agent view (the LLM's prompt) takes its perceived parts from the perceiver.

`build_lazy_agent_view` (domains/agent_view.py) is the view of a backend with `wants_agent_view` (the LLM). It is built
from `world.observe`, which has no perceiver record, so with PERCEPTION on an LLM resident was shown the truth where the
full view showed the percept. `perceived` replaces the lazy view's people, things, heard sentences and written marks
with the full view's: the same `_around` helpers (perceiver.percept, impairment.distort, impairment.mishear,
reading.writing_rows) that build_agent_view uses. The lazy view's place handles (`cell:x,y`, which a move needs), its
seen rows and its capabilities are kept as they were.

`perceived` is called only when PERCEPTION.enabled is on. Off, the lazy view is built exactly as before.

The truth stays out of the agent view. The perceiver's referee rows (both the truth and the percept) go to the `log`
that `referee_perception` puts in the referee block, which the prompt never reads.
"""
from __future__ import annotations

from domains import agent_view, impairment, perceiver

HEARD_LAST = 10   # the lazy view's own bound on heard sentences (the packet trims to speech_max as well)


def perceived(game, actor, obs, around, known, pack):
    """Returns (around, rec, log). `around` is the lazy view's around with people, things, heard and writing replaced
    by the perceiver path; `rec` is the perceiver record and `log` the referee rows of this view."""
    backend = getattr(game, "backends", {}).get(actor)
    rec = perceiver.record(game, actor, perceiver.declared(backend, pack), pack)
    log = []
    full = agent_view._around(game, actor, pack, known, rec, log)
    impairment.note_view(game, actor, rec, log, pack)
    things = list(full.get("things") or [])[:agent_view.LAZY_THINGS_CAP]
    used = {row["handle"] for row in things if row.get("handle")}
    # Place handles are not perceived objects: a move needs them, so the lazy view keeps them after the things.
    for handle, label in agent_view._lazy_destinations(obs):
        if handle in used or len(things) >= agent_view.LAZY_THINGS_CAP + agent_view.LAZY_PLACES_CAP:
            continue
        used.add(handle)
        things.append(agent_view._check_keys("thing", {"handle": handle, "what": label}, pack))
    out = dict(around)
    out["people"] = list(full.get("people") or [])[:agent_view.LAZY_PEOPLE_CAP]
    out["heard"] = list(full.get("heard") or [])[-HEARD_LAST:]
    out["things"] = things
    out.pop("writing", None)
    if full.get("writing"):
        out["writing"] = list(full["writing"])
    return agent_view._check_keys("around", out, pack), rec, log


def referee_perception(game, rec, log, pack):
    """The referee block's perception entry, in the same shape build_agent_view writes it."""
    return {"faculties": dict(rec["modes"]), "perceiver": perceiver.summary(rec), "subjects": log,
            **impairment.referee_block(game, log, pack)}
