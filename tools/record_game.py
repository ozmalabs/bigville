"""Record a short live Bigville session as an animated GIF.

This drives the same Phaser client a player uses.  Install the optional
recording tools with ``pip install playwright pillow`` and make sure a browser
is available (``playwright install chromium`` is sufficient).
"""
from __future__ import annotations

import argparse
import io
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_server(port: int, timeout: float = 20.0):
    import urllib.request

    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError("Bigville server did not become ready")


def record(*, output: Path, turns: int, frame_delay: int, scenario: str,
           seed: int, player: str | None, focus: tuple[int, int] | None = None,
           screenshot_dir: Path | None = None):
    root = Path(__file__).resolve().parents[1]
    port = free_port()
    command = [sys.executable, "-m", "bigville.server", "--port", str(port),
               "--scenario", scenario, "--seed", str(seed)]
    if player:
        command.extend(["--player", player])
    server = subprocess.Popen(command, cwd=root, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    try:
        wait_for_server(port)
        frames: list[Image.Image] = []
        with sync_playwright() as playwright:
            executable = shutil.which("google-chrome") or shutil.which("chromium")
            browser_args = ["--no-sandbox"] if executable else []
            browser = playwright.chromium.launch(headless=True,
                                                  executable_path=executable,
                                                  args=browser_args)
            page = browser.new_page(viewport={"width": 1200, "height": 760},
                                     device_scale_factor=1)
            page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle",
                      timeout=60000)
            page.wait_for_selector("#game canvas", timeout=60000)
            page.click("#reset")
            page.wait_for_timeout(900)
            if focus is not None:
                page.evaluate("([x, y]) => window.bigvilleScene?.focusOnCell(x, y)", list(focus))
                page.wait_for_timeout(250)

            def capture():
                image = Image.open(io.BytesIO(page.screenshot(full_page=True))).convert("RGB")
                # Keep the README animation compact while retaining readable UI.
                image.thumbnail((960, 960), Image.Resampling.LANCZOS)
                frames.append(image.copy())

            capture()
            if screenshot_dir is not None:
                screenshot_dir.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot_dir / "bigville-overview.png"), full_page=True)
                page.evaluate("() => window.bigvilleScene?.adjustZoom(0.75)")
                page.wait_for_timeout(250)
                page.screenshot(path=str(screenshot_dir / "bigville-detail.png"), full_page=True)
                page.evaluate("() => window.bigvilleScene?.adjustZoom(-0.75)")
                page.wait_for_timeout(250)
            for _ in range(max(0, turns)):
                buttons = page.locator("#actions button:not([disabled])")
                if buttons.count() == 0:
                    break
                buttons.first.click()
                # A town100 turn can take longer than the visual frame delay:
                # wait for the real response before capturing the next state.
                page.wait_for_function(
                    "!document.querySelector('#status').textContent.includes('considering')",
                    timeout=60000,
                )
                page.wait_for_timeout(frame_delay)
                capture()
                if screenshot_dir is not None and len(frames) == 2:
                    page.screenshot(path=str(screenshot_dir / "bigville-after-turn.png"), full_page=True)
            browser.close()
        if not frames:
            raise RuntimeError("no frames captured")
        output.parent.mkdir(parents=True, exist_ok=True)
        frames[0].save(output, save_all=True, append_images=frames[1:],
                        duration=max(80, frame_delay), loop=0, optimize=True,
                        disposal=2)
        print(f"recorded {len(frames)} frames to {output}")
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=Path("docs/screenshots/bigville-simulation.gif"))
    parser.add_argument("--turns", type=int, default=24)
    parser.add_argument("--frame-delay", type=int, default=220,
                        help="milliseconds between captured turns")
    parser.add_argument("--scenario", default="town100")
    parser.add_argument("--seed", type=int, default=305000)
    parser.add_argument("--player", default=None)
    parser.add_argument("--focus", default="23,18",
                        help="map cell to center (x,y); pass 'none' to keep the player-centered view")
    parser.add_argument("--screenshots-dir", type=Path, default=None,
                        help="also write overview, detail, and after-turn PNGs")
    args = parser.parse_args(argv)
    focus = None if args.focus.lower() == "none" else tuple(int(part) for part in args.focus.split(",", 1))
    record(output=args.output, turns=args.turns, frame_delay=args.frame_delay,
           scenario=args.scenario, seed=args.seed, player=args.player, focus=focus,
           screenshot_dir=args.screenshots_dir)


if __name__ == "__main__":
    main()
