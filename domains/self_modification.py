"""self_modification — the jabberwock edits and extends ITSELF, safely.

The agent is made of layers, and full self-control means being able to change every one:
  · GRAPH rules / concepts / seeds      — it already rewrites these (self-improvement loops)
  · native DSL ops (JIT)                — auto-compiled hot; perceivable via jit report (layer A)
  · native PRIMITIVES (new TermNodes)   — specify + emit + rebuild + reload (layer B)
  · the PYTHON host (adapters + logic)  — EDIT in place, or MOVE to native (layer C)

This faculty is the SAFE foundation under B and C: it modifies the SOURCE layers (Python + Rust)
under hard guards — backup → apply → CHECK (py compile / cargo check) → ROLLBACK on failure →
APPEND-ONLY AUDIT. Reload = re-import (Python) or maturin rebuild (native). Per CLAUDE.md the
end-state is move-to-native; until then the agent can also edit its Python. The invariant:
no source change lands without a backup and a passing check, and a failed change is reverted —
the agent can experiment on itself without ever bricking the build.
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # the gamma-substrate checkout
DSL = ROOT / "runners" / "dsl"
AUDIT = ROOT / "var" / "self_mod_audit.log"


class SelfModification:
    """Guarded self-edit of the agent's own source. All mutating ops back up first,
    check, and roll back on failure; every attempt is audited."""

    def __init__(self, root: Path = ROOT) -> None:
        self.root = Path(root)

    # --- read ---------------------------------------------------------------
    def read(self, relpath: str) -> str:
        return (self.root / relpath).read_text()

    def list_layer(self, layer: str) -> list[str]:
        """What the agent can edit: 'python' (domains/, substrate/) or 'rust' (the DSL src)."""
        if layer == "python":
            return sorted(str(p.relative_to(self.root))
                          for p in (self.root / "domains").glob("*.py"))
        if layer == "rust":
            return sorted(str(p.relative_to(self.root)) for p in (DSL / "src").glob("*.rs"))
        return []

    # --- guarded edit -------------------------------------------------------
    def _backup(self, p: Path) -> Path:
        bak = p.with_suffix(p.suffix + ".selfmod.bak")
        shutil.copy2(p, bak)
        return bak

    def edit(self, relpath: str, old: str, new: str, *, check: bool = True) -> dict:
        """Replace the first occurrence of `old` with `new` in a source file, with backup +
        check + rollback-on-failure. Returns {ok, ...}."""
        p = self.root / relpath
        src = p.read_text()
        if old not in src:
            return self._done(relpath, "edit", "NO_ANCHOR", "anchor text not found", ok=False)
        bak = self._backup(p)
        p.write_text(src.replace(old, new, 1))
        if check:
            ok, msg = self.check(relpath)
            if not ok:
                shutil.copy2(bak, p)               # ROLLBACK — never leave it broken
                return self._done(relpath, "edit", "ROLLBACK", msg, ok=False,
                                  extra={"rolled_back": True})
        return self._done(relpath, "edit", "OK", new.strip()[:100], ok=True,
                          extra={"backup": str(bak)})

    def append(self, relpath: str, text: str, *, check: bool = True) -> dict:
        """Append text to a source file (e.g. a new function/helper), guarded."""
        p = self.root / relpath
        bak = self._backup(p)
        with open(p, "a") as f:
            f.write(text)
        if check:
            ok, msg = self.check(relpath)
            if not ok:
                shutil.copy2(bak, p)
                return self._done(relpath, "append", "ROLLBACK", msg, ok=False,
                                  extra={"rolled_back": True})
        return self._done(relpath, "append", "OK", text.strip()[:100], ok=True,
                          extra={"backup": str(bak)})

    def restore(self, relpath: str) -> bool:
        """Manual rollback to the last backup."""
        p = self.root / relpath
        bak = p.with_suffix(p.suffix + ".selfmod.bak")
        if bak.exists():
            shutil.copy2(bak, p)
            self._done(relpath, "restore", "OK", "reverted to backup", ok=True)
            return True
        return False

    # --- burn (delete a dead boat) -----------------------------------------
    def burn(self, relpath: str) -> dict:
        """Delete a domains/ source file the agent has determined is a DEAD
        BOAT (referenced by no live runtime / test / script / sibling). Git
        history preserves it; the deletion is audited. Refuses anything
        outside domains/*.py."""
        if not relpath.startswith("domains/") or not relpath.endswith(".py"):
            return self._done(relpath, "burn", "REFUSED", "only domains/*.py", ok=False)
        p = self.root / relpath
        if not p.exists():
            return self._done(relpath, "burn", "MISSING", "already gone", ok=False)
        p.unlink()
        return self._done(relpath, "burn", "OK", "deleted (recoverable via git)", ok=True)

    # --- migration (the agent's own domains/ -> graph-native burn) ---------
    def migrate(self, apply: bool = False, builders: bool = False) -> dict:
        """Run the agent's OWN migration: discover dead-boat domains/*.py
        (referenced by nothing) and, with apply, BURN them via self.burn; with
        builders=True also capture+burn the seed-builders the seed boot
        reproduces. Delegates to the Migrator capability. apply=False = dry
        run. The agent can now migrate itself with no external script."""
        from domains.self_migration import Migrator
        return Migrator(self).run(apply=apply, builders=builders)

    # --- checks -------------------------------------------------------------
    def check(self, relpath: str) -> tuple[bool, str]:
        p = self.root / relpath
        if p.suffix == ".py":
            try:
                ast.parse(p.read_text(), str(p))      # syntax/parse check (fast, safe)
                return True, "python parse ok"
            except SyntaxError as e:
                return False, f"SyntaxError: {e}"
        if p.suffix == ".rs":
            try:
                r = subprocess.run(["cargo", "check", "--quiet"], cwd=DSL,
                                   capture_output=True, text=True, timeout=900)
                return (r.returncode == 0,
                        "cargo check ok" if r.returncode == 0 else r.stderr[-600:])
            except Exception as e:  # noqa: BLE001
                return False, f"cargo check failed to run: {e}"
        return True, "no checker for this file type"

    # --- reload / rebuild ---------------------------------------------------
    def reload_python(self, module: str) -> bool:
        import importlib
        import sys
        if module in sys.modules:
            try:
                importlib.reload(sys.modules[module])
                self._done(module, "reload_python", "OK", "", ok=True)
                return True
            except Exception as e:  # noqa: BLE001
                self._done(module, "reload_python", "FAIL", str(e), ok=False)
        return False

    def rebuild_native(self) -> dict:
        """maturin develop --release (compile the agent's native layer). Slow; one-shot.

        Build parallelism is CAPPED (CARGO_BUILD_JOBS=2) and the release codegen
        is held to few units so the rebuild does not OOM: an unbounded release
        build spawns one rustc/LLVM job per core (12 here), and the big DSL crate
        blows past memory. 2 jobs is slower but survives. Override via the env."""
        env = {**os.environ}
        env.setdefault("CARGO_BUILD_JOBS", "2")
        env.setdefault("CARGO_PROFILE_RELEASE_CODEGEN_UNITS", "4")
        try:
            r = subprocess.run(["maturin", "develop", "--release", "-j", "2"], cwd=DSL,
                               capture_output=True, text=True, timeout=3600, env=env)
            ok = r.returncode == 0
            tail = (r.stdout + r.stderr)[-600:]
            # SYNC the freshly built cdylib over the IMPORTED extension module.
            # `maturin develop` builds target/release/libsubstrate_rs.so but, in
            # this environment, does NOT refresh the installed _native.*.so the
            # interpreter imports — so a rebuild would silently keep running the
            # OLD binary (a newly authored primitive loads as UnknownTermType).
            # Copy it across so the next fresh process actually sees the rebuild.
            if ok:
                synced, detail = self._sync_native()
                ok = synced
                if not synced:
                    tail = (tail + " | SYNC FAILED: " + detail)[-600:]
            self._done("runners/dsl", "rebuild_native", "OK" if ok else "FAIL",
                       tail[-200:], ok=ok)
            return {"ok": ok, "tail": tail}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "tail": f"maturin failed to run: {e}"}

    def _sync_native(self) -> tuple[bool, str]:
        """Copy the just-built cdylib over the imported substrate_rs extension."""
        try:
            import glob
            built = sorted((DSL / "target" / "release").glob("libsubstrate_rs.so"))
            if not built:
                return False, "no built libsubstrate_rs.so under target/release"
            import substrate_rs
            pkgdir = os.path.dirname(substrate_rs.__file__)
            dests = glob.glob(os.path.join(pkgdir, "_native*.so"))
            if not dests:
                return False, f"no _native*.so under {pkgdir}"
            # ATOMIC replace (write temp in the same dir + os.replace) — NOT an
            # in-place copy: overwriting the .so in place truncates the inode the
            # running interpreter has mmap'd and segfaults it. os.replace swaps in
            # a NEW inode; the running process keeps the old (unlinked) one, fresh
            # processes get the new build.
            for d in dests:
                tmp = d + ".new"
                shutil.copy2(str(built[-1]), tmp)
                os.replace(tmp, d)
            return True, f"synced -> {dests}"
        except Exception as e:  # noqa: BLE001
            return False, f"{type(e).__name__}: {e}"

    # --- audit (append-only; corrigibility you can read) -------------------
    def _done(self, target: str, op: str, result: str, detail: str, *,
              ok: bool, extra: dict | None = None) -> dict:
        rec = {"t": time.time(), "target": str(target), "op": op,
               "result": result, "detail": detail}
        try:
            AUDIT.parent.mkdir(parents=True, exist_ok=True)
            with open(AUDIT, "a") as f:
                f.write(json.dumps(rec) + "\n")
        except Exception:  # noqa: BLE001
            pass
        out = {"ok": ok, "result": result, "detail": detail}
        if extra:
            out.update(extra)
        return out
