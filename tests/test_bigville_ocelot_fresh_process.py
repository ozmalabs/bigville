"""Fresh-interpreter checks for the sibling Ocelot/Bigville source layout."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
import textwrap

import pytest


BIGVILLE_ROOT = Path(__file__).resolve().parents[1]
OCELOT_ROOT = BIGVILLE_ROOT.parent / "ocelot"
NATIVE_PACKAGE_ROOT = OCELOT_ROOT / "runners" / "dsl" / "python"
HAS_SOURCE_CHECKOUTS = (
    (OCELOT_ROOT / "worlds" / "bigville_ocelot_adapter.py").is_file()
    and (NATIVE_PACKAGE_ROOT / "substrate_rs" / "_native.abi3.so").is_file()
)


def _run_fresh_process(source: str, *, pythonpath: list[Path], cwd=OCELOT_ROOT,
                       extra_env=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(str(path) for path in pythonpath)
    env["BIGVILLE_ROOT"] = str(BIGVILLE_ROOT)
    env["OCELOT_ROOT"] = str(OCELOT_ROOT)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=90,
    )


@pytest.mark.skipif(not HAS_SOURCE_CHECKOUTS,
                    reason="Ocelot checkout/native extension is not present")
@pytest.mark.parametrize("order", ["ocelot-first", "bigville-first"])
def test_fresh_process_import_orders_construct_mixed_real_backends(order, tmp_path):
    roots = [OCELOT_ROOT, BIGVILLE_ROOT] if order == "ocelot-first" else [BIGVILLE_ROOT, OCELOT_ROOT]
    # Keep the native package discoverable after either source-root order.
    result = _run_fresh_process(
        """
        import json
        import os
        import sys
        from pathlib import Path

        # Python puts the working directory at sys.path[0] for `-c`; remove
        # that implicit entry so the PYTHONPATH permutation is what selects
        # package roots. The working directory still supplies Ocelot's
        # historical relative seed-file paths.
        if '' in sys.path:
            sys.path.remove('')
        assert Path.cwd().resolve() != Path(os.environ['OCELOT_ROOT']).resolve()
        order = __import__('os').environ['IMPORT_ORDER']
        if order == 'ocelot-first':
            from worlds.bigville_ocelot_adapter import BigvilleOcelotResident
            from bigville import create_game
        else:
            from bigville import create_game
            from worlds.bigville_ocelot_adapter import BigvilleOcelotResident

        from bigville.backends import HumanBackend, OcelotBackend
        from bigville.scenarios import load_scenario
        import bigville
        import worlds.bigville_ocelot_adapter as adapter_module

        assert Path(bigville.__file__).resolve().is_relative_to(
            Path(os.environ['BIGVILLE_ROOT']).resolve())
        assert Path(adapter_module.__file__).resolve() == Path(
            os.environ['PYTHONPATH'].split(os.pathsep)[0 if order == 'ocelot-first' else 1],
            'worlds', 'bigville_ocelot_adapter.py').resolve()

        scenario = load_scenario('simple_resident_food').to_dict()
        scenario['actors'] = [
            {'name': 'Ada', 'role': 'hand', 'backend': 'ocelot', 'home_cell': [2, 2]},
            {'name': 'Ben', 'role': 'hand', 'backend': 'simple', 'home_cell': [2, 2]},
            {'name': 'Cal', 'role': 'hand', 'backend': 'ocelot', 'home_cell': [2, 2]},
            {'name': 'Dee', 'role': 'hand', 'backend': 'simple', 'home_cell': [2, 2]},
        ]
        game = create_game(scenario=scenario, seed=305000, player='Ben',
                           default_backend='simple', ticks_per_period=None)

        assert isinstance(game.world.actor_mind('Ada'), BigvilleOcelotResident)
        assert isinstance(game.world.actor_mind('Cal'), BigvilleOcelotResident)
        assert isinstance(game.backends['Ada'], OcelotBackend)
        assert isinstance(game.backends['Cal'], OcelotBackend)
        assert isinstance(game.backends['Ben'], HumanBackend)
        assert game.backends['Dee'].kind == 'cheap'
        print(order, 'constructed Ada/Cal=ocelot, Ben=human, Dee=cheap')
        """,
        pythonpath=[*roots, NATIVE_PACKAGE_ROOT],
        cwd=tmp_path,
        extra_env={"IMPORT_ORDER": order},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"{order} constructed Ada/Cal=ocelot, Ben=human, Dee=cheap" in result.stdout


@pytest.mark.skipif(not (OCELOT_ROOT / "worlds" / "bigville_ocelot_adapter.py").is_file(),
                    reason="Ocelot source checkout is not present")
def test_fresh_process_missing_native_dependency_reports_actionable_cause():
    result = _run_fresh_process(
        """
        import importlib.abc

        class BlockNativeSubstrate(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == 'substrate_rs':
                    raise ModuleNotFoundError(
                        \"No module named 'substrate_rs'\", name='substrate_rs')

        import sys
        sys.meta_path.insert(0, BlockNativeSubstrate())

        from bigville import create_game
        from bigville.backends import OcelotUnavailableError
        from bigville.scenarios import load_scenario

        scenario = load_scenario('simple_resident_food').to_dict()
        scenario['actors'][0]['backend'] = 'ocelot'
        try:
            create_game(scenario=scenario, default_backend='simple', ticks_per_period=None)
        except OcelotUnavailableError as exc:
            assert 'Adapter import failed' in str(exc)
            assert \"ModuleNotFoundError: No module named 'substrate_rs'\" in str(exc)
            assert isinstance(exc.__cause__, ModuleNotFoundError)
            assert exc.__cause__.name == 'substrate_rs'
            print(str(exc))
        else:
            raise AssertionError('missing Ocelot native dependency was not reported')
        """,
        # Deliberately exclude runners/dsl/python: the meta-path blocker also
        # makes the test deterministic on machines with a globally installed
        # substrate_rs package.
        pythonpath=[BIGVILLE_ROOT, OCELOT_ROOT],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "No module named 'substrate_rs'" in result.stdout
