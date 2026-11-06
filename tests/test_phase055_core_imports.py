"""Phase 055: the core imports with no network and no third-party module.

The check runs in a subprocess. Socket connections are replaced by an error before anything is imported, and
every module the import loads must be from the standard library or from this repository's own packages."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCRIPT = r'''
import socket
import sys

BASELINE = set(sys.modules)

def _blocked(*args, **kwargs):
    raise RuntimeError("network access blocked by the test")

socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.create_connection = _blocked

import bigville
import bigville.api
import bigville.game
import bigville.reporting
import bigville.backends
import bigville.backends.llm
import bigville.llm_transcript
import bigville.llm_scenario
import bigville.concurrency

LOCAL = {"bigville", "domains", "worlds", "tools"}
# Only what the bigville import loads counts. Modules the interpreter loaded at startup (such as sitecustomize)
# are not the core's imports.
loaded = {name.split(".")[0] for name in set(sys.modules) - BASELINE}
third_party = sorted(name for name in loaded
                     if name not in sys.stdlib_module_names and name not in LOCAL and not name.startswith("_"))
print("PROVIDERS_LOADED", "bigville.providers" in sys.modules)
print("THIRD_PARTY", third_party)
'''


def test_the_core_imports_with_no_network_and_no_third_party_module():
    result = subprocess.run([sys.executable, "-c", SCRIPT], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr[-2000:]
    lines = dict(line.split(" ", 1) for line in result.stdout.strip().splitlines())
    assert lines["PROVIDERS_LOADED"] == "False"
    assert lines["THIRD_PARTY"] == "[]"


def test_the_provider_modules_use_only_the_standard_library():
    result = subprocess.run(
        [sys.executable, "-c",
         "import sys; base = set(sys.modules); import bigville.providers as p; "
         "names = sorted(n.split('.')[0] for n in set(sys.modules) - base); "
         "bad = [n for n in names if n not in sys.stdlib_module_names and n not in "
         "('bigville', 'domains', 'worlds', 'tools') and not n.startswith('_')]; print(bad)"],
        cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip() == "[]"
