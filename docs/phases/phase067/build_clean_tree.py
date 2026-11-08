"""build_clean_tree.py -- a clean copy of HEAD plus the files of Phase 067, for the focused tests and the full suite.

    python3 docs/phases/phase067/build_clean_tree.py --out /tmp/t067_clean [--src REPO]

The copy is `git archive HEAD` (the commit named in the report's Validation, 5de0e52 when this was written), extracted
into --out. Then:

* NEW FILES are copied from --src (this phase's new modules, pack table files and the new test file).
* TERMINAL FILES are the bigville/tui modules this phase changed. They are copied whole from --src, and the builder
  first checks that HEAD's version of each is the version this phase started from (BASE_SHA256). If HEAD moves a
  terminal file, the builder stops and says so.
* SHARED HUNKS are anchored edits to files other sessions edit. Each old text must occur EXACTLY ONCE in HEAD's
  version of the file, or the builder stops with "anchor found N times". The hunk is then replaced by its new text.

The builder never touches --src. It exits 1 on any anchor or base mismatch and writes nothing for that file.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SRC = os.path.abspath(os.path.join(HERE, "..", "..", ".."))

NEW_FILES = (
    "bigville/tui/art.py",
    "bigville/tui/prose.py",
    "domains/tui_check.py",
    "packs/bigville/world/tui_modes.json",
    "packs/test_hamlet/world/tui_modes.json",
    "tests/test_phase067_tui_modes.py",
)

# SHA-256 of HEAD's version of each terminal module before this phase (HEAD 5de0e52).
TERMINAL_FILES = {
    "bigville/tui/__main__.py": "1df4af925b0a1f7c6cd8f82849a3f293a591b85a6ad67ce7f9405762525ef326",
    "bigville/tui/app.py": "cc3f6188d59d0bcf2ad1110811db3da2fbb061c914675f5bd3458d6c1d8dfc05",
    "bigville/tui/client.py": "0f9a4fb7d43b3e3c9e46028fc7af86f1e1904f51242227368a1a3369dd105802",
    "bigville/tui/commands.py": "1cdc7f77619e538c6951688bc7a25b652d3c05351632eb0e757d713e8d7c3277",
    "bigville/tui/narrate.py": "13bbdeac9d44eb900533af369c62476a724c476fbffa43dcdcc2b72a0e086a01",
    "bigville/tui/render.py": "0e37e04b222ff8dcf2ad9c719d39268e6ba3d25d10beb6d6ec1350038ea3dc46",
}

PACK_MANIFEST_OLD = ('"name": "RECOGNISED_SEED",\n      "file": "world/literacy.json"\n    }\n  ]')
PACK_MANIFEST_NEW = ('"name": "RECOGNISED_SEED",\n      "file": "world/literacy.json"\n    },\n'
                     '    {"name": "TUI_ART", "file": "world/tui_modes.json"},\n'
                     '    {"name": "TUI_PROSE", "file": "world/tui_modes.json"}\n  ]')
CAPS_OLD = '        "things": 800,\n'
CAPS_NEW = '        "things": 800,\n        "writing": 600,\n'

# (path, old, new): each old text must occur exactly once in HEAD's version of the file.
SHARED_HUNKS = (
    ("packs/bigville/pack.json", PACK_MANIFEST_OLD, PACK_MANIFEST_NEW),
    ("packs/test_hamlet/pack.json", PACK_MANIFEST_OLD, PACK_MANIFEST_NEW),
    ("packs/bigville/world/prompt_packet.json", CAPS_OLD, CAPS_NEW),
    ("packs/test_hamlet/world/prompt_packet.json", CAPS_OLD, CAPS_NEW),
    ("bigville/backends/prompt_packet.py",
     "    if consult_reason is not None:\n",
     "    # Phase 064: written marks in sight go in the packet only when the view carries them (reading on). Off, the\n"
     "    # packet is byte-for-byte what it was before.\n"
     "    if around.get(\"writing\"):\n"
     "        public[\"around\"][\"writing\"] = caps.items(\"writing\", around[\"writing\"])\n"
     "    if consult_reason is not None:\n"),
    ("domains/prompt_packet_check.py",
     '"people", "seen", "things", "heard", "map", "can", "last", "consult")',
     '"people", "seen", "things", "writing", "heard", "map", "can", "last", "consult")'),
    ("domains/bigville_entities.py",
     "    check_narration(_WORLD_PACK.path, errors, warnings, info)\n",
     "    check_narration(_WORLD_PACK.path, errors, warnings, info)\n"
     "    from domains.tui_check import check_tui  # Phase 067: the terminal modes' map art and text sentences\n"
     "    check_tui(_WORLD_PACK.path, errors, warnings, info)\n"),
)


def fail(message):
    print(f"build_clean_tree: {message}", file=sys.stderr)
    sys.exit(1)


def head_bytes(repo, path):
    return subprocess.run(["git", "-C", repo, "show", f"HEAD:{path}"], check=True, capture_output=True).stdout


def head_sha(repo):
    return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], check=True, capture_output=True,
                          text=True).stdout.strip()


def extract_head(repo, out):
    archive = subprocess.run(["git", "-C", repo, "archive", "--format=tar", "HEAD"], check=True,
                             capture_output=True).stdout
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(out, filter="data")
        else:
            tar.extractall(out)


def write(out, path, data):
    target = os.path.join(out, path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as handle:
        handle.write(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", required=True, help="the directory to build the clean tree in (replaced)")
    parser.add_argument("--src", default=DEFAULT_SRC, help="the working tree that holds this phase's files")
    args = parser.parse_args(argv)
    repo, out = os.path.abspath(args.src), os.path.abspath(args.out)
    if out in (repo, os.path.dirname(repo)) or out.startswith(repo + os.sep):
        fail("--out must be outside the working tree")
    print(f"HEAD {head_sha(repo)}")
    extract_head(repo, out)

    for path in TERMINAL_FILES:
        base = hashlib.sha256(head_bytes(repo, path)).hexdigest()
        if base != TERMINAL_FILES[path]:
            fail(f"{path}: HEAD's version is not the one this phase started from ({base[:12]}); stop and re-base")
    for path in NEW_FILES:
        with open(os.path.join(repo, path), "rb") as handle:
            write(out, path, handle.read())
        print(f"new      {path}")
    for path in TERMINAL_FILES:
        with open(os.path.join(repo, path), "rb") as handle:
            write(out, path, handle.read())
        print(f"terminal {path}")

    by_path: dict[str, bytes] = {}
    for path, old, new in SHARED_HUNKS:
        text = by_path[path].decode("utf-8") if path in by_path else head_bytes(repo, path).decode("utf-8")
        found = text.count(old)
        if found != 1:
            fail(f"{path}: anchor found {found} times (need 1): {old[:60]!r}")
        by_path[path] = text.replace(old, new, 1).encode("utf-8")
    for path, data in by_path.items():
        write(out, path, data)
        print(f"hunks    {path}")
    print(f"clean tree at {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
