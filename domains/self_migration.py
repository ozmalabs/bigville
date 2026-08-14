"""self_migration — the jabberwock's OWN boat-burning migration faculty.

A pure capability class (no agent decisions — deterministic graph/import analysis,
the same kind CLAUDE.md permits for ToolBox / GraphEye / SelfModification). It
gives the agent the ability to run the domains/ -> graph-native migration ITSELF:

  discover_orphans()            domains/*.py referenced by NOTHING (runtime,
                                tests, scripts, siblings, dynamic) and not a
                                seed-builder -> dead boats.
  discover_builders()           install_*_seed builders, split into:
                                  equivalent  (load_all_seeds reproduces them
                                               -> burnable),
                                  gaps        (seed boot misses some node/edge
                                               -> capture-to-seed first),
                                  in_use      (a test/runtime CALLS the builder
                                               -> burning needs the caller
                                               migrated; left alone).
  capture_to_seed(module)       write a builder's GAP (missing nodes + edges,
                                by name) into its seed JSON as extra_nodes +
                                relations, so load_one_seed reproduces it.
  run(apply=False, builders=False)
                                discover + (optionally) burn orphans (+ capture
                                & burn equivalent builders) via the agent's
                                SelfModification.burn faculty. apply=False is a
                                dry run; returns a full report.

The MUTATIONS go through the agent's own SelfModification (burn = audited,
git-recoverable; capture = a guarded seed write). The driver/agent only invokes
this; the analysis is mechanical and the deletions are the agent's faculty.
"""
from __future__ import annotations

import ast
import glob
import json
import os
import re
from pathlib import Path


class Migrator:
    """The agent's migration faculty. Construct with its SelfModification
    (for burn) — ``Migrator(self_mod)`` — or bare for discovery only."""

    def __init__(self, self_mod=None, root: Path | None = None):
        self.mod = self_mod
        self.root = Path(root or (self_mod.root if self_mod is not None
                                  else Path(__file__).resolve().parent.parent))

    # ----- import reachability ------------------------------------------
    def _dom_imports(self, path, domains, in_domains=False):
        out = set()
        try:
            tree = ast.parse(open(path).read(), path)
        except Exception:
            return out
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom):
                mod = n.module or ""
                lvl = n.level or 0
                if lvl >= 1 and in_domains:
                    if mod:
                        out.add(mod.split(".")[0])
                    else:
                        for a in n.names:
                            out.add(a.name)
                elif mod == "domains":
                    for a in n.names:
                        out.add(a.name)
                elif mod.startswith("domains."):
                    out.add(mod.split(".")[1])
            elif isinstance(n, ast.Import):
                for a in n.names:
                    if a.name.startswith("domains."):
                        out.add(a.name.split(".")[1])
        return out & domains

    def _all_domains(self):
        return {os.path.basename(p)[:-3]
                for p in glob.glob(str(self.root / "domains" / "*.py"))
                if not p.endswith("__init__.py")}

    def _builders(self):
        out = {}
        for p in glob.glob(str(self.root / "domains" / "*.py")):
            fns = re.findall(r"def (install_\w+_seed)\(", open(p).read())
            if fns:
                out[os.path.basename(p)[:-3]] = fns
        return out

    def _referenced(self, roots_only=False):
        """domains modules reachable by import. roots_only -> from substrate/+tests/
        (the bench guard); else from everywhere incl. scripts + dynamic."""
        domains = self._all_domains()
        refs = set()
        scan = glob.glob(str(self.root / "substrate" / "*.py")) + \
            glob.glob(str(self.root / "tests" / "*.py"))
        if not roots_only:
            scan += glob.glob(str(self.root / "scripts" / "*.py"))
        for p in scan:
            refs |= self._dom_imports(p, domains, False)
        for d in domains:
            refs |= self._dom_imports(str(self.root / "domains" / f"{d}.py"), domains, True)
        if not roots_only:
            for p in glob.glob(str(self.root / "**" / "*.py"), recursive=True):
                try:
                    t = open(p).read()
                except Exception:
                    continue
                for m in re.finditer(r'import_module\(\s*[\'"]domains\.([a-zA-Z_]\w*)', t):
                    if m.group(1) in domains:
                        refs.add(m.group(1))
        # transitive closure
        dep = {d: self._dom_imports(str(self.root / "domains" / f"{d}.py"), domains, True)
               for d in domains}
        from collections import deque
        seen, q = set(refs), deque(refs)
        while q:
            x = q.popleft()
            for y in dep.get(x, ()):
                if y not in seen:
                    seen.add(y)
                    q.append(y)
        return domains, seen

    def discover_orphans(self, include_allowed=False):
        """domains/*.py referenced by NOTHING. By default returns only TRUE dead
        boats — inert Python that is NEITHER a seed-builder NOR allowed-Python.
        Allowed-Python (a Term/graph-data builder or a world adapter) is a RE-WIRE
        candidate, not a burn (see discover_unwired); the import graph can't see
        graph-data/dynamic wiring, so such a module must never be auto-burned.
        include_allowed=True returns every unreferenced module (the raw set)."""
        domains, refs = self._referenced(roots_only=False)
        builders = set(self._builders())
        unref = domains - refs - builders
        if include_allowed:
            return sorted(unref)
        return sorted(m for m in unref if not self._is_allowed_python(m))

    def discover_unwired(self):
        """Unreferenced ALLOWED-Python (Term/graph-data builders, world adapters) —
        capable code that is merely import-unwired. RE-WIRE candidates (restore
        access + a guarding test), NOT dead boats. A capability is only 'orphaned'
        w.r.t. the IMPORT graph; graph-wired/dynamically-routed code needs a test to
        pin it (as relation_ingest / shape_generation_programs were re-wired)."""
        domains, refs = self._referenced(roots_only=False)
        builders = set(self._builders())
        unref = domains - refs - builders
        return sorted(m for m in unref if self._is_allowed_python(m))

    def _is_allowed_python(self, module, src=None):
        """Recognise ALLOWED Python (CLAUDE.md) that must NOT be treated as a dead
        boat even when import-unreferenced: a Term/graph-data BUILDER (emits
        {"type": "..."} Term dicts, or install_*_seed / *_program / build_* / make_*
        graph-data builders) or an ingest/emit world ADAPTER (mechanical substrate
        I/O: .nodes( / .node( / .add_node( / .add_edge(, or ingest_* / emit_*
        functions). Such a module is a RE-WIRE candidate, never an auto-burn."""
        import ast as _ast, os as _os, re as _re
        if src is None:
            p = _os.path.join(self.root, "domains", module + ".py")
            if not _os.path.exists(p):
                return False
            src = open(p).read()
        if ('"type":' in src) or ("'type':" in src):           # emits Term dicts
            return True
        if any(t in src for t in (".add_node(", ".add_edge(", ".nodes(", ".node(")):
            return True                                          # mechanical substrate I/O (adapter)
        try:
            tree = _ast.parse(src)
        except Exception:
            return False
        for n in _ast.walk(tree):
            if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                nm = n.name
                if (_re.match(r"install_\w+_seed$", nm) or nm.endswith("_program")
                        or nm.startswith(("build_", "make_", "ingest_", "emit_"))):
                    return True
        return False

    # ----- self-host comprehension + behavioral verification (the two faculties
    #       the agent worked out it needs to migrate ITSELF) -------------------
    def comprehend_faculty(self, module, agent=None):
        """COMPREHEND a host faculty into a behavioral SPEC the agent can design
        against: its cognitive SHAPE (shape_hits over its concepts, when an agent
        carrying the shape vocabulary is given) + its TEST CONTRACT (the test file
        IS the behavioral spec). The self-host-comprehension faculty: the agent
        reading its own Python as a spec its graph self-model otherwise can't see."""
        import ast, os
        from collections import Counter
        path = os.path.join(self.root, "domains", module + ".py")
        if not os.path.exists(path):
            return {"module": module, "error": "no such faculty"}
        tree = ast.parse(open(path).read())
        shape = None
        if agent is not None:
            try:
                from domains.analogical_thinking import shape_hits
                v = Counter()
                for n in ast.walk(tree):
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        for s in shape_hits(agent.s, n.name.replace("_", " ") + " " + (ast.get_docstring(n) or "")):
                            v[s] += 1
                shape = v.most_common(1)[0][0] if v else None
            except Exception:
                shape = None
        tpath = os.path.join(self.root, "tests", "test_" + module + ".py")
        contracts = []
        if os.path.exists(tpath):
            for n in ast.walk(ast.parse(open(tpath).read())):
                if isinstance(n, ast.FunctionDef) and n.name.startswith("test"):
                    asserts = sum(1 for x in ast.walk(n) if isinstance(x, ast.Assert))
                    contracts.append({"name": n.name, "asserts": asserts})
        return {"module": module, "shape": shape,
                "test": ("tests/test_" + module + ".py") if os.path.exists(tpath) else None,
                "contracts": contracts, "n_contracts": len(contracts),
                "spec_source": "test_contract" if contracts else "none (no test -> behaviour must be traced)"}

    def verify_faculty(self, module, timeout=600):
        """VERIFY behavioral equivalence: run the faculty's test (its spec) — the
        migration GATE. Returns {ran, passed, summary}. After a candidate graph
        form is wired in place of the Python faculty, green == behaviour preserved."""
        import os, subprocess, sys as _sys
        rel = "tests/test_" + module + ".py"
        if not os.path.exists(os.path.join(self.root, rel)):
            return {"ran": False, "passed": None, "summary": "no test"}
        env = dict(os.environ)
        env["PYTHONPATH"] = "runners/dsl/python:.:scripts"
        try:
            r = subprocess.run([_sys.executable, "-m", "pytest", rel, "-q", "-p", "no:cacheprovider"],
                               cwd=str(self.root), capture_output=True, text=True, timeout=timeout, env=env)
        except Exception as e:
            return {"ran": False, "passed": None, "summary": f"{type(e).__name__}: {e}"}
        last = [l for l in r.stdout.splitlines() if l.strip()]
        return {"ran": True, "passed": r.returncode == 0, "summary": last[-1] if last else ""}

    # ----- VERIFY-GATED COMPOSER (the capstone: compose proposes, verify decides) --
    def migrate_faculty(self, module, candidates, agent=None):
        """Wire verify as the GATE on the composer. `candidates` is an ordered list
        of (label, apply_fn, revert_fn) graph-native proposals. Apply each; ACCEPT
        the first whose faculty TEST passes (verify_faculty); REVERT every rejected
        proposal. The composer proposes, verify decides — nothing is kept that does
        not preserve behaviour. Returns {accepted, attempts, spec}."""
        spec = self.comprehend_faculty(module, agent)
        if not spec.get("test"):
            return {"accepted": None,
                    "reason": "ungateable: no test (needs execution-tracing comprehension)",
                    "spec": spec, "attempts": []}
        attempts = []
        for label, apply_fn, revert_fn in candidates:
            try:
                apply_fn()
            except Exception as e:
                attempts.append((label, f"apply-error: {e}"))
                continue
            v = self.verify_faculty(module)
            if v.get("passed"):
                attempts.append((label, "ACCEPT (" + str(v.get("summary")) + ")"))
                return {"accepted": label, "attempts": attempts, "spec": spec}
            attempts.append((label, "reject (" + str(v.get("summary")) + ")"))
            try:
                revert_fn()
            except Exception:
                pass
        return {"accepted": None, "attempts": attempts, "spec": spec}

    def held_numeric_ops(self, term_rs_path=None):
        """The agent's FULL held numeric vocabulary, read from its OWN eval table
        (term.rs evaluate() match arms = the source of truth) — NOT a hand-picked
        subset. Every TermNode that evaluates its scalar children to a numeric
        Value is offered, tagged by arity form ('unary' {arg}, 'ab' {a,b}, 'items'
        {items}); index reductions (ArgMax/ArgMin) are excluded (they return an
        index, not a value). New numeric primitives the agent authors later are
        picked up automatically. Returns [(name, form), ...]."""
        import os as _os, re as _re
        path = term_rs_path or _os.path.join(self.root, "runners", "dsl", "src", "term.rs")
        src = open(path).read().splitlines()
        start = next((i for i, l in enumerate(src) if l.startswith("pub fn evaluate(")), 0)
        end = next((i for i in range(start + 1, len(src)) if _re.match(r"^(pub )?fn ", src[i])), len(src))
        body = src[start:end]
        forms = {"a, b": "ab", "items": "items", "arg": "unary"}
        arm = _re.compile(r"TermNode::([A-Za-z]\w*) \{ (a, b|items|arg) \} =>(.*)")
        ops, seen = [], set()
        i = 0
        while i < len(body):
            m = arm.search(body[i])
            if not m:
                i += 1
                continue
            name, fld, rest = m.group(1), m.group(2), m.group(3)
            chunk = rest
            if rest.strip().endswith("{"):                 # a block arm: gather to its close
                j = i + 1
                while j < len(body) and not arm.search(body[j]) and body[j] != "        }":
                    chunk += "\n" + body[j]
                    j += 1
            if _re.search(r"numeric_arg(max|min)\b", chunk):
                numeric = False                            # index op, not a value
            elif _re.search(r"numeric_(binary|variadic|minmax)\b", chunk):
                numeric = True
            elif ("Value::Float(" in chunk or "Value::Int(" in chunk) and "evaluate(arena" in chunk:
                numeric = True
            else:
                numeric = False
            if numeric and name not in seen:
                seen.add(name)
                ops.append((name, forms[fld]))
            i += 1
        return ops

    def _compose_candidates(self, operands, ops, max_depth, cap):
        """Lazily YIELD candidate Term compositions over `ops` (each (name, form),
        form in {'unary','ab','items'}) up to `max_depth`, breadth-first (shallow
        terms first), the growing pool bounded by `cap`. Lazy so the caller GATES
        each and stops at the first hit — success is fast no matter how large the
        held vocabulary is; `cap` only bounds the genuine-failure search."""
        def mk(opname, form, x, y):
            if form == "unary":
                return {"type": opname, "arg": x}
            if form == "ab":
                return {"type": opname, "a": x, "b": y}
            return {"type": opname, "items": [x, y]}
        pool = list(operands)          # operands + every layer so far (args for any op)
        prev = list(operands)          # the previous layer (the new frontier)
        n = 0
        for _d in range(max_depth):
            layer = []
            for opname, form in ops:
                if form == "unary":
                    for x in prev:
                        t = mk(opname, form, x, None); layer.append(t); n += 1
                        yield t
                        if n >= cap:
                            return
                else:
                    for x in pool:
                        for y in prev:
                            t = mk(opname, form, x, y); layer.append(t); n += 1
                            yield t
                            if n >= cap:
                                return
            pool = pool + layer
            prev = layer

    # ----- rung-2 FREE SEARCH fed into the VERIFY gate (autonomous composition) ----
    def compose_search_gated(self, agent, points, operands, ops=None, max_depth=2,
                             tol=1e-6, cap=600000):
        """Enumerate candidate Term compositions over held binary `ops` up to
        `max_depth`, and GATE each by evaluating it on behavioural `points`
        ([{env, expected}], the faculty's test contract). Return the FIRST
        candidate satisfying ALL points {found, term, tried}; if none can, return
        {found: False, impasse: ...} — a real primitive gap, NOT a faked answer
        (the no-donkey designer). Generation is free (not hand-fed); acceptance is
        the behavioural gate."""
        ops = ops or self.held_numeric_ops()          # the WHOLE held vocabulary, not a subset

        def gate(term):
            for pt in points:
                try:
                    val = float(agent.inner.evaluate(term, pt["env"]))
                except Exception:
                    return False
                if not (-1e308 < val < 1e308) or abs(val - pt["expected"]) > tol:
                    return False                          # reject NaN/inf (e.g. 0*inf) too
            return True

        tried = 0
        for term in self._compose_candidates(operands, ops, max_depth, cap):
            tried += 1
            if gate(term):                                # gate lazily, stop at the FIRST hit
                return {"found": True, "term": term, "tried": tried}
        return {"found": False, "tried": tried,
                "impasse": ("the agent's FULL held numeric vocabulary (" + ", ".join(n for n, _ in ops) +
                            ") cannot satisfy the gate on all points within depth %d / %d candidates -> "
                            "escalate depth/operands, or a genuinely new primitive is needed "
                            "(HumanImpasse, no donkey)" % (max_depth, tried))}

    # ----- TWO-STAGE gate: free search -> points pre-filter -> REAL-TEST final gate
    def migrate_function(self, agent, module, fn_name, fn_anchor, env_map, points,
                         operands, ops=None, max_depth=2, want=6, tol=1e-6):
        """Free search -> POINTS pre-filter -> collect up to `want` survivors ->
        WIRE each as fn_name (edit fn_anchor to evaluate the Term) and run
        verify_faculty (the REAL test) as the FINAL gate. Accept the first that
        passes the real test (overfits the points-gate let through are killed
        here), else honest impasse. env_map = {term_var: param_name}."""
        ops = ops or self.held_numeric_ops()          # the WHOLE held vocabulary, not a subset

        def gate(term):
            for pt in points:
                try:
                    v = float(agent.inner.evaluate(term, pt["env"]))
                except Exception:
                    return False
                if not (-1e308 < v < 1e308) or abs(v - pt["expected"]) > tol:
                    return False                          # reject NaN/inf (e.g. 0*inf) too
            return True

        survivors = []
        for term in self._compose_candidates(operands, ops, max_depth, 600000):
            if gate(term):                                # gate lazily, collect up to `want`
                survivors.append(term)
                if len(survivors) >= want:
                    break
        env_src = "{" + ", ".join("%r: %s" % (k, p) for k, p in env_map.items()) + "}"
        relpath = "domains/" + module + ".py"
        results = []
        for term in survivors:
            stub = ("    import substrate_rs as _srs\n"
                    "    return float(_srs._native.Substrate().evaluate(%r, %s))" % (term, env_src))
            r = self.mod.edit(relpath, fn_anchor, stub, check=False)
            if not r.get("ok"):
                results.append((term, "wire-fail")); continue
            v = self.verify_faculty(module)
            self.mod.restore(relpath)
            results.append((term, "PASS" if v.get("passed") else "reject: " + str(v.get("summary"))))
            if v.get("passed"):
                return {"accepted": term, "n_survivors": len(survivors), "results": results}
        return {"accepted": None, "n_survivors": len(survivors), "results": results,
                "impasse": "all points-survivors REJECTED by the REAL test (full semantics) -> a primitive is needed"}

    # ----- parameterised builders (install_*(substrate/agent, path/data)) -----
    def parameterized_builders(self):
        """install_* funcs (present domains) taking a 2nd required positional —
        a path/data/agent arg — so they don't fit the zero-arg load_one_seed
        swap. Returns [(module, fn, [param_names])]."""
        import glob, importlib, inspect, os, re
        out = []
        for p in glob.glob(str(self.root / "domains" / "*.py")):
            mod = os.path.basename(p)[:-3]
            src = open(p).read()
            for fn in re.findall(r"def (install_\w+)\(", src):
                try:
                    f = getattr(importlib.import_module(f"domains.{mod}"), fn, None)
                    if f is None:
                        continue
                    req = [pp for pp in inspect.signature(f).parameters.values()
                           if pp.default is inspect.Parameter.empty
                           and pp.kind in (pp.POSITIONAL_ONLY, pp.POSITIONAL_OR_KEYWORD)]
                    if len(req) >= 2:
                        out.append((mod, fn, [pp.name for pp in req]))
                except Exception:
                    continue
        return out

    def analyze_parameterized(self):
        """CLASSIFY each parameterised builder so the right migration is chosen:
          path_loader        - loads a JSON path (a canonical seed) into typed
                               graph nodes -> migratable by FULL-GRAPH CAPTURE
                               (run with the canonical path + deps, capture the
                               new nodes/edges to a seed load_one_seed replays).
          agent_replay_dead  - drives the DELETED CuriousAgent interface
                               (learn_from_teacher / mind_graph) -> NOT a graph
                               builder; cannot run on the live substrate.
          utility            - no path/agent install path that builds graph data
                               (e.g. a baker whose tests use other functions).
        Pure static read of each builder's source + signature."""
        import re
        out = []
        for mod, fn, params in self.parameterized_builders():
            src = open(str(self.root / "domains" / f"{mod}.py")).read()
            dead = any(s in src for s in ("learn_from_teacher", "mind_graph", "_concept_nodes"))
            loads_path = ("json.load" in src or "load_" in src) and \
                any(p in ("path",) for p in params)
            builds_nodes = "add_node(" in src
            # FACULTY check: does the MODULE export ENGINE functions beyond its
            # load_/install_ data-loaders? If so the module is a live faculty
            # (e.g. compile_rule / run_pipeline_by_name) — its loader can't be
            # swapped to load_one_seed AND the module burned; it stays.
            m = re.search(r"__all__\s*=\s*\[([^\]]*)\]", src)
            exports = re.findall(r'"([A-Za-z_]\w*)"', m.group(1)) if m else []
            engine = [e for e in exports if not e.startswith(("load_", "install_"))]
            # FINGERPRINT-wired loaders compute edges to nameless nodes at install
            # time — not declaratively reproducible by load_one_seed's relations.
            fingerprint = "fingerprint" in src
            if dead:
                kind = "agent_replay_dead"
            elif engine:
                kind = "faculty"          # module is an engine; keep it
            elif fingerprint and loads_path:
                kind = "fingerprint_loader"   # computed wiring; not declaratively migratable
            elif loads_path and builds_nodes:
                kind = "path_loader"
            else:
                kind = "utility"
            out.append({"module": mod, "fn": fn, "params": params, "kind": kind,
                        "engine_exports": engine})
        return out

    # ----- builder graph-equivalence ------------------------------------
    def _fresh_substrate(self):
        import substrate_rs as srs
        s = srs._native.Substrate()
        types = ("Microtheory", "Concept", "Rule", "DerivationRule", "Frame",
                 "Reflex", "Production", "PrimitiveSpec", "DesignPattern",
                 "ProgrammingLanguage", "CodeTarget", "ShapePrototype",
                 "CapabilityAxis", "SourceEvent")
        edges = ("has_concept", "has_rule", "in_category", "genlMt", "refers_to",
                 "depends_on", "built_from", "decomposes", "best_for",
                 "applies_when", "applies_to", "implements", "has_shape", "of_language")
        for a in types:
            for b in types:
                for et in edges:
                    try:
                        s.add_production({"src": {"type": a, "var": "s"}, "edge_type": et,
                                          "tgt": {"type": b, "var": "t"}, "where": None,
                                          "weight": {"type": "Lit", "value": 1.0},
                                          "provenance": "migrate"})
                    except Exception:
                        pass
        return s

    def _snapshot(self, s):
        d = s.graph_to_dict()
        nm, nodes = {}, {}
        for n in d.get("nodes", []):
            x = (n.get("attrs") or {}).get("name")
            nm[n["id"]] = x
            if x:
                nodes[(n.get("type"), x)] = dict(n.get("attrs") or {})
        edges = set()
        for e in d.get("edges", []):
            a, b = nm.get(e.get("src")), nm.get(e.get("tgt"))
            if a and b:
                edges.add((a, e.get("type"), b))
        return nodes, edges

    def _run_builder(self, module, fns):
        import importlib
        import inspect
        s = self._fresh_substrate()
        mod = importlib.import_module(f"domains.{module}")
        ran = 0
        for fn_name in fns:
            fn = getattr(mod, fn_name, None)
            if fn is None:
                continue
            req = [p for p in inspect.signature(fn).parameters.values()
                   if p.default is inspect.Parameter.empty
                   and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
            if len(req) != 1:
                return None
            try:
                fn(s)
                ran += 1
            except Exception:
                return None
        return self._snapshot(s) if ran else None

    def _seed_boot_snapshot(self):
        from substrate.world_adapter import WorldAdapter
        from substrate.boot_all import load_all_seeds
        a = WorldAdapter(seeds=())
        load_all_seeds(a)
        return self._snapshot(a.s)

    def discover_builders(self):
        """Split install_*_seed builders into equivalent / gaps / in_use."""
        domains, kept = self._referenced(roots_only=True)
        blds = self._builders()
        seed_nodes, seed_edges = self._seed_boot_snapshot()
        equivalent, gaps, in_use, unverifiable = [], [], [], []
        for d, fns in sorted(blds.items()):
            if d in kept:
                in_use.append(d)
                continue
            snap = self._run_builder(d, fns)
            if snap is None:
                unverifiable.append(d)
                continue
            bn, be = snap
            miss_n = {k: v for k, v in bn.items() if k not in seed_nodes}
            miss_e = [e for e in be if e not in seed_edges]
            if not miss_n and not miss_e:
                equivalent.append(d)
            else:
                gaps.append({"module": d, "miss_n": miss_n, "miss_e": miss_e})
        return {"equivalent": equivalent, "gaps": gaps,
                "in_use": in_use, "unverifiable": unverifiable}

    # ----- capture-to-seed ----------------------------------------------
    def capture_to_seed(self, gap):
        """Write a gap-builder's missing nodes/edges (from discover_builders)
        into its seed JSON as extra_nodes + relations, so load_one_seed
        reproduces it. Returns the seed path."""
        d = gap["module"]
        extra = []
        for (t, nm), attrs in sorted(gap["miss_n"].items()):
            en = {"type": t, "name": nm}
            for k, v in attrs.items():
                if k != "name" and isinstance(v, (str, int, float, bool, list)):
                    en[k] = v
            extra.append(en)
        rels = [{"src": s_, "edge": et, "tgt": t_} for (s_, et, t_) in sorted(gap["miss_e"])]
        path = self.root / "seeds" / f"{d}.json"
        seed = json.load(open(path)) if path.exists() else {
            "id": d, "version": "1.0.0", "depends_on": [],
            "description": f"captured from domains/{d}.py"}
        if extra:
            seed["extra_nodes"] = extra
        if rels:
            seed["relations"] = rels
        json.dump(seed, open(path, "w"), indent=1, ensure_ascii=False)
        return str(path)

    # ----- the whole migration ------------------------------------------
    def run(self, apply=False, builders=False):
        """Discover (and, with apply, burn) dead boats. With builders=True also
        capture+burn the equivalent/gap seed-builders. Burns go through the
        agent's SelfModification.burn (audited, git-recoverable)."""
        report = {"applied": apply}
        orphans = self.discover_orphans()
        report["orphans"] = orphans
        burned = []
        if apply and self.mod is not None:
            for d in orphans:
                if self.mod.burn(f"domains/{d}.py").get("ok"):
                    burned.append(d)
        if builders:
            binfo = self.discover_builders()
            report["builders"] = {k: (v if k != "gaps" else [g["module"] for g in v])
                                  for k, v in binfo.items()}
            if apply and self.mod is not None:
                for g in binfo["gaps"]:
                    self.capture_to_seed(g)
                # re-verify after capture, then burn equivalent + closed gaps
                for d in self.discover_builders()["equivalent"]:
                    if self.mod.burn(f"domains/{d}.py").get("ok"):
                        burned.append(d)
        report["burned"] = burned
        report["n_burned"] = len(burned)
        return report


__all__ = ["Migrator"]
