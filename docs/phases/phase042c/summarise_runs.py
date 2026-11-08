"""summarise_runs.py -- one table from the duty_run.py summaries (Phase 042c).

    python3 docs/phases/phase042c/summarise_runs.py DIR [DIR ...]

Each DIR holds duty_summary.json from duty_run.py. Prints, per run and day: the hours after sunset until all four
lamps are lit, the hours after sunrise until all four are dark, the lamplighter's lowest energy and highest hunger,
his eat, sleep and duty ticks, and the end state (alive, residents alive, oil).
"""
from __future__ import annotations

import json
import os
import sys


def main(argv=None):
    dirs = (argv if argv is not None else sys.argv[1:])
    if not dirs:
        raise SystemExit(__doc__)
    for path in dirs:
        with open(os.path.join(path, "duty_summary.json"), encoding="utf-8") as fh:
            s = json.load(fh)
        role = s.get("role_identity")
        print(f"## {os.path.basename(os.path.normpath(path))}: seed {s['seed']}, role_identity {role}, "
              f"root {os.path.basename(s['root'])}, {s['days']} days")
        print("| day | sunset h | lit: h after sunset | sunrise h | dark: h after sunrise | lights | douses | "
              "min energy | max hunger | eat ticks | sleep ticks | duty ticks | lamplighter alive | town alive |")
        print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for d in s["days_detail"]:
            print("| {day} | {sunset_hour} | {dusk_all_lit_hours_after_sunset} | {sunrise_hour} | "
                  "{dawn_all_dark_hours_after_sunrise} | {lamp_lights_applied} | {lamp_douses_applied} | "
                  "{lamplighter_min_energy} | {lamplighter_max_hunger} | {lamplighter_eat_ticks} | "
                  "{lamplighter_sleep_ticks} | {lamplighter_duty_ticks} | {lamplighter_alive_at_day_end} | "
                  "{town_alive_at_day_end} |"
                  .format(**d))
        print(f"\nend: lamplighter alive {s['lamplighter_alive_end']}, residents alive "
              f"{s['residents_alive_end']} of {s['residents']}, oil {s['oil_end']}, lamps lit {s['lamps_lit_end']}")
        print(f"lamplighter actions: {s['lamplighter_actions']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
