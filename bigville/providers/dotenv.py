"""A minimal reader for a ``.env`` file (standard library only; python-dotenv is not used).

It fills in variables that are not already set. A variable already in the environment is never replaced.
Values are never printed or logged by this module: callers get the names of the keys they were given."""
from __future__ import annotations

import os
import re
from pathlib import Path

_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def parse_dotenv(text: str) -> dict[str, str]:
    """KEY=VALUE lines. Blank lines and lines starting with ``#`` are skipped, an ``export `` prefix is
    allowed, single or double quotes around a value are removed, and ` #` starts a comment after an unquoted
    value. Lines that are not KEY=VALUE are ignored."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not _KEY.fullmatch(key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        values[key] = value
    return values


def load_dotenv(path: str | Path, environ: dict[str, str] | None = None) -> list[str]:
    """Set each variable of the file that ``environ`` (default ``os.environ``) does not already define.

    Returns the names that were set. A missing file sets nothing and is not an error."""
    target = os.environ if environ is None else environ
    file = Path(path)
    if not file.is_file():
        return []
    applied = []
    for key, value in parse_dotenv(file.read_text(encoding="utf-8")).items():
        if key not in target:
            target[key] = value
            applied.append(key)
    return applied
