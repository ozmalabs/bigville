"""arity_homes — the AFFORDANCE the jabberwock asked for: a UNIFORM home-emitter keyed by Term ARITY.

The agent's self-extension was closed (emit_primitive_rust = a fixed menu of 7 semantic kinds). The agent
diagnosed that the home ARMS a leaf touches (enum variant, copy_subtree, evaluator, jsonio name/parse,
reflect, shape) are MECHANICAL and IDENTICAL across primitives of the same arity; only the helper BODY (the
maths) differs. This module is that decoupling: `emit_binary_scalar_leaf(name, fn, body)` emits ALL the home
fragments for a binary {a,b} scalar leaf, parameterised only by name + fn-name + body. The fragments are byte-
identical in shape to an existing binary leaf (MahalFull), so self_extend anchors on MahalFull's verbatim arms
and inserts the new one after each. Build this once -> the closed menu is an OPEN faculty: the agent authors
ANY binary leaf it specifies (body composed from held primitives, or authored by its self-teacher and
compile-checked by self_extend). This is a world-adapter (mechanical string templating); no decisions.
"""
from __future__ import annotations

# the existing binary leaf whose verbatim arms are the insertion anchors.
ANCHOR_NAME = "MahalFull"
ANCHOR_FN = "mahal_full"


def emit_binary_scalar_leaf(name: str, fn: str, body: str = "") -> dict:
    """Emit every home fragment for a binary {a,b} -> Float leaf. Keys carry 'group'/'helper' so self_extend
    routes them (group = add to a `|` chain; helper = append fn at EOF; else = insert arm after the anchor)."""
    return {
        "term.rs (enum variant)":
            f"    {name} {{ a: TermIdx, b: TermIdx }},",
        "term.rs (copy_subtree arm)":
            f"        TermNode::{name} {{ a, b }} => TermNode::{name} {{ a: copy_subtree(src, dst, a), b: copy_subtree(src, dst, b) }},",
        "term.rs (evaluator arm)":
            f"        TermNode::{name} {{ a, b }} => {{\n"
            f"            let av = evaluate(arena, *a, env, ctx);\n"
            f"            let bv = evaluate(arena, *b, env, ctx);\n"
            f"            Value::Float({fn}(&av, &bv))\n"
            f"        }}",
        "term.rs (children group)":
            f"        | TermNode::{name} {{ a, b }}",
        "term.rs (helper)":
            body,
        "jsonio.rs (name arm)":
            f'        TermNode::{name} {{ .. }} => "{name}",',
        "jsonio.rs (children group)":
            f"        | TermNode::{name} {{ a, b }}",
        "jsonio.rs (parse arm)":
            f'        "{name}" => TermNode::{name} {{\n'
            f'            a: child_of("a", obj, arena, interner, variant)?,\n'
            f'            b: child_of("b", obj, arena, interner, variant)?,\n'
            f"        }},",
        "reflect.rs (children arm)":
            f'        TermNode::{name} {{ a, b }} => ("{name}", vec![Child {{ name: "a", child: *a }}, Child {{ name: "b", child: *b }}]),',
        "reflect.rs (parse arm)":
            f'        "{name}" => TermNode::{name} {{ a: take_child!("a"), b: take_child!("b") }},',
        "shape.rs (kind group)":                       # mid-line in a long `|` list (no leading indent)
            f" | {name} {{ .. }}",
        "shape.rs (children group)":
            f"        | {name} {{ a, b }}",
    }


def anchor_spec_fragments() -> dict:
    """the anchor = the existing MahalFull leaf's fragments (must be verbatim in source for insertion)."""
    return emit_binary_scalar_leaf(ANCHOR_NAME, ANCHOR_FN, body="")
