"""python -m bigville.tui: play one resident in the terminal (Phase 057). There is no referee option: the
interface shows only what the resident can see."""
from __future__ import annotations

import argparse
import os
import sys

from bigville.tui.app import Session, choose_front_end, run_curses, run_plain, run_text
from bigville.tui.client import ClientError, EmbeddedClient, HttpClient, UnsupportedOverHttp


def build_client(args):
    if args.url:
        return HttpClient(args.url, args.player, pack=args.pack)
    from bigville.api import create_game
    game = create_game(scenario=args.scenario, seed=args.seed, player=args.player)
    return EmbeddedClient(game, args.player)


def open_log(log_dir, player):
    """The text mode's turn log: one append-only, hash-chained file per run (bigville.llm_log.LLMLog)."""
    import re
    from bigville.llm_log import LLMLog, new_run_id
    slug = re.sub(r"[^A-Za-z0-9]+", "_", str(player)).strip("_") or "player"
    return LLMLog(os.path.join(log_dir, f"text_{slug}.jsonl"), run_id=new_run_id())


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
    parser.add_argument("--mode", choices=("map", "text"), default=None,
                        help="map: the screen with character art; text: the text adventure, written from the prompt "
                             "packet. Without --mode the screen is the one of Phase 057")
    parser.add_argument("--show-packet", action="store_true",
                        help="text mode: print the prompt packet the room came from, after each room")
    parser.add_argument("--log-dir", default=None,
                        help="text mode: write the turn log (hash-chained JSON lines) to this directory")
    args = parser.parse_args(argv)
    if args.mode != "text" and (args.show_packet or args.log_dir):
        parser.error("--show-packet and --log-dir need --mode text")
    if args.mode == "text" and args.url:
        parser.error("--mode text runs in process (the packet is built from the game); drop --url")
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    try:
        session = Session(build_client(args), art=args.mode == "map", text=args.mode == "text")
    except (ClientError, KeyError, UnsupportedOverHttp) as exc:
        print(f"cannot start: {exc}", file=sys.stderr)
        return 1
    if args.mode == "text":
        log = open_log(args.log_dir, args.player) if args.log_dir else None
        if args.snapshot:
            print("\n".join([session.banner()] + session.room(args.show_packet)), file=stdout)
            return 0
        run_text(session, stdin, stdout, show_packet=args.show_packet, log=log)
        return 0
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
