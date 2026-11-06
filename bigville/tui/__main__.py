"""python -m bigville.tui: play one resident in the terminal (Phase 057). There is no referee option: the
interface shows only what the resident can see."""
from __future__ import annotations

import argparse
import sys

from bigville.tui.app import Session, choose_front_end, run_curses, run_plain
from bigville.tui.client import ClientError, EmbeddedClient, HttpClient, UnsupportedOverHttp


def build_client(args):
    if args.url:
        return HttpClient(args.url, args.player, pack=args.pack)
    from bigville.api import create_game
    game = create_game(scenario=args.scenario, seed=args.seed, player=args.player)
    return EmbeddedClient(game, args.player)


def main(argv=None, stdin=None, stdout=None):
    parser = argparse.ArgumentParser(prog="python -m bigville.tui",
                                     description="Play one Bigville resident in the terminal.")
    parser.add_argument("--player", required=True, help="the resident to play")
    parser.add_argument("--url", default=None, help="a server in agent mode, for example http://127.0.0.1:8765")
    parser.add_argument("--scenario", default="town100")
    parser.add_argument("--seed", type=int, default=305000)
    parser.add_argument("--pack", default="bigville", help="the pack's words, when playing over --url")
    parser.add_argument("--plain", action="store_true", help="the line-by-line text interface")
    parser.add_argument("--snapshot", action="store_true", help="print one 80 by 24 screen and exit")
    args = parser.parse_args(argv)
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    try:
        session = Session(build_client(args))
    except (ClientError, KeyError, UnsupportedOverHttp) as exc:
        print(f"cannot start: {exc}", file=sys.stderr)
        return 1
    if args.snapshot:
        print("\n".join(session.screen()), file=stdout)
        return 0
    if choose_front_end(plain=args.plain, stdout=stdout) == "curses":
        import curses
        curses.wrapper(lambda screen: run_curses(session, screen, screen.getch))
    else:
        run_plain(session, stdin, stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
