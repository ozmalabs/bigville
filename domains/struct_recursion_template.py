"""struct_recursion_template — a DETERMINISTIC, NAME-PARAMETERISED template that
emits the Rust for a STRUCTURAL-RECURSION primitive (the AntiUnify family) across
its TermNode homes. Part 2 of the self-author fix: the ~8 prior templates miss the
recursion shapes (AntiUnify / Substitute / Unify / StructSim / AntiUnifyWitness),
so the rung-4 Rust path could not self-author them. This template covers the whole
family as ONE shape parameterised by (recur_kind = leaf-op + combine-op + return).

NO LLM. The agent SPECIFIES (a graph-resident spec choosing recur_kind + name); this
RENDERS deterministically (string templates). Same contract + key naming as
arity_homes.emit_binary_scalar_leaf (name-parameterised, keys carry 'group'/'helper'
so self_extend.plan routes them; an anchor of the SAME recur_kind has the SAME keys,
so set(frags)==set(anchors) holds).

The shape: a single-collection Term `Name { values, wild }` (like AntiUnify) whose
evaluator calls a self-contained recursive helper `fn <name_lower>_recur(...)`
deriving its name from spec["name"] — so two primitives of the same recur_kind do
NOT collide (fixes the diagnosed E0428).

recur_kind ∈ {
  "meet_wild"   : leaf = wild-if-differ (the AntiUnify MEET; over the FULL collection),
  "join_fuse"   : leaf = fuse-distinct-into-frozenset (the Unify JOIN),
  "graded_sim"  : leaf = exp(-|a-b|) over the FIRST TWO, combine = mean (the StructSim),
}
All recurse Tuple element-wise + Set→intersection/union; deterministic bodies below.
"""
from __future__ import annotations

# ---- the deterministic recursive-helper bodies, parameterised only by fn name ----
def _meet_wild_body(fn: str) -> str:
    # the AntiUnify MEET over a collection: agree→fix, differ→wild; recurse tuples/sets.
    return (
        f"fn {fn}(vals: &[Value], wild: &Value) -> Value {{\n"
        f"    if vals.is_empty() {{ return wild.clone(); }}\n"
        f"    let first = &vals[0];\n"
        f"    if vals[1..].iter().all(|v| v == first) {{ return first.clone(); }}\n"
        f"    if vals.iter().all(|v| matches!(v, Value::Tuple(_))) {{\n"
        f"        let tups: Vec<&std::sync::Arc<smallvec::SmallVec<[Value; 4]>>> = vals.iter()\n"
        f"            .map(|v| match v {{ Value::Tuple(t) => t, _ => unreachable!() }}).collect();\n"
        f"        let len = tups[0].len();\n"
        f"        if tups.iter().all(|t| t.len() == len) {{\n"
        f"            let mut out: smallvec::SmallVec<[Value; 4]> = smallvec::SmallVec::with_capacity(len);\n"
        f"            for i in 0..len {{\n"
        f"                let col: Vec<Value> = tups.iter().map(|t| t[i].clone()).collect();\n"
        f"                out.push({fn}(&col, wild));\n"
        f"            }}\n"
        f"            return Value::Tuple(std::sync::Arc::new(out));\n"
        f"        }}\n"
        f"    }}\n"
        f"    if vals.iter().all(|v| matches!(v, Value::Set(_) | Value::FrozenSet(_))) {{\n"
        f"        let getset = |v: &Value| -> Vec<Value> {{ match v {{\n"
        f"            Value::Set(s) | Value::FrozenSet(s) => s.to_vec(), _ => vec![] }} }};\n"
        f"        let mut inter = getset(&vals[0]);\n"
        f"        for v in &vals[1..] {{ let s = getset(v); inter.retain(|x| s.iter().any(|y| y == x)); }}\n"
        f"        return Value::make_frozenset(inter);\n"
        f"    }}\n"
        f"    wild.clone()\n"
        f"}}"
    )


def _join_fuse_body(fn: str) -> str:
    # the Unify JOIN: agree→fix, differ-leaf→fuse into a frozenset; recurse tuples; sets→union.
    return (
        f"fn {fn}(vals: &[Value], wild: &Value) -> Value {{\n"
        f"    let concrete: Vec<&Value> = vals.iter().filter(|v| *v != wild).collect();\n"
        f"    if concrete.is_empty() {{ return wild.clone(); }}\n"
        f"    let first = concrete[0];\n"
        f"    if concrete[1..].iter().all(|v| *v == first) {{ return first.clone(); }}\n"
        f"    if concrete.iter().all(|v| matches!(v, Value::Tuple(_))) {{\n"
        f"        let tups: Vec<&std::sync::Arc<smallvec::SmallVec<[Value; 4]>>> = concrete.iter()\n"
        f"            .map(|v| match v {{ Value::Tuple(t) => t, _ => unreachable!() }}).collect();\n"
        f"        let len = tups[0].len();\n"
        f"        if tups.iter().all(|t| t.len() == len) {{\n"
        f"            let mut out: smallvec::SmallVec<[Value; 4]> = smallvec::SmallVec::with_capacity(len);\n"
        f"            for i in 0..len {{\n"
        f"                let col: Vec<Value> = tups.iter().map(|t| t[i].clone()).collect();\n"
        f"                out.push({fn}(&col, wild));\n"
        f"            }}\n"
        f"            return Value::Tuple(std::sync::Arc::new(out));\n"
        f"        }}\n"
        f"    }}\n"
        f"    if concrete.iter().all(|v| matches!(v, Value::Set(_) | Value::FrozenSet(_))) {{\n"
        f"        let mut members: Vec<Value> = Vec::new();\n"
        f"        for v in &concrete {{ let s = match v {{ Value::Set(s) | Value::FrozenSet(s) => s.to_vec(), _ => vec![] }};\n"
        f"            for x in s {{ if !members.iter().any(|y| *y == x) {{ members.push(x); }} }} }}\n"
        f"        return Value::make_frozenset(members);\n"
        f"    }}\n"
        f"    let mut fused: Vec<Value> = Vec::new();\n"
        f"    for v in &concrete {{ if !fused.iter().any(|y| y == *v) {{ fused.push((*v).clone()); }} }}\n"
        f"    Value::make_frozenset(fused)\n"
        f"}}"
    )


def _graded_sim_body(fn: str) -> str:
    # the StructSim: graded structural similarity in [0,1] over the FIRST TWO members.
    return (
        f"fn {fn}(vals: &[Value], wild: &Value) -> Value {{\n"
        f"    fn sim(a: &Value, b: &Value, wild: &Value) -> f64 {{\n"
        f"        if a == wild || b == wild {{ return 1.0; }}\n"
        f"        let as_vec = |v: &Value| -> Option<Vec<f64>> {{ match v {{\n"
        f"            Value::Tuple(t) => {{ let mut o = Vec::with_capacity(t.len());\n"
        f"                for x in t.iter() {{ match x {{ Value::Float(f) => o.push(*f),\n"
        f"                    Value::Int(i) => o.push(*i as f64), _ => return None }} }}\n"
        f"                if o.is_empty() {{ None }} else {{ Some(o) }} }}\n"
        f"            _ => None }} }};\n"
        f"        if let (Some(va), Some(vb)) = (as_vec(a), as_vec(b)) {{\n"
        f"            if va.len() == vb.len() {{ let mut s = 0.0;\n"
        f"                for i in 0..va.len() {{ let d = va[i] - vb[i]; s += d * d; }}\n"
        f"                return (-s.sqrt()).exp(); }}\n"
        f"            return 0.0;\n"
        f"        }}\n"
        f"        if let (Value::Tuple(ta), Value::Tuple(tb)) = (a, b) {{\n"
        f"            let n = ta.len().min(tb.len()); let denom = ta.len().max(tb.len());\n"
        f"            if denom == 0 {{ return 1.0; }} if n == 0 {{ return 0.0; }}\n"
        f"            let mut acc = 0.0; for i in 0..n {{ acc += sim(&ta[i], &tb[i], wild); }}\n"
        f"            return (acc / n as f64) * (n as f64 / denom as f64);\n"
        f"        }}\n"
        f"        if a == b {{ 1.0 }} else {{ 0.0 }}\n"
        f"    }}\n"
        f"    if vals.len() < 2 {{ return Value::Float(1.0); }}\n"
        f"    Value::Float(sim(&vals[0], &vals[1], wild))\n"
        f"}}"
    )


def _witness_body(fn: str) -> str:
    # the AntiUnifyWitness MEET that RETAINS its witnesses: returns (template, subs)
    # where subs[i] is a Vec of (position-PATH, residue) for instance i. Recurses
    # Dict/Tuple element-wise threading `path`; at a leaf disagreement records each
    # instance's value at the path. The evaluator wraps subs into (template, sigmas).
    return (
        f"fn {fn}(vals: &[Value], wild: &Value)\n"
        f"    -> (Value, Vec<Vec<(Value, Value)>>) {{\n"
        f"    fn go(vals: &[Value], wild: &Value, path: &mut Vec<Value>,\n"
        f"          subs: &mut [Vec<(Value, Value)>]) -> Value {{\n"
        f"        if vals.is_empty() {{ return wild.clone(); }}\n"
        f"        let first = &vals[0];\n"
        f"        if vals[1..].iter().all(|v| v == first) {{ return first.clone(); }}\n"
        f"        if vals.iter().all(|v| matches!(v, Value::Tuple(_))) {{\n"
        f"            let tups: Vec<&std::sync::Arc<smallvec::SmallVec<[Value; 4]>>> = vals.iter()\n"
        f"                .map(|v| match v {{ Value::Tuple(t) => t, _ => unreachable!() }}).collect();\n"
        f"            let len = tups[0].len();\n"
        f"            if tups.iter().all(|t| t.len() == len) {{\n"
        f"                let mut out: smallvec::SmallVec<[Value; 4]> = smallvec::SmallVec::with_capacity(len);\n"
        f"                for i in 0..len {{\n"
        f"                    let col: Vec<Value> = tups.iter().map(|t| t[i].clone()).collect();\n"
        f"                    path.push(Value::Int(i as i64));\n"
        f"                    out.push(go(&col, wild, path, subs));\n"
        f"                    path.pop();\n"
        f"                }}\n"
        f"                return Value::Tuple(std::sync::Arc::new(out));\n"
        f"            }}\n"
        f"        }}\n"
        f"        let p = Value::Tuple(std::sync::Arc::new(\n"
        f"            smallvec::SmallVec::from_vec(path.clone())));\n"
        f"        for (i, v) in vals.iter().enumerate() {{ subs[i].push((p.clone(), v.clone())); }}\n"
        f"        wild.clone()\n"
        f"    }}\n"
        f"    let mut subs: Vec<Vec<(Value, Value)>> = vec![Vec::new(); vals.len()];\n"
        f"    let mut path: Vec<Value> = Vec::new();\n"
        f"    let template = go(vals, wild, &mut path, &mut subs);\n"
        f"    (template, subs)\n"
        f"}}"
    )


def _substitute_body(fn: str) -> str:
    # the Substitute JOIN-step: walk `template`, replace each WILD by sigma[path];
    # recurse into nested Tuples (so a higher-order template is instantiated). The
    # inverse of the witness walk. Two-arg: (template, sigma) -> term.
    return (
        f"fn {fn}(template: &Value, sigma: &[(Value, Value)], wild: &Value) -> Value {{\n"
        f"    fn lookup<'a>(sigma: &'a [(Value, Value)], path: &Value) -> Option<&'a Value> {{\n"
        f"        sigma.iter().find(|(k, _)| k == path).map(|(_, v)| v)\n"
        f"    }}\n"
        f"    fn go(t: &Value, sigma: &[(Value, Value)], wild: &Value, path: &mut Vec<Value>) -> Value {{\n"
        f"        if t == wild {{\n"
        f"            let p = Value::Tuple(std::sync::Arc::new(smallvec::SmallVec::from_vec(path.clone())));\n"
        f"            return match lookup(sigma, &p) {{ Some(v) => v.clone(), None => wild.clone() }};\n"
        f"        }}\n"
        f"        match t {{\n"
        f"            Value::Tuple(items) => {{\n"
        f"                let mut out: smallvec::SmallVec<[Value; 4]> = smallvec::SmallVec::with_capacity(items.len());\n"
        f"                for (i, it) in items.iter().enumerate() {{\n"
        f"                    path.push(Value::Int(i as i64));\n"
        f"                    out.push(go(it, sigma, wild, path));\n"
        f"                    path.pop();\n"
        f"                }}\n"
        f"                Value::Tuple(std::sync::Arc::new(out))\n"
        f"            }}\n"
        f"            other => other.clone(),\n"
        f"        }}\n"
        f"    }}\n"
        f"    let mut path: Vec<Value> = Vec::new();\n"
        f"    go(template, sigma, wild, &mut path)\n"
        f"}}"
    )


_BODIES = {
    "meet_wild": _meet_wild_body,
    "join_fuse": _join_fuse_body,
    "graded_sim": _graded_sim_body,
    "witness": _witness_body,
    "substitute": _substitute_body,
}

# arg-shape per recur_kind: single-collection {values, wild} (the MEET/JOIN/sim/
# witness family) vs two-arg {template, sigma, wild} (the substitute family).
_TWO_ARG = {"substitute"}
_WITNESS = {"witness"}

import os as _os


def anchor_from_live(name: str, recur_kind: str) -> dict:
    """Build the bootstrap anchor for a recur_kind by EXTRACTING the verbatim
    live-source fragments of an existing same-shape Term `name` (e.g. AntiUnifyWitness
    for witness, Substitute for substitute). Reads the current term.rs/jsonio.rs/
    reflect.rs and pulls each home's exact text by matching the variant — so the
    anchor lines are present in source by construction (no hand-transcription, robust
    to live formatting). The emit's helper key is excluded (helpers are appended
    fresh). Returns {key -> verbatim fragment}, keyed identically to the emit."""
    src_dir = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                            "runners", "dsl", "src")
    files = {f: open(_os.path.join(src_dir, f)).read()
             for f in ("term.rs", "jsonio.rs", "reflect.rs")}
    # the emit gives us the KEY SET + the per-key opening pattern; we replace each
    # emitted (possibly mis-formatted) fragment with the verbatim live block.
    emit = emit_structural_recursion(name, recur_kind)

    def first_line(frag: str) -> str:
        return frag.split("\n", 1)[0]

    def live_block(text: str, opener: str) -> str | None:
        # `opener` is the emit's first line with the NEW name; the live anchor uses
        # the SOURCE name — so search by the opener with the new name swapped back to
        # `name`. We pass the source-named opener in via the caller; here we match it
        # verbatim and read a brace-balanced block (or a single comma-terminated line).
        i = text.find(opener)
        if i < 0:
            return None
        seg = text[i:]
        # brace/bracket balance from the opener; the arm ends when depth returns to 0
        # AND the line ends with a terminator (',' / '}' / ']' / '},' / ']),').
        depth = 0
        out = []
        started = False
        for ln in seg.split("\n"):
            out.append(ln)
            for ch in ln:
                if ch in "{[(":
                    depth += 1; started = True
                elif ch in "}])":
                    depth -= 1
            stripped = ln.rstrip()
            if depth <= 0 and (started or stripped.endswith(",")) \
                    and (stripped.endswith(",") or stripped.endswith("}") or stripped.endswith("]),")):
                break
        return "\n".join(out)

    anchors = {}
    for k, frag in emit.items():
        if "helper" in k:
            anchors[k] = ""        # helper appended fresh, never anchored
            continue
        f = k.split(" ", 1)[0]
        opener = first_line(frag)
        block = live_block(files[f], opener)
        anchors[k] = block if block is not None else frag
    return anchors


# The BOOTSTRAP anchor for `meet_wild`: the held, live AntiUnify Term, whose source
# lines are verbatim in the tree. self_extend.plan needs anchor lines present in
# source for every non-helper key; AntiUnify supplies them (the family's first
# member is live). Once one template-emitted primitive of a recur_kind is live, it
# can serve as the anchor for the next — but AntiUnify lets `meet_wild` self-author
# from the existing tree with no prior install. (graded_sim -> StructSim live;
# join_fuse -> Unify live — same idea; meet_wild/AntiUnify is the one wired here.)
def antiunify_anchor() -> dict:
    """The verbatim live-source AntiUnify fragments, keyed identically to a
    `meet_wild` emit, so plan(spec, anchor_spec=ANTIUNIFY_ANCHOR_FRAGS) finds every
    anchor in the tree. NOT emitted — these are the exact live lines."""
    return {
        "term.rs (enum variant)": "    AntiUnify { values: TermIdx, wild: Sym },",
        "term.rs (copy_subtree arm)":
            "        TermNode::AntiUnify { values, wild } =>\n"
            "            TermNode::AntiUnify { values: copy_subtree(src, dst, values), wild },",
        "term.rs (evaluator arm)":
            "        TermNode::AntiUnify { values, wild } => {\n"
            "            let v = evaluate(arena, *values, env, ctx);\n"
            "            // The instances may arrive as any collection Value; iterate its\n"
            "            // members. A non-collection degenerates to a single instance.\n"
            "            let insts: Vec<Value> = match &v {\n"
            "                Value::Set(s) | Value::FrozenSet(s) => s.to_vec(),\n"
            "                Value::Tuple(t) => t.to_vec(),\n"
            "                Value::None => vec![],\n"
            "                other => vec![other.clone()],\n"
            "            };\n"
            "            let wild_val = Value::Tuple(std::sync::Arc::new(\n"
            "                smallvec::smallvec![Value::Str(*wild)]));\n"
            "            anti_unify_values(&insts, &wild_val)\n"
            "        }",
        "term.rs (children arm)":
            "        TermNode::AntiUnify { values, .. } => out.push(*values),",
        "term.rs (helper)": "",   # helper is appended fresh, never anchored
        "jsonio.rs (name arm)": '        TermNode::AntiUnify { .. } => "AntiUnify",',
        "jsonio.rs (serialize arm)":
            "        TermNode::AntiUnify { values, .. } => {\n"
            "            // `wild` is a fixed sentinel re-derived on parse — not emitted.\n"
            '            m.insert("values".into(), child(*values, arena, interner));\n'
            "        }",
        "jsonio.rs (parse arm)":
            '        "AntiUnify" => TermNode::AntiUnify {\n'
            '            values: child_of("values", obj, arena, interner, variant)?,\n'
            '            wild: interner.intern("·?·"),\n'
            "        },",
        "reflect.rs (children arm)":
            '        TermNode::AntiUnify { values, wild } => ("AntiUnify", vec![\n'
            '            Child { name: "values", child: *values },\n'
            '            ScalarSym { name: "wild", value: *wild },\n'
            "        ]),",
        "reflect.rs (parse arm)":
            '        "AntiUnify" => TermNode::AntiUnify {\n'
            '            values: take_child!("values"),\n'
            '            wild: get_sym("wild")?,\n'
            "        },",
    }


def _emit_witness_eval(name: str, fn: str) -> str:
    # witness evaluator: run the (template, subs) helper, wrap subs into a Tuple of
    # path->value Dicts, return (template, sigmas). Mirrors the live AntiUnifyWitness.
    return (
        f"        TermNode::{name} {{ values, wild }} => {{\n"
        f"            let v = evaluate(arena, *values, env, ctx);\n"
        f"            let insts: Vec<Value> = match &v {{\n"
        f"                Value::Set(s) | Value::FrozenSet(s) => s.to_vec(),\n"
        f"                Value::Tuple(t) => t.to_vec(),\n"
        f"                Value::None => vec![],\n"
        f"                other => vec![other.clone()],\n"
        f"            }};\n"
        f"            let wild_val = Value::Tuple(std::sync::Arc::new(\n"
        f"                smallvec::smallvec![Value::Str(*wild)]));\n"
        f"            let (template, subs) = {fn}(&insts, &wild_val);\n"
        f"            let sigmas: SmallVec<[Value; 4]> = subs.into_iter()\n"
        f"                .map(|pairs| {{\n"
        f"                    let mut entries: Vec<(Value, Value)> = pairs;\n"
        f"                    entries.sort_by(|a, b| cmp_value(&a.0, &b.0));\n"
        f"                    Value::Dict(std::sync::Arc::from(entries))\n"
        f"                }})\n"
        f"                .collect();\n"
        f"            Value::Tuple(std::sync::Arc::new(smallvec::smallvec![\n"
        f"                template, Value::Tuple(std::sync::Arc::new(sigmas))]))\n"
        f"        }}"
    )


def _emit_single_collection(name: str, recur_kind: str, fn: str, helper: str) -> dict:
    """The `Name { values, wild }` family (meet_wild/join_fuse/graded_sim/witness)."""
    evaluator = _emit_witness_eval(name, fn) if recur_kind in _WITNESS else (
        f"        TermNode::{name} {{ values, wild }} => {{\n"
        f"            let v = evaluate(arena, *values, env, ctx);\n"
        f"            let insts: Vec<Value> = match &v {{\n"
        f"                Value::Set(s) | Value::FrozenSet(s) => s.to_vec(),\n"
        f"                Value::Tuple(t) => t.to_vec(),\n"
        f"                Value::None => vec![],\n"
        f"                other => vec![other.clone()],\n"
        f"            }};\n"
        f"            let wild_val = Value::Tuple(std::sync::Arc::new(\n"
        f"                smallvec::smallvec![Value::Str(*wild)]));\n"
        f"            {fn}(&insts, &wild_val)\n"
        f"        }}")
    return {
        "term.rs (enum variant)": f"    {name} {{ values: TermIdx, wild: Sym }},",
        "term.rs (copy_subtree arm)":
            f"        TermNode::{name} {{ values, wild }} =>\n"
            f"            TermNode::{name} {{ values: copy_subtree(src, dst, values), wild }},",
        "term.rs (evaluator arm)": evaluator,
        "term.rs (children arm)":
            f"        TermNode::{name} {{ values, .. }} => out.push(*values),",
        "term.rs (helper)": helper,
        "jsonio.rs (name arm)": f'        TermNode::{name} {{ .. }} => "{name}",',
        "jsonio.rs (serialize arm)":
            f"        TermNode::{name} {{ values, .. }} => {{\n"
            f'            m.insert("values".into(), child(*values, arena, interner));\n'
            f"        }}",
        "jsonio.rs (parse arm)":
            f'        "{name}" => TermNode::{name} {{\n'
            f'            values: child_of("values", obj, arena, interner, variant)?,\n'
            f'            wild: interner.intern("·?·"),\n'
            f"        }},",
        "reflect.rs (children arm)":
            f'        TermNode::{name} {{ values, wild }} => ("{name}", vec![\n'
            f'            Child {{ name: "values", child: *values }},\n'
            f'            ScalarSym {{ name: "wild", value: *wild }},\n'
            f"        ]),",
        "reflect.rs (parse arm)":
            f'        "{name}" => TermNode::{name} {{\n'
            f'            values: take_child!("values"),\n'
            f'            wild: get_sym("wild")?,\n'
            f"        }},",
    }


def _emit_two_arg(name: str, fn: str, helper: str) -> dict:
    """The two-arg `Name { template, sigma, wild }` family (substitute): walk the
    template, replace WILDs per the sigma Dict. Mirrors the live Substitute."""
    return {
        "term.rs (enum variant)": f"    {name} {{ template: TermIdx, sigma: TermIdx, wild: Sym }},",
        "term.rs (copy_subtree arm)":
            f"        TermNode::{name} {{ template, sigma, wild }} =>\n"
            f"            TermNode::{name} {{ template: copy_subtree(src, dst, template),\n"
            f"                                   sigma: copy_subtree(src, dst, sigma), wild }},",
        "term.rs (evaluator arm)":
            f"        TermNode::{name} {{ template, sigma, wild }} => {{\n"
            f"            let t = evaluate(arena, *template, env, ctx);\n"
            f"            let sg = evaluate(arena, *sigma, env, ctx);\n"
            f"            let pairs: Vec<(Value, Value)> = match &sg {{\n"
            f"                Value::Dict(d) => d.to_vec(),\n"
            f"                _ => vec![],\n"
            f"            }};\n"
            f"            let wild_val = Value::Tuple(std::sync::Arc::new(\n"
            f"                smallvec::smallvec![Value::Str(*wild)]));\n"
            f"            {fn}(&t, &pairs, &wild_val)\n"
            f"        }}",
        "term.rs (children arm)":
            f"        TermNode::{name} {{ template, sigma, .. }} => {{ out.push(*template); out.push(*sigma); }}",
        "term.rs (helper)": helper,
        "jsonio.rs (name arm)": f'        TermNode::{name} {{ .. }} => "{name}",',
        "jsonio.rs (serialize arm)":
            f"        TermNode::{name} {{ template, sigma, .. }} => {{\n"
            f'            m.insert("template".into(), child(*template, arena, interner));\n'
            f'            m.insert("sigma".into(), child(*sigma, arena, interner));\n'
            f"        }}",
        "jsonio.rs (parse arm)":
            f'        "{name}" => TermNode::{name} {{\n'
            f'            template: child_of("template", obj, arena, interner, variant)?,\n'
            f'            sigma: child_of("sigma", obj, arena, interner, variant)?,\n'
            f'            wild: interner.intern("·?·"),\n'
            f"        }},",
        "reflect.rs (children arm)":
            f'        TermNode::{name} {{ template, sigma, wild }} => ("{name}", vec![\n'
            f'            Child {{ name: "template", child: *template }},\n'
            f'            Child {{ name: "sigma", child: *sigma }},\n'
            f'            ScalarSym {{ name: "wild", value: *wild }},\n'
            f"        ]),",
        "reflect.rs (parse arm)":
            f'        "{name}" => TermNode::{name} {{\n'
            f'            template: take_child!("template"),\n'
            f'            sigma: take_child!("sigma"),\n'
            f'            wild: get_sym("wild")?,\n'
            f"        }},",
    }


def emit_structural_recursion(name: str, recur_kind: str) -> dict:
    """Emit every TermNode home for a structural-recursion primitive of `recur_kind`.
    Name-parameterised (helper fn = <name_lower>_recur) so same-kind primitives don't
    collide. Arg-shape per recur_kind:
      • single-collection `Name { values, wild }` — meet_wild / join_fuse / graded_sim
        / witness (witness returns (template, sigmas); others return a Value);
      • two-arg `Name { template, sigma, wild }` — substitute (template + σ → term).
    Keys carry 'helper' for self_extend.plan; an anchor of the same recur_kind has the
    same key set (set(frags)==set(anchors))."""
    if recur_kind not in _BODIES:
        raise ValueError(f"no structural-recursion body for recur_kind {recur_kind!r} "
                         f"(have {sorted(_BODIES)})")
    fn = f"{name.lower()}_recur"
    helper = _BODIES[recur_kind](fn)
    if recur_kind in _TWO_ARG:
        return _emit_two_arg(name, fn, helper)
    return _emit_single_collection(name, recur_kind, fn, helper)
