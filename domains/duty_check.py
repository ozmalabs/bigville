"""duty_check.py -- self-test checks for the DUTIES table (Phase 042c).

Called from bigville_entities.check_consistency. A duty is a job's standing task that the world can see is due
(bigville/backends/duty.py reads it as a drive). The checks: each duty names a JOBS entry and a LABOUR_TASKS task,
its acts are MAJOR_ACTIONS, its valuations are in range, and the day-and-night lamplighter job has a duty whose
lead equals the lead the world uses for the walk before dusk.
"""
from __future__ import annotations


def check(errors, warnings, info, *, duties, daynight, jobs, labour_tasks, major_actions, time):
    where = "DUTIES"
    half_day = float(time["hours_per_day"]) / 2.0
    for job, spec in duties.items():
        here = f"{where}[{job}]"
        if job not in jobs:
            errors.append(f"{here}: '{job}' is not a JOBS entry")
        task = spec.get("task")
        if task not in labour_tasks:
            errors.append(f"{here}.task: '{task}' is not a LABOUR_TASKS entry")
        acts = spec.get("acts") or []
        if not acts:
            errors.append(f"{here}.acts: a duty names at least one major action")
        for act in acts:
            if act not in major_actions:
                errors.append(f"{here}.acts: '{act}' is not a MAJOR_ACTIONS entry")
        lead = float(spec.get("lead_hours", 0.0))
        if not 0.0 < lead < half_day:
            errors.append(f"{here}.lead_hours: must be positive and under half a day")
        if not 0.0 < float(spec.get("due_floor", 0.0)) <= 1.0:
            errors.append(f"{here}.due_floor: must be in (0, 1]")
        if float(spec.get("ramp_hours", 0.0)) <= 0.0:
            errors.append(f"{here}.ramp_hours: must be positive")
        if float(spec.get("in_place_bonus", -1.0)) < 0.0:
            errors.append(f"{here}.in_place_bonus: must be 0 or more")
        if float(spec.get("score_weight", 0.0)) <= 0.0:
            errors.append(f"{here}.score_weight: must be positive")
    lamp_job = daynight.get("lamplighter_job")
    if lamp_job:
        spec = duties.get(lamp_job)
        if spec is None:
            errors.append(f"DUTIES: the lamplighter job '{lamp_job}' has no duty (Phase 042c)")
        elif float(spec.get("lead_hours", 0.0)) != float(daynight["lamplighter_dusk_lead_hours"]):
            errors.append(f"DUTIES[{lamp_job}].lead_hours: must equal DAYNIGHT.lamplighter_dusk_lead_hours "
                          f"({daynight['lamplighter_dusk_lead_hours']}), the walk the world offers before dusk")
        elif set(spec.get("acts") or []) != {"light", "douse"}:
            errors.append(f"DUTIES[{lamp_job}].acts: the lamp duty names light and douse")
    if duties:
        info.append(f"DUTIES: {len(duties)} job duty(ies): {', '.join(sorted(duties))}")
