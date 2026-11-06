"""Joint actions (Phase 047): several people doing one thing at once.

Pure functions, no world state and no randomness. Every number is passed in from the pack's JOINT_TASKS table
(domains/bigville_entities.JOINT_TASKS), so the same inputs always give the same outputs.

Team capability is the summed force of the members times a coordination factor that falls as the group grows:
coordination(n) = 1 / (1 + loss x (1 - skill_relief x skill) x (n - 1)). A group of one has coordination 1.0, so a
lone resident keeps the committed numbers. Summed capability grows with n but by less each time, so a third worker adds
less than a second did.
"""
from __future__ import annotations

import math


def clamp(value, low, high):
    return max(low, min(high, value))


def coordination(n, skill=0.0, loss=0.1, skill_relief=0.5):
    """The share of the summed force a group of n keeps. A skilled group at the task loses less to coordination."""
    members = max(1, int(n))
    s = clamp(float(skill), 0.0, 1.0)
    return 1.0 / (1.0 + float(loss) * (1.0 - float(skill_relief) * s) * (members - 1))


def team_term(forces, loss, skill=0.0, skill_relief=0.5):
    """(summed force, team term) for a group. The team term is the core's `team` input (Phase 050)."""
    total = sum(max(0.0, float(f)) for f in forces)
    if not forces:
        return 0.0, 1.0
    return total, coordination(len(forces), skill, loss, skill_relief)


def members_needed(force, demand, max_members, loss, skill=0.0, skill_relief=0.5):
    """The fewest people of this force who make the load's demand, up to max_members: 1 when one person is enough,
    None when even the largest group falls short."""
    if float(force) <= 0.0:
        return None
    for members in range(1, int(max_members) + 1):
        total = members * float(force) * coordination(members, skill, loss, skill_relief)
        if total >= float(demand):
            return members
    return None


def carry_pace(rho, pace_cap):
    """Cells a joint carry moves in one turn: none while the group's capability is short of the load (rho < 1), else
    floor(rho), at most pace_cap. A lighter load per person moves faster."""
    if float(rho) < 1.0:
        return 0
    return int(min(int(pace_cap), math.floor(float(rho))))


def crew_factor(members, crew_penalty, skill=0.0, loss=0.1, skill_relief=0.5):
    """The progress multiplier a crewed job gets from its workers present (the worker counts as one).

    A lone worker on a crewed job crawls at crew_penalty. Two or more share the labour: members x coordination(members),
    so the progress per tick rises with each person by less than a full worker's labour."""
    count = max(1, int(members))
    if count == 1:
        return float(crew_penalty)
    return count * coordination(count, skill, loss, skill_relief)


def chebyshev(a, b):
    """Grid distance in cells (the world's own distance for reach and sight)."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))
