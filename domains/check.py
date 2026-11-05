"""check.py -- the entity self-test for any data pack.

    python3 -m domains.check                      # the default pack, bigville
    python3 -m domains.check --pack test_hamlet   # a pack by name under packs/, or a directory

Prints the same reports as `python3 domains/bigville_entities.py` (consistency, production systems
and balance, job seeding, capacity), computed over the chosen pack. Exit status 1 when the pack has
errors, 0 otherwise. Warnings do not change the exit status.
"""
from __future__ import annotations

import argparse
import sys

from domains.data_view import DEFAULT_PACK, entities


def report_text(pack=None):
    """The printed self-test for `pack` (None is the default pack), and its error count."""
    E = entities(pack)
    report = E.check_consistency()
    parts = [
        E.format_consistency_report(report),
        E.format_systems_report(E.analyse_systems()),
        "",
        E.format_jobs_report(),
        "",
        E.format_capacity_report(),
    ]
    return "\n".join(parts), len(report["errors"])


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m domains.check", description=__doc__.split("\n")[0])
    parser.add_argument("--pack", default=DEFAULT_PACK,
                        help=f"pack name under packs/, or a directory (default: {DEFAULT_PACK})")
    args = parser.parse_args(argv)
    text, errors = report_text(args.pack)
    print(text)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
