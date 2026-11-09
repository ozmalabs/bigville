#!/usr/bin/env python3
"""balance_run.py -- per-day balance metrics for the default Bigville town.

Runs `create_game(scenario="town100", seed=SEED, default_backend="simple", autonomous=True,
ticks_per_period="world", affordance_mode="menu", llm_log=False)` one step (one 15-minute tick) at a time
and writes one row per simulated day for each seed. It is the measuring instrument for the balance
programme (docs/FEATURE_PHASES.md, Programme G); it changes no game data.

Usage
    python3 tools/balance_run.py --seed 305000 --days 7 --out runs/base_305000.json --label base
    python3 tools/balance_run.py --seeds 305000,305001,305002 --days 7 --set CARRYING.stamina_per_move_unit=0.03
    python3 tools/balance_run.py --seed 305000 --ticks 20 --label smoke          # a short smoke run

Options
    --seed N          one seed (default 305000)
    --seeds A,B,...   several seeds, run one after another in this process (use with or without --seed)
    --days N          simulated days (default 7; one day = 96 ticks)
    --ticks N         simulate N ticks instead of days*96 (smoke runs; the last partial day is reported)
    --out PATH        write the JSON result here (always also printed as one JSON line per day)
    --label TEXT      a name for this run, stored in the output (default "base")
    --set TABLE.KEY=VALUE
                      lever override, repeatable. Mutates the default pack's table in place before the
                      town is built, so the world reads the new value. The key must already exist (a typo
                      is an error). Values are numbers. The effective value read back from the world is
                      recorded in the output under "effective". Only the default pack (bigville) is supported.

Output (JSON): {"label", "set", "effective", "days", "ticks", "runs": [{"seed", "elapsed_s", "rows", "summary"}]}
Each row is one day (0-based `day`):
    alive                       residents alive at the end of the day
    deaths_day / deaths_cum     deaths during the day / to date, by cause
    hunger_mean/p10/p90         hunger of the living at the end of the day
    store_food                  food units in town stock at the end of the day
    food_held                   food units in residents' inventories (living residents)
    meals_eaten, fetches        applied `eat` and `fetch` actions during the day
    work_starts                 applied `work` actions by recipe
    work_completions            jobs finished during the day by recipe (found at the day's last tick)
    food_produced               food units that completed jobs added to stock during the day
    energy_1700_mean/p10        energy (0-100) of the living at 17:00 (tick 44 of the day)
    energy_1700_share_lt35      share of the living below 35 energy at 17:00
    share_lt35_eod              share of the living below 35 energy at the end of the day
    cells_walked_per_resident   cells moved by all residents that day / residents alive at the day's start
    walk_attempts               applied `move` actions (a waiting tick counts as an attempt)
    walk_moved                  of those, the ticks in which the resident's cell changed
    walk_moved_share            walk_moved / walk_attempts
    walk_energy_per_cell        walking energy minted that day (points) / cells moved that day
    effort_energy_walk_share    walking energy / all effort energy minted that day
    move_refused                `move` actions the world refused (for example `exhausted`)
The low-energy line is 35 points, the simple policy's rest threshold (bigville/backends/cheap.py).

Instrumentation: the tool wraps the engine's `set_attr` and `add_edge_unchecked`, and the world's
`set_stock` and `_plan_inputs`. The wrappers only observe. If the world's internals are renamed, the tool
fails with an AttributeError rather than miscounting.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

LOW_ENERGY = 35.0          # the simple policy's rest threshold, in energy points (0-100)
TICKS_PER_DAY = 96         # packs/bigville/world/time.json ticks_per_day
SAMPLE_HOUR = 17.0         # the hour of the 17:00 energy reading


def _parse_sets(items):
    """Parse --set TABLE.KEY=VALUE into [(table, key, float_value)]."""
    out = []
    for item in items or []:
        left, sep, right = item.partition("=")
        table, dot, key = left.partition(".")
        if not sep or not dot or not table or not key:
            raise SystemExit(f"--set expects TABLE.KEY=VALUE, not {item!r}")
        try:
            value = float(right)
        except ValueError:
            raise SystemExit(f"--set value must be a number, not {right!r}")
        out.append((table, key, value))
    return out


def _apply_sets(sets):
    """Mutate the default pack's tables in place. Returns the values before the change."""
    from domains import bigville_entities as E
    before = {}
    for table, key, value in sets:
        tbl = getattr(E, table, None)
        if not isinstance(tbl, dict):
            raise SystemExit(f"--set: no table named {table!r} in the default pack")
        if key not in tbl:
            raise SystemExit(f"--set: table {table} has no key {key!r} (keys: {sorted(tbl)})")
        before[f"{table}.{key}"] = tbl[key]
        tbl[key] = value
    return before


def _percentile(sorted_values, fraction):
    if not sorted_values:
        return None
    index = min(len(sorted_values) - 1, int(fraction * len(sorted_values)))
    return round(sorted_values[index], 3)


def run_seed(seed, total_ticks, label):
    """Simulate one seed for `total_ticks` ticks and return {"seed", "elapsed_s", "rows", "summary"}."""
    from bigville.api import create_game
    from domains import bigville_entities as E

    started = time.time()
    g = create_game(scenario="town100", seed=seed, default_backend="simple", autonomous=True,
                    ticks_per_period="world", affordance_mode="menu", llm_log=False)
    w = g.world
    eng = w.eng
    names = list(w._actors)
    sample_index = int(round((SAMPLE_HOUR - float(E.TIME["start_hour"])) * TICKS_PER_DAY / 24.0))

    def attrs(name):
        return eng.node(w._actors[name])["attrs"]

    food_kinds = [k for k, spec in w._item_specs.items() if spec.get("food")]

    # ---- instrumentation (observation only)
    walk_points = collections.defaultdict(float)     # day -> walking energy minted (points)
    effort_points = collections.defaultdict(float)   # day -> all effort energy minted (points)
    day_now = [0]
    stock_buf = []
    completions = collections.Counter()              # (day, recipe) -> jobs finished
    food_added = collections.defaultdict(float)      # day -> food units added by finished jobs
    per = {n: collections.Counter() for n in names}  # per-resident counters (inspection)
    min_energy = {n: 100.0 for n in names}
    reached = {n: False for n in names}
    role = {n: str(eng.node(w._actors[n])["attrs"].get("role")) for n in names}
    work_cell = {}
    for n in names:
        a = eng.node(w._actors[n])["attrs"]
        wx, wy = int(a.get("work_x", -1)), int(a.get("work_y", -1))
        work_cell[n] = (wx, wy) if wx >= 0 else None
    store_cell = tuple(w.map_position_node(w._store))

    original_add_edge = eng.add_edge_unchecked

    def add_edge_unchecked(source, edge, target, *args, **kwargs):
        if edge == "exerted":
            node = eng.node(target)["attrs"]
            points = float(node.get("stamina_cost", 0.0)) * 100.0
            effort_points[day_now[0]] += points
            if str(node.get("body_use", "")) == "walk":
                walk_points[day_now[0]] += points
        return original_add_edge(source, edge, target, *args, **kwargs)

    eng.add_edge_unchecked = add_edge_unchecked

    original_set_attr = eng.set_attr

    def set_attr(node, key, value):
        result = original_set_attr(node, key, value)
        if key == "complete" and float(value) == 1.0:
            job = eng.node(node)
            if job["type"] == "Job":
                asp = eng.neighbours(node, "runs")
                recipe = eng.node(asp[0])["attrs"].get("name", "?") if asp else "?"
                completions[(day_now[0], str(recipe))] += 1
                actor = str(job["attrs"].get("canonical_actor", ""))
                if actor in per:
                    per[actor]["work_completions"] += 1
                food_added[day_now[0]] += sum(stock_buf)
                stock_buf.clear()
        return result

    eng.set_attr = set_attr

    original_set_stock = w.set_stock

    def set_stock(kind, qty):
        before = w.qty(kind)
        result = original_set_stock(kind, qty)
        delta = w.qty(kind) - before
        if delta > 0 and kind in food_kinds:
            stock_buf.append(float(delta))
        return result

    w.set_stock = set_stock
    original_plan = w._plan_inputs

    def plan_inputs(*args, **kwargs):
        stock_buf.clear()
        return original_plan(*args, **kwargs)

    w._plan_inputs = plan_inputs

    # ---- run
    rows = []
    deaths_seen = 0
    deaths_cum = collections.Counter()
    alive_at_day_start = len([n for n in names if w.is_alive(n)])
    day_cells = 0
    day_stats = collections.Counter()
    day_recipe_starts = collections.Counter()
    day_energy_1700 = None
    extinct = False
    last_positions = {n: tuple(w.actor_position(n) or ()) for n in names}

    def close_day(day, partial):
        nonlocal deaths_seen, alive_at_day_start, day_cells, day_stats, day_recipe_starts
        living = [n for n in names if w.is_alive(n)]
        new_deaths = w._deaths[deaths_seen:]
        deaths_seen = len(w._deaths)
        day_deaths = collections.Counter(str(d["cause"]) for d in new_deaths)
        deaths_cum.update(day_deaths)
        hunger = sorted(float(attrs(n).get("hunger", 0.0)) for n in living)
        energies = sorted(float(w.energy(n)) for n in living)
        store = sum(float(w.qty(k)) for k in food_kinds)
        held = 0.0
        for n in living:
            for kind, qty in w.inventory(n).items():
                if w._item_specs.get(kind, {}).get("food"):
                    held += float(qty)
        completed = {recipe: count for (d, recipe), count in completions.items() if d == day}
        moved = day_cells
        row = {
            "day": day,
            "partial_day": partial,
            "alive": len(living),
            "deaths_day": dict(day_deaths),
            "deaths_cum": dict(deaths_cum),
            "hunger_mean": round(sum(hunger) / len(hunger), 3) if hunger else None,
            "hunger_p10": _percentile(hunger, 0.1),
            "hunger_p90": _percentile(hunger, 0.9),
            "store_food": round(store, 1),
            "food_held": round(held, 1),
            "meals_eaten": day_stats["eat"],
            "fetches": day_stats["fetch"],
            "work_starts": dict(day_recipe_starts),
            "work_completions": completed,
            "food_produced": round(food_added.get(day, 0.0), 2),
            "energy_1700_mean": day_energy_1700["mean"] if day_energy_1700 else None,
            "energy_1700_p10": day_energy_1700["p10"] if day_energy_1700 else None,
            "energy_1700_share_lt35": day_energy_1700["share"] if day_energy_1700 else None,
            "share_lt35_eod": round(sum(1 for e in energies if e < LOW_ENERGY) / len(energies), 3) if energies else None,
            "cells_walked_per_resident": round(day_cells / alive_at_day_start, 3) if alive_at_day_start else None,
            "walk_attempts": day_stats["walk_attempts"],
            "walk_moved": day_stats["walk_moved"],
            "walk_moved_share": round(day_stats["walk_moved"] / day_stats["walk_attempts"], 3)
            if day_stats["walk_attempts"] else None,
            "walk_energy_per_cell": round(walk_points.get(day, 0.0) / moved, 3) if moved else None,
            "effort_energy_walk_share": round(walk_points.get(day, 0.0) / effort_points[day], 4)
            if effort_points.get(day) else None,
            "move_refused": day_stats["move_refused"],
        }
        rows.append(row)
        print(json.dumps(row, default=str), flush=True)
        alive_at_day_start = len(living)
        day_cells = 0
        day_stats = collections.Counter()
        day_recipe_starts = collections.Counter()
        return row

    for tick in range(total_ticks):
        day = tick // TICKS_PER_DAY
        day_now[0] = day
        g.step()
        for n in names:
            if not w.is_alive(n):
                continue
            response = g.last_responses.get(n)
            result = g.last_results.get(n)
            applied = bool(result.get("applied", False)) if isinstance(result, dict) else bool(result)
            action = response.major_action.action if (response is not None and response.major_action is not None) else None
            position = tuple(w.actor_position(n) or ())
            moved = 0
            if position and last_positions.get(n) and position != last_positions[n]:
                moved = abs(position[0] - last_positions[n][0]) + abs(position[1] - last_positions[n][1])
            last_positions[n] = position
            day_cells += moved
            per[n]["cells"] += moved
            min_energy[n] = min(min_energy[n], float(w.energy(n)))
            if work_cell[n] is not None and position == work_cell[n]:
                reached[n] = True
            if action == "move":
                if applied:
                    day_stats["walk_attempts"] += 1
                    per[n]["walk_attempts"] += 1
                    if moved:
                        day_stats["walk_moved"] += 1
                        per[n]["walk_moved"] += 1
                else:
                    day_stats["move_refused"] += 1
            if action is not None and applied:
                if action == "eat":
                    day_stats["eat"] += 1
                    per[n]["meals"] += 1
                elif action == "fetch":
                    day_stats["fetch"] += 1
                    per[n]["fetches"] += 1
                elif action == "work":
                    recipe = str(response.major_action.params.get("recipe"))
                    day_recipe_starts[recipe] += 1
                    per[n]["work_starts"] += 1
        if tick % TICKS_PER_DAY == sample_index:
            energies = sorted(float(w.energy(n)) for n in names if w.is_alive(n))
            if energies:
                day_energy_1700 = {"mean": round(sum(energies) / len(energies), 2),
                                   "p10": _percentile(energies, 0.1),
                                   "share": round(sum(1 for e in energies if e < LOW_ENERGY) / len(energies), 3)}
        last_tick_of_day = tick % TICKS_PER_DAY == TICKS_PER_DAY - 1
        if last_tick_of_day or tick == total_ticks - 1:
            partial = tick == total_ticks - 1 and not last_tick_of_day
            close_day(day, partial)
            day_energy_1700 = None
            if not any(w.is_alive(n) for n in names):
                extinct = True
                break

    # Days after extinction are reported as empty rows, so every run has the same row count.
    last_day = rows[-1]["day"] if rows else -1
    total_days = (total_ticks + TICKS_PER_DAY - 1) // TICKS_PER_DAY
    while extinct and last_day + 1 < total_days:
        last_day += 1
        rows.append({"day": last_day, "partial_day": False, "alive": 0, "extinct": True,
                     "deaths_day": {}, "deaths_cum": dict(deaths_cum)})

    deaths_by = {d["actor"]: d for d in w._deaths}
    residents = []
    for n in names:
        alive_now = w.is_alive(n)
        here = tuple(w.actor_position(n) or ())
        wc = work_cell[n]
        death = deaths_by.get(n)
        residents.append({
            "name": n, "role": role[n], "alive": alive_now,
            "death_cause": str(death["cause"]) if death else None,
            "death_day": death["day"] if death else None,
            "cells": per[n]["cells"], "meals": per[n]["meals"], "fetches": per[n]["fetches"],
            "work_starts": per[n]["work_starts"], "work_completions": per[n]["work_completions"],
            "walk_attempts": per[n]["walk_attempts"], "walk_moved": per[n]["walk_moved"],
            "reached_work_cell": reached[n], "min_energy": round(min_energy[n], 1),
            "energy_end": round(float(w.energy(n)), 1) if alive_now else None,
            "hunger_end": round(float(attrs(n).get("hunger", 0.0)), 3) if alive_now else None,
            "work_cell": list(wc) if wc else None,
            "dist_to_work_end": (abs(here[0] - wc[0]) + abs(here[1] - wc[1])) if (wc and alive_now and here) else None,
            "dist_to_store_end": (abs(here[0] - store_cell[0]) + abs(here[1] - store_cell[1])) if (alive_now and here) else None,
        })

    alive_end = [row["alive"] for row in rows]
    first_death = next((row["day"] for row in rows if row.get("deaths_day")), None)
    extinct_day = next((row["day"] for row in rows if row["alive"] == 0), None)
    summary = {
        "person_days": sum(alive_end),
        "alive_end": alive_end[-1] if alive_end else None,
        "first_death_day": first_death,
        "extinct_day": extinct_day,
        "walk_moved_share": round(sum(r.get("walk_moved", 0) for r in rows) / max(1, sum(r.get("walk_attempts", 0) for r in rows)), 3),
        "food_produced_total": round(sum(r.get("food_produced", 0.0) for r in rows), 2),
    }
    return {"seed": seed, "elapsed_s": round(time.time() - started, 1), "rows": rows, "summary": summary,
            "residents": residents}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Per-day balance metrics for the default Bigville town.")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--seeds", default=None, help="comma-separated seeds")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--ticks", type=int, default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--label", default="base")
    parser.add_argument("--set", action="append", default=[], metavar="TABLE.KEY=VALUE")
    args = parser.parse_args(argv)

    seeds = []
    if args.seeds:
        seeds += [int(s) for s in args.seeds.split(",") if s.strip()]
    if args.seed is not None:
        seeds.append(args.seed)
    if not seeds:
        seeds = [305000]
    total_ticks = args.ticks if args.ticks is not None else args.days * TICKS_PER_DAY
    if total_ticks < 1:
        raise SystemExit("the run must have at least one tick")

    sets = _parse_sets(args.set)
    before = _apply_sets(sets)
    runs = [run_seed(seed, total_ticks, args.label) for seed in seeds]
    from domains import bigville_entities as E
    effective = {f"{t}.{k}": E.__dict__[t][k] for t, k, _ in sets}
    result = {"label": args.label, "set": {f"{t}.{k}": v for t, k, v in sets}, "effective": effective,
              "replaced": before, "days": args.days, "ticks": total_ticks, "seeds": seeds, "runs": runs}
    if args.out:
        out_dir = os.path.dirname(os.path.abspath(args.out))
        os.makedirs(out_dir, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=1, default=str)
    return result


if __name__ == "__main__":
    main()
