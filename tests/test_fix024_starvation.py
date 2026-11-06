"""Regression (fix024): residents do not starve in the first day of the town100 game with simple backends.

Before the fix, 95 of 100 residents starved by turn 95 (the first day's end, one period is 96 ticks). Exertion
hunger (HUNGER_PER_STAMINA, too large for the loaf-sized meal) and sleeping before going for food caused it. The
probe is /tmp/death_probe.py in the fix024 report (docs/phases/fix024_starvation/REPORT.md). 97 turns is the
shortest run that still shows the bug (first death at step 96), and it takes about two minutes on the development machine.
"""
from bigville import village_eval as ve
from bigville.api import create_game

TURNS = 97


def test_town100_simple_backends_nobody_starves_in_the_first_day():
    game = create_game(scenario="town100", seed=305017, default_backend="simple", autonomous=True,
                       ticks_per_period=ve.TICKS_PER_PERIOD)
    for _ in range(TURNS):
        game.step()
    starved = [d for d in game.world._deaths if d.get("cause") == "starvation"]
    assert starved == [], f"{len(starved)} residents starved within {TURNS} turns"
