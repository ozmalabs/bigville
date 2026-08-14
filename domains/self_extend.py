"""self_extend — layer B: the jabberwock adds a NEW native PRIMITIVE to itself, safely.

The agent specifies a primitive it lacks (runtime_design.agent_specify_primitive), emits the
Rust for it across its homes (runtime_design.emit_primitive_rust), and this module APPLIES those
fragments into the live source, rebuilds the native layer, and verifies the new TermNode is
callable — all under an ALL-OR-NOTHING guard.

Why this module on top of the SelfModification keystone: a new primitive touches several match
arms in ONE file (term.rs alone gets ~5 inserts), so the keystone's per-edit .bak (which it
overwrites on each edit to the same file) cannot give all-or-nothing rollback. We take ONE
pristine snapshot of every touched file BEFORE any edit, apply all fragments with the build check
deferred, run a single `cargo check`/rebuild at the end, and on ANY failure restore EVERY file
from the snapshot. Nothing lands without the whole extension compiling; a failure leaves the tree
byte-identical to where it started. Every attempt is audited via the keystone.

Anchor derivation (no hand-written line numbers): the same emit template produces both the
existing primitive's lines and the new one's. So we emit an ANCHOR spec (e.g. ArgMax) — whose
emitted text is already verbatim in the source — and the NEW spec, then insert each new fragment
immediately after its anchor sibling. If any anchor is not found verbatim, we abort before
touching anything. Per CLAUDE.md the primitive itself is graph-composable Rust; this is the
agent extending its own native vocabulary, not Python reasoning.
"""
from __future__ import annotations

import time
from pathlib import Path

from domains.runtime_design import emit_primitive_rust
from domains.self_modification import DSL, SelfModification

SRC = DSL / "src"

# The ArgMax spec: its emit is already verbatim in the source, so it supplies exact anchors
# for any other index_of_reduction primitive (same template, same keys).
ARGMAX_ANCHOR = {
    "name": "ArgMax", "items_field": "items", "semantic_kind": "index_of_reduction",
    "reduce_op": "max", "purpose": "anchor", "why_new": "anchor", "grounded_in_science": True,
}


def _file_for(key: str) -> str:
    return key.split(" ", 1)[0]            # "term.rs (enum variant)" -> "term.rs"


def _is_group(key: str) -> bool:
    return "group" in key                  # a "| TermNode::X {..}" addition to a `|` chain


def _is_helper(key: str) -> bool:
    return "helper" in key                 # a top-level fn -> append to end of file


class PrimitiveExtension:
    """Apply an emitted primitive into the native source under an all-or-nothing guard."""

    def __init__(self) -> None:
        self.mod = SelfModification()
        self.root = self.mod.root

    # --- targeted patch (REPLACE existing code, all-or-nothing) -------------
    def apply_patch(self, patches: list[dict], *, build: bool = True,
                    revert_after: bool = False) -> dict:
        """Apply a list of TARGETED REPLACE patches to existing source/config under
        the SAME all-or-nothing guard as `extend` (snapshot every touched file ->
        replace `old` with `new` (each must appear exactly once) -> ONE cargo check
        -> maturin rebuild -> restore EVERY file on any failure). The PATCH content
        is supplied by the caller (a deterministic diagnosed change), NOT authored
        here — this is the harness, the agent's compile/verify/rollback. Each patch:
        {"file": "<path under the crate root>", "old": "<exact text>", "new": "<replacement>"}.
        Paths resolve under DSL (the crate root) so Cargo.toml is reachable too."""
        # preflight: every old must appear EXACTLY ONCE in its file (safe unique replace)
        errors = []
        files = {}
        for p in patches:
            fp = DSL / p["file"]
            if not fp.exists():
                errors.append(f"missing file: {p['file']}")
                continue
            text = files.setdefault(p["file"], fp.read_text())
            cnt = text.count(p["old"])
            if cnt != 1:
                errors.append(f"anchor in {p['file']} appears {cnt}x (need exactly 1): {p['old'][:60]!r}")
        if errors:
            self.mod._done("patch", "apply_patch", "ABORT_PREFLIGHT", "; ".join(errors)[:200], ok=False)
            return {"ok": False, "stage": "preflight", "errors": errors}

        touched = sorted({p["file"] for p in patches})
        snapshot = {f: (DSL / f).read_text() for f in touched}        # pristine, all-or-nothing

        def restore() -> None:
            for f, text in snapshot.items():
                (DSL / f).write_text(text)

        try:
            for p in patches:
                fp = DSL / p["file"]
                fp.write_text(fp.read_text().replace(p["old"], p["new"], 1))
            ok, msg = self._cargo_check()
            if not ok:
                restore()
                self.mod._done("patch", "apply_patch", "ROLLBACK_CHECK", msg[-200:], ok=False,
                               extra={"rolled_back": True, "files": touched})
                return {"ok": False, "stage": "cargo_check", "rolled_back": True, "detail": msg}
            if not build:
                self.mod._done("patch", "apply_patch", "OK_CHECK_ONLY", f"{len(touched)} files",
                               ok=True, extra={"files": touched})
                return {"ok": True, "stage": "cargo_check", "built": False, "files": touched}
            rb = self.mod.rebuild_native()
            if not rb["ok"]:
                restore()
                self.mod.rebuild_native()
                self.mod._done("patch", "apply_patch", "ROLLBACK_BUILD", rb["tail"][-200:], ok=False,
                               extra={"rolled_back": True})
                return {"ok": False, "stage": "rebuild", "rolled_back": True, "detail": rb["tail"]}
            if revert_after:
                restore()
                self.mod.rebuild_native()
                self.mod._done("patch", "apply_patch", "OK_REVERTED", "verified then reverted",
                               ok=True, extra={"files": touched})
                return {"ok": True, "stage": "reverted", "built": True, "files": touched}
            self.mod._done("patch", "apply_patch", "OK_BUILT", f"{len(touched)} files",
                           ok=True, extra={"files": touched})
            return {"ok": True, "stage": "built", "built": True, "files": touched}
        except Exception as e:                                         # noqa: BLE001
            restore()
            self.mod._done("patch", "apply_patch", "ROLLBACK_EXC", str(e)[:200], ok=False,
                           extra={"rolled_back": True})
            return {"ok": False, "stage": "exception", "rolled_back": True, "detail": str(e)}

    # --- plan ---------------------------------------------------------------
    def plan(self, spec: dict, anchor_spec: dict = ARGMAX_ANCHOR) -> dict:
        """Build the insertion plan from emitted fragments. No file writes.
        Returns {ok, name, inserts:[{file, key, anchor, insert, mode}], appends:[...], errors:[...]}."""
        name = spec["name"]
        # anchor_spec may be a normal spec (emit it) OR pre-emitted live-source
        # fragments under "__frags__" (e.g. a held Term's verbatim lines, used to
        # bootstrap a same-shape self-author — the structural-recursion anchor).
        anchors = anchor_spec["__frags__"] if "__frags__" in anchor_spec \
            else emit_primitive_rust(anchor_spec)
        frags = emit_primitive_rust(spec)
        if set(frags) != set(anchors):
            return {"ok": False, "name": name,
                    "errors": [f"emit key mismatch: {sorted(set(frags) ^ set(anchors))}"]}

        inserts: list[dict] = []
        appends: list[dict] = []
        errors: list[str] = []
        files: dict[str, str] = {}
        for key, frag in frags.items():
            fname = _file_for(key)
            files.setdefault(fname, (SRC / fname).read_text())
            if _is_helper(key):
                appends.append({"file": fname, "key": key, "insert": "\n\n" + frag + "\n"})
                continue
            anchor = anchors[key]
            if anchor not in files[fname]:
                errors.append(f"anchor not found verbatim in {fname}: {key!r}")
                continue
            if _is_group(key):
                mode, joined = "group", anchor + " " + frag.strip()
            else:
                mode, joined = "arm", anchor + "\n" + frag
            inserts.append({"file": fname, "key": key, "anchor": anchor,
                            "insert": joined, "mode": mode})

        # dup guard — refuse if the primitive already exists in the native layer.
        term = files.get("term.rs", (SRC / "term.rs").read_text())
        if f"    {name} {{" in term or f"TermNode::{name} " in term:
            errors.append(f"primitive {name!r} already present in term.rs (refusing to duplicate)")

        return {"ok": not errors, "name": name, "inserts": inserts,
                "appends": appends, "files": sorted(files), "errors": errors}

    # --- apply (all-or-nothing) --------------------------------------------
    def extend(self, spec: dict, anchor_spec: dict = ARGMAX_ANCHOR,
               *, build: bool = True, revert_after: bool = False) -> dict:
        """Apply the primitive, rebuild, verify it compiled. All-or-nothing: any failure
        restores every touched file from a pristine snapshot taken before the first write.
        build=False stops after `cargo check` (no maturin install); revert_after restores
        the snapshot after a successful build (for a demonstration that leaves no trace)."""
        plan = self.plan(spec, anchor_spec)
        if not plan["ok"]:
            self.mod._done(spec["name"], "extend", "ABORT_PREFLIGHT",
                           "; ".join(plan["errors"])[:200], ok=False)
            return {"ok": False, "stage": "preflight", "errors": plan["errors"]}

        touched = sorted({d["file"] for d in plan["inserts"] + plan["appends"]})
        snapshot = {f: (SRC / f).read_text() for f in touched}     # pristine, all-or-nothing

        def restore() -> None:
            for f, text in snapshot.items():
                (SRC / f).write_text(text)

        try:
            # apply inserts (anchor -> anchor+fragment) and appends (fn at EOF)
            for d in plan["inserts"]:
                p = SRC / d["file"]
                src = p.read_text()
                p.write_text(src.replace(d["anchor"], d["insert"], 1))
            for d in plan["appends"]:
                with open(SRC / d["file"], "a") as f:
                    f.write(d["insert"])

            # one check for the whole extension
            ok, msg = self._cargo_check()
            if not ok:
                restore()
                self.mod._done(spec["name"], "extend", "ROLLBACK_CHECK", msg[-200:], ok=False,
                               extra={"rolled_back": True, "files": touched})
                return {"ok": False, "stage": "cargo_check", "rolled_back": True, "detail": msg}

            if not build:
                self.mod._done(spec["name"], "extend", "OK_CHECK_ONLY",
                               f"{len(touched)} files", ok=True, extra={"files": touched})
                return {"ok": True, "stage": "cargo_check", "built": False, "files": touched}

            rb = self.mod.rebuild_native()                          # maturin develop --release
            if not rb["ok"]:
                restore()
                self.mod.rebuild_native()                           # resync binary to pristine src
                self.mod._done(spec["name"], "extend", "ROLLBACK_BUILD", rb["tail"][-200:],
                               ok=False, extra={"rolled_back": True})
                return {"ok": False, "stage": "rebuild", "rolled_back": True, "detail": rb["tail"]}

            if revert_after:
                restore()
                self.mod.rebuild_native()                           # resync binary to pristine src
                self.mod._done(spec["name"], "extend", "OK_REVERTED",
                               "verified then reverted", ok=True, extra={"files": touched})
                return {"ok": True, "stage": "reverted", "built": True, "files": touched}

            self.mod._done(spec["name"], "extend", "OK_BUILT",
                           f"{len(touched)} files", ok=True, extra={"files": touched})
            return {"ok": True, "stage": "built", "built": True, "files": touched}
        except Exception as e:                                       # noqa: BLE001
            restore()
            self.mod._done(spec["name"], "extend", "ROLLBACK_EXC", str(e)[:200], ok=False,
                           extra={"rolled_back": True})
            return {"ok": False, "stage": "exception", "rolled_back": True, "detail": str(e)}

    # --- check (cargo, no install) -----------------------------------------
    def _cargo_check(self) -> tuple[bool, str]:
        import subprocess
        try:
            r = subprocess.run(["cargo", "check", "--quiet"], cwd=DSL,
                               capture_output=True, text=True, timeout=1200)
            return (r.returncode == 0,
                    "cargo check ok" if r.returncode == 0 else r.stderr[-800:])
        except Exception as e:                                       # noqa: BLE001
            return False, f"cargo check failed to run: {e}"
