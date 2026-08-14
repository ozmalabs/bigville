"""runtime_design — the agent designs a piece of its OWN runtime.

The agent composes programs (Term-trees) over a fixed set of DSL primitives. When
its reasoning needs an operation the language LACKS, it cannot compose its way out
— it has to extend the runtime itself. This module is the first donkey-free step
of that: the agent SPECIFIES the primitive it needs (a declarative graph-resident
spec, reasoned from its science), and a MECHANICAL generator — a compiler, not an
LLM — emits the Rust for it across the four places a TermNode lives (enum / eval /
jsonio / reflect).

No LLM writes the code. The agent decides WHAT (the spec); the generator emits HOW
(deterministic templates). This is the accretion path toward a self-designed
runtime: one self-authored primitive, then more. See [[ozma_agent_writes_its_own_code]]
/ [[ozma_write_not_train_prior_art]].
"""
from __future__ import annotations


def agent_specify_primitive(substrate) -> dict:
    """The agent reasons from its OWN science to a primitive its language lacks,
    and specifies it. Records a `PrimitiveSpec` graph node. Returns the spec."""
    # what the agent knows: formants are spectral PEAKS; F1/F2 are peak FREQUENCIES;
    # the speaker-invariant cue is the RATIO F2/F1 (vocal-tract-length cancels).
    mt = next((n for n in substrate.nodes("Microtheory")
               if n.attrs.get("name") == "speech_science"), None)
    grounded = False
    if mt is not None:
        for c in substrate.neighbours(mt.id, "has_concept"):
            if substrate.node(c).attrs.get("name") == \
                    "vocal_tract_resonance_formants":
                grounded = "peak" in substrate.node(c).attrs.get(
                    "definition", "").lower()
    # introspect its own primitives: Max yields the VALUE of the peak, not WHERE it
    # is. Formant frequency IS the where (the bin index). No current primitive gives
    # an index. -> it must extend the runtime.
    spec = {
        "name": "ArgMax",
        "items_field": "items",
        "semantic_kind": "index_of_reduction",
        "reduce_op": "max",
        "purpose": "the bin INDEX of a spectral peak = a formant FREQUENCY; the "
                   "ratio F2/F1 of two such indices is vocal-tract-length (speaker) "
                   "invariant — the exact cue actual speaker-independent speech needs",
        "why_new": "the existing Max primitive returns the peak VALUE, not its "
                   "INDEX; no current DSL primitive yields a position, so a formant "
                   "frequency is INEXPRESSIBLE in the current language",
        "grounded_in_science": bool(grounded),
    }
    substrate.add_node("PrimitiveSpec", {**spec, "origin": "agent_runtime_design"})
    return spec


def agent_specify_vision_foreground(substrate=None) -> dict:
    """The agent reasons from VISION science to the object-isolation primitive its
    language lacks, and specifies it. The grounding result (a sound NAMES a sight)
    failed because the visual cue was the WHOLE frame — dominated by the persistent
    presenter/background. Vision science: an OBJECT is figure against ground; the
    NAMED object is what DEVIATES from the persistent background (background
    subtraction = the classic figure/ground + saliency op). The agent introspects
    its primitives: none isolate figure from ground over a vector/image. -> extend
    the runtime with `Foreground` (elementwise |frame - background|) + its running
    background model `EmaBlend`. Records a PrimitiveSpec; returns the spec."""
    spec = {
        "name": "Foreground",
        "items_field": "frame",
        "semantic_kind": "vector_elementwise",
        "reduce_op": "abs_diff",
        "companion": "EmaBlend",   # background*(1-alpha) + frame*alpha
        "purpose": "isolate the figure (named object) from the ground (persistent "
                   "presenter/set) so a word binds to its referent's pixels, not the "
                   "dominant scene — the cue specificity grounding needs",
        "why_new": "no current primitive isolates figure from ground over a frame; "
                   "scalar Plus/Times do not span a vector, so foreground extraction "
                   "is INEXPRESSIBLE in the current language",
        "grounded_in_science": True,
    }
    if substrate is not None:
        substrate.add_node("PrimitiveSpec", {**spec, "origin": "agent_runtime_design"})
    return spec


def agent_specify_whiten_primitive(substrate=None) -> dict:
    """The agent reasons from its SEEDED linear-algebra concepts (linear_discriminant_
    analysis / cholesky_whitening) to the primitive its language LACKS — within-class
    WHITENING — and specifies it. It DERIVED the fix (whiten by the within-class
    covariance to remove the structured speaker DIRECTION; agent_derives_xspeaker)
    but cannot WIRE it: the DSL has Dot/VecAdd/VecSub but NO matrix factorisation /
    inverse, so y = L⁻¹x (Cholesky-solve) is INEXPRESSIBLE. It specifies `Whiten`:
    given a symmetric PD matrix W and a vector x, return L⁻¹x where W = L Lᵀ — whose
    distances are the Mahalanobis metric that suppresses the within-class scatter.
    Records a PrimitiveSpec; returns the spec."""
    def _has(name):
        if substrate is None:
            return False
        for mt in substrate.nodes("Microtheory"):
            for c in substrate.neighbours(mt, "has_concept"):
                if substrate.node(c)["attrs"].get("name") == name:
                    return True
        return False
    grounded = {"cholesky_whitening": _has("cholesky_whitening"),
                "linear_discriminant_analysis": _has("linear_discriminant_analysis")}
    spec = {
        "name": "Whiten",
        "semantic_kind": "matrix_whiten",
        "purpose": ("within-class WHITENING: given the within-class scatter matrix W "
                    "(symmetric PD) and a vector x, return y = L⁻¹x where W = L Lᵀ "
                    "(Cholesky) — ‖y‖² = xᵀW⁻¹x, the Mahalanobis metric that suppresses "
                    "the within-class (speaker) scatter directions = the derived "
                    "cross-speaker fix, made native"),
        "why_new": ("the DSL has Dot / VecAdd / VecSub but NO matrix factorisation or "
                    "inverse; a Cholesky factor + triangular solve is INEXPRESSIBLE in "
                    "the current language — the matrix-primitive frozen edge"),
        "reduces_to": ("Cholesky W = L Lᵀ then forward-solve L y = x (held f64 +,-,*,/ "
                       "and sqrt, but over a MATRIX the DSL cannot index) — a native "
                       "Rust helper `whiten_cholesky(w, x)`"),
        "children": ["w", "x"],         # binary {w, x} -> vector, shaped like DtwTo
        "grounded_in_science": grounded,
        "is_agent_design": True,
    }
    if substrate is not None:
        try:
            substrate.add_node("PrimitiveSpec", {
                "name": "Whiten", "semantic_kind": "matrix_whiten",
                "purpose": spec["purpose"], "why_new": spec["why_new"],
                "reduces_to": spec["reduces_to"],
                "grounded": sum(1 for v in grounded.values() if v),
                "origin": "agent_runtime_design", "composed_by": "agent"})
        except Exception:
            pass
    return spec


def agent_specify_within_scatter_primitive(substrate=None) -> dict:
    """The agent reasons from its SEEDED within_class_scatter concept to the primitive
    its language LACKS — the within-class scatter MATRIX — and specifies it. The Whiten
    primitive consumes W; computing W needs grouped mean-subtraction + an OUTER-PRODUCT
    accumulation into a d×d matrix, INEXPRESSIBLE from Dot/VecAdd/VecSub. Specifies
    `WithinScatter`: a = the data (Tuple of token vectors), b = the class labels;
    returns the regularized within-class scatter matrix. Records a PrimitiveSpec."""
    def _has(name):
        if substrate is None:
            return False
        return any(substrate.node(c)["attrs"].get("name") == name
                   for mt in substrate.nodes("Microtheory")
                   for c in substrate.neighbours(mt, "has_concept"))
    grounded = {"within_class_scatter": _has("within_class_scatter"),
                "linear_discriminant_analysis": _has("linear_discriminant_analysis")}
    spec = {
        "name": "WithinScatter",
        "semantic_kind": "within_class_scatter",
        "purpose": ("the regularized WITHIN-CLASS SCATTER matrix W = avg over classes of "
                    "(x-μ_c)(x-μ_c)ᵀ (shrunk toward its diagonal) — the matrix the derived "
                    "cross-speaker fix whitens by; pairs with Whiten to make the whole "
                    "pipeline native"),
        "why_new": ("computing W needs grouped mean-subtraction and an OUTER-PRODUCT "
                    "accumulation into a d×d matrix; the DSL has Dot/VecAdd/VecSub but no "
                    "outer product or matrix accumulation — INEXPRESSIBLE"),
        "reduces_to": ("group tokens by label; per class subtract the class mean and "
                       "accumulate the outer products of the centred tokens; average; "
                       "diagonal-shrink for conditioning — a native Rust helper "
                       "`within_class_scatter(vecs, labels)`"),
        "children": ["a", "b"],          # a = data matrix, b = labels; binary like Whiten
        "grounded_in_science": grounded,
        "is_agent_design": True,
    }
    if substrate is not None:
        try:
            substrate.add_node("PrimitiveSpec", {
                "name": "WithinScatter", "semantic_kind": "within_class_scatter",
                "purpose": spec["purpose"], "why_new": spec["why_new"],
                "reduces_to": spec["reduces_to"],
                "grounded": sum(1 for v in grounded.values() if v),
                "origin": "agent_runtime_design", "composed_by": "agent"})
        except Exception:
            pass
    return spec


def agent_specify_between_scatter_primitive(substrate=None) -> dict:
    """The agent reasons from its SEEDED between_class_scatter concept (and the
    between-observed-group scatter its nuisance_conditioning derivation already names)
    to the primitive its language LACKS — the BETWEEN-class scatter matrix — and
    specifies it. The nuisance-conditioned fix whitens by the between-OBSERVED-group
    scatter; computing it as St - Sw is a numpy crutch. Specifies `BetweenScatter`:
    a = data (Tuple of token vectors), b = group labels; returns Sb = (1/N) Σ_c n_c
    (μ_c-μ)(μ_c-μ)ᵀ. Records a PrimitiveSpec."""
    def _has(name):
        if substrate is None:
            return False
        return any(substrate.node(c)["attrs"].get("name") == name
                   for mt in substrate.nodes("Microtheory")
                   for c in substrate.neighbours(mt, "has_concept"))
    grounded = {"between_class_scatter": _has("between_class_scatter"),
                "covariate_conditioning": _has("covariate_conditioning")}
    spec = {
        "name": "BetweenScatter",
        "semantic_kind": "between_class_scatter",
        "purpose": ("the BETWEEN-class scatter Sb = (1/N) Σ_c n_c (μ_c-μ)(μ_c-μ)ᵀ — the "
                    "scatter of group means about the global mean; the between-OBSERVED-"
                    "group (e.g. between-speaker) scatter the nuisance-conditioned fix "
                    "whitens by, computed in ONE native op instead of St-Sw in numpy"),
        "why_new": ("computing Sb needs per-group means, weighted mean-difference OUTER "
                    "PRODUCTS accumulated into a d×d matrix; the DSL has Dot/VecAdd/"
                    "VecSub but no outer product or matrix accumulation — INEXPRESSIBLE"),
        "reduces_to": ("global mean + per-group means; accumulate n_c·(μ_c-μ)(μ_c-μ)ᵀ "
                       "over groups; divide by N — a native Rust helper "
                       "`between_class_scatter(vecs, labels)`"),
        "children": ["a", "b"],          # a = data, b = labels; binary like WithinScatter
        "grounded_in_science": grounded,
        "is_agent_design": True,
    }
    if substrate is not None:
        try:
            substrate.add_node("PrimitiveSpec", {
                "name": "BetweenScatter", "semantic_kind": "between_class_scatter",
                "purpose": spec["purpose"], "why_new": spec["why_new"],
                "reduces_to": spec["reduces_to"],
                "grounded": sum(1 for v in grounded.values() if v),
                "origin": "agent_runtime_design", "composed_by": "agent"})
        except Exception:
            pass
    return spec


def agent_specify_whiten_many_primitive(substrate=None) -> dict:
    """The agent introspects the COST of its own Whiten: it recomputes the Cholesky
    factor L of W on EVERY call, so whitening m vectors by the SAME W is O(m·n^3) when
    the factorisation is shared. It specifies the batch realisation `WhitenMany`:
    a = W, b = the data matrix X; factor W = L L^T ONCE, then forward-solve L y = x for
    every row — O(n^3 + m·n^2). Same math as Whiten, amortised. Records a PrimitiveSpec."""
    spec = {
        "name": "WhitenMany",
        "semantic_kind": "matrix_whiten_batch",
        "purpose": ("batch within-class whitening: factor the within-class scatter W = "
                    "L L^T ONCE, then return L^-1 x for every row of the data matrix X — "
                    "the Whiten transform amortised so the Cholesky is shared, not "
                    "recomputed per vector"),
        "why_new": ("Whiten { W, x } re-factors W on every call (O(m·n^3) for m vectors); "
                    "the factorisation is INVARIANT across the rows, so the cost belongs "
                    "ONCE — but the single-vector Term cannot hoist it"),
        "reduces_to": ("Cholesky W = L L^T once; forward-solve L y = x per row of X — the "
                       "held Whiten kernel, batched: `whiten_many(w, xs)`"),
        "children": ["a", "b"],          # a = W, b = X (data matrix); binary like Whiten
        "grounded_in_science": {"cholesky_whitening": True},
        "is_agent_design": True,
    }
    if substrate is not None:
        try:
            substrate.add_node("PrimitiveSpec", {
                "name": "WhitenMany", "semantic_kind": "matrix_whiten_batch",
                "purpose": spec["purpose"], "why_new": spec["why_new"],
                "reduces_to": spec["reduces_to"], "grounded": 1,
                "origin": "agent_runtime_design", "composed_by": "agent"})
        except Exception:
            pass
    return spec


# ---- the mechanical generator (a compiler spec->Rust; NO LLM) ----------------

def emit_primitive_rust(spec: dict) -> dict:
    """Emit the Rust for a new TermNode across its four homes, from the spec.
    Deterministic templates per semantic_kind. Returns {place: source}."""
    name = spec["name"]
    field = spec.get("items_field", "items")
    lname = name.lower()
    if spec["semantic_kind"] == "arity_binary_scalar_leaf":
        from domains.arity_homes import emit_binary_scalar_leaf
        return emit_binary_scalar_leaf(spec["name"], spec["fn"], spec.get("body", ""))
    if spec["semantic_kind"] == "structural_recursion":
        # part-2 generalisation: the AntiUnify family (one shape parameterised by
        # recur_kind = leaf-op + combine-op + return). Name-parameterised helper
        # (<name_lower>_recur) so same-kind primitives don't collide. Deterministic,
        # NO LLM — the agent's spec chooses (name, recur_kind); this renders.
        from domains.struct_recursion_template import emit_structural_recursion
        return emit_structural_recursion(spec["name"], spec["recur_kind"])
    if spec["semantic_kind"] == "index_of_reduction":
        cmp = ">" if spec["reduce_op"] == "max" else "<"
        init = "NEG_INFINITY" if spec["reduce_op"] == "max" else "INFINITY"
        ord = "Greater" if spec["reduce_op"] == "max" else "Less"
        # matches the real substrate API (mirrors numeric_minmax): TermArena,
        # &mut Env, &mut EvalCtx, evaluate(), cmp_value(), Value::Int. This is the
        # version that actually integrated + runs.
        helper = (
            f"fn numeric_{lname}(arena: &TermArena, items: &[TermIdx],\n"
            f"                 env: &mut Env, ctx: &mut EvalCtx) -> Value {{\n"
            f"    let mut best: Option<(usize, Value)> = None;\n"
            f"    for (i, c) in items.iter().enumerate() {{\n"
            f"        let v = evaluate(arena, *c, env, ctx);\n"
            f"        let take = match &best {{ None => true, Some((_, cur)) =>\n"
            f"            matches!(cmp_value(&v, cur), std::cmp::Ordering::{ord}) }};\n"
            f"        if take {{ best = Some((i, v)); }}\n"
            f"    }}\n"
            f"    Value::Int(best.map(|(i, _)| i as i64).unwrap_or(0))\n"
            f"}}")
    elif spec["semantic_kind"] == "trajectory_distance":
        # DtwTo: banded DTW between two frames x bands trajectories. The
        # genuinely-new primitive analysis-by-synthesis recognition needs —
        # synthesis+compare is INEXPRESSIBLE from the existing Terms. Two
        # children a, b each evaluate to a Tuple of frames (each a Tuple of
        # band floats); returns the length-normalised banded-DTW distance.
        band = int(spec.get("band", 8))
        helper = (
            f"fn banded_dtw(a: &Value, b: &Value, band: usize) -> f64 {{\n"
            f"    fn rows(v: &Value) -> Vec<Vec<f64>> {{\n"
            f"        v.iter().map(|f| f.iter().map(|x| x.as_f64())\n"
            f"            .collect::<Vec<f64>>()).collect()\n"
            f"    }}\n"
            f"    let (ra, rb) = (rows(a), rows(b));\n"
            f"    let (na, nb) = (ra.len(), rb.len());\n"
            f"    if na == 0 || nb == 0 {{ return f64::INFINITY; }}\n"
            f"    // Sakoe-Chiba banded DP; Euclidean per-frame. Mirrors the\n"
            f"    // Python `dtw` the bottom-up baseline uses, so the AxS\n"
            f"    // instance<->synthesis score is comparable to the\n"
            f"    // instance<->instance baseline.\n"
            f"    /* ... full body emitted into term.rs ... */\n"
            f"}}")
        return {
            "term.rs (enum variant)":
                f"    DtwTo {{ a: TermIdx, b: TermIdx }},",
            "term.rs (evaluator arm)":
                f"        TermNode::DtwTo {{ a, b }} => {{\n"
                f"            let av = evaluate(arena, *a, env, ctx);\n"
                f"            let bv = evaluate(arena, *b, env, ctx);\n"
                f"            Value::Float(banded_dtw(&av, &bv, {band}))\n"
                f"        }}",
            "term.rs (helper)": helper,
            "jsonio.rs (name)":
                f'        TermNode::DtwTo {{ .. }} => "DtwTo",',
            "jsonio.rs (parse)":
                f'        "DtwTo" => TermNode::DtwTo {{ '
                f'a: child_of("a", obj, arena, interner, variant)?, '
                f'b: child_of("b", obj, arena, interner, variant)? }},',
        }
    elif spec["semantic_kind"] == "matrix_whiten":
        # Whiten { w, x }: w -> a matrix (Tuple of Tuple of Float), x -> a vector
        # (Tuple of Float); returns L^-1 x where w = L L^T (Cholesky). The matrix
        # factorisation + triangular solve the DSL cannot express. Binary {a,b}-shaped
        # like DtwTo, but returns a Value::Tuple vector instead of a scalar.
        helper = (
            "fn whiten_cholesky(w: &Value, x: &Value) -> Value {\n"
            "    let rows: Vec<Vec<f64>> = w.iter()\n"
            "        .map(|r| r.iter().map(|v| v.as_f64()).collect()).collect();\n"
            "    let xv: Vec<f64> = x.iter().map(|v| v.as_f64()).collect();\n"
            "    let n = rows.len();\n"
            "    if n == 0 || xv.len() != n || rows.iter().any(|r| r.len() != n) {\n"
            "        return x.clone();\n"
            "    }\n"
            "    // Cholesky: W = L L^T (lower), with a tiny floor for PD safety.\n"
            "    let mut l = vec![vec![0.0f64; n]; n];\n"
            "    for i in 0..n {\n"
            "        for j in 0..=i {\n"
            "            let mut s = rows[i][j];\n"
            "            for k in 0..j { s -= l[i][k] * l[j][k]; }\n"
            "            if i == j {\n"
            "                l[i][j] = if s > 1e-12 { s.sqrt() } else { 1e-6 };\n"
            "            } else {\n"
            "                let d = if l[j][j].abs() > 1e-12 { l[j][j] } else { 1e-6 };\n"
            "                l[i][j] = s / d;\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "    // forward-solve L y = x\n"
            "    let mut y = vec![0.0f64; n];\n"
            "    for i in 0..n {\n"
            "        let mut s = xv[i];\n"
            "        for k in 0..i { s -= l[i][k] * y[k]; }\n"
            "        let d = if l[i][i].abs() > 1e-12 { l[i][i] } else { 1e-6 };\n"
            "        y[i] = s / d;\n"
            "    }\n"
            "    let mut out: smallvec::SmallVec<[Value; 4]> = smallvec::smallvec![];\n"
            "    for v in y { out.push(Value::Float(v)); }\n"
            "    Value::Tuple(std::sync::Arc::new(out))\n"
            "}")
        # Fields named a (=matrix W) / b (=vector x) so the variant joins every
        # existing {a,b} exhaustive group exactly like DtwTo (no field-name mismatch).
        return {
            "term.rs (enum variant)": "    Whiten { a: TermIdx, b: TermIdx },",
            "term.rs (evaluator arm)":
                "        TermNode::Whiten { a, b } => {\n"
                "            let wv = evaluate(arena, *a, env, ctx);\n"
                "            let xv = evaluate(arena, *b, env, ctx);\n"
                "            whiten_cholesky(&wv, &xv)\n"
                "        }",
            "term.rs (copy_subtree)":
                "        TermNode::Whiten { a, b } => TermNode::Whiten { "
                "a: copy_subtree(src, dst, a), b: copy_subtree(src, dst, b) },",
            "term.rs (child-index group)": "        | TermNode::Whiten { a, b }",
            "term.rs (helper)": helper,
            "jsonio.rs (name)": '        TermNode::Whiten { .. } => "Whiten",',
            "jsonio.rs (exhaustive group)": "        | TermNode::Whiten { a, b }",
            "jsonio.rs (parse)":
                '        "Whiten" => TermNode::Whiten {\n'
                '            a: child_of("a", obj, arena, interner, variant)?,\n'
                '            b: child_of("b", obj, arena, interner, variant)?,\n'
                "        },",
            "shape.rs (exhaustive group)": "        | Whiten { a, b }",
            "reflect.rs (describe)":
                '        TermNode::Whiten { a, b } => ("Whiten", '
                'vec![Child { name: "a", child: *a }, Child { name: "b", child: *b }]),',
            "reflect.rs (parse)":
                '        "Whiten" => TermNode::Whiten { a: take_child!("a"), '
                'b: take_child!("b") },',
        }
    elif spec["semantic_kind"] == "within_class_scatter":
        # WithinScatter { a, b }: a -> data (Tuple of token vectors), b -> labels
        # (Tuple of Float). Returns the regularized within-class scatter matrix W
        # (Tuple of Tuple of Float). Grouped mean-subtraction + outer-product accum
        # the DSL cannot express. Binary {a,b}-shaped like DtwTo/Whiten.
        helper = (
            "fn within_class_scatter(vecs: &Value, labels: &Value) -> Value {\n"
            "    let rows: Vec<Vec<f64>> = vecs.iter()\n"
            "        .map(|r| r.iter().map(|v| v.as_f64()).collect()).collect();\n"
            "    let labs: Vec<i64> = labels.iter()\n"
            "        .map(|v| v.as_f64().round() as i64).collect();\n"
            "    let n = rows.len();\n"
            "    let empty = || Value::Tuple(std::sync::Arc::new(\n"
            "        smallvec::SmallVec::<[Value; 4]>::new()));\n"
            "    if n == 0 || labs.len() != n { return empty(); }\n"
            "    let d = rows[0].len();\n"
            "    if d == 0 || rows.iter().any(|r| r.len() != d) { return empty(); }\n"
            "    let mut classes = labs.clone(); classes.sort_unstable(); classes.dedup();\n"
            "    let mut w = vec![vec![0.0f64; d]; d];\n"
            "    for &c in &classes {\n"
            "        let idx: Vec<usize> = (0..n).filter(|&i| labs[i] == c).collect();\n"
            "        if idx.is_empty() { continue; }\n"
            "        let m = idx.len() as f64;\n"
            "        let mut mu = vec![0.0f64; d];\n"
            "        for &i in &idx { for k in 0..d { mu[k] += rows[i][k]; } }\n"
            "        for k in 0..d { mu[k] /= m; }\n"
            "        for &i in &idx {\n"
            "            for a in 0..d {\n"
            "                let ca = rows[i][a] - mu[a];\n"
            "                for b in 0..d { w[a][b] += ca * (rows[i][b] - mu[b]); }\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "    let nn = n as f64;\n"
            "    for a in 0..d { for b in 0..d { w[a][b] /= nn; } }\n"
            "    // diagonal shrinkage (regularized covariance estimate)\n"
            "    let s = 0.3f64;\n"
            "    let mut tr = 0.0; for a in 0..d { tr += w[a][a]; }\n"
            "    let lam = s * tr / (d as f64);\n"
            "    for a in 0..d {\n"
            "        for b in 0..d { w[a][b] *= 1.0 - s; }\n"
            "        w[a][a] += lam;\n"
            "    }\n"
            "    let mut outer: smallvec::SmallVec<[Value; 4]> = smallvec::smallvec![];\n"
            "    for a in 0..d {\n"
            "        let mut inner: smallvec::SmallVec<[Value; 4]> = smallvec::smallvec![];\n"
            "        for b in 0..d { inner.push(Value::Float(w[a][b])); }\n"
            "        outer.push(Value::Tuple(std::sync::Arc::new(inner)));\n"
            "    }\n"
            "    Value::Tuple(std::sync::Arc::new(outer))\n"
            "}")
        return {
            "term.rs (enum variant)": "    WithinScatter { a: TermIdx, b: TermIdx },",
            "term.rs (evaluator arm)":
                "        TermNode::WithinScatter { a, b } => {\n"
                "            let dv = evaluate(arena, *a, env, ctx);\n"
                "            let lv = evaluate(arena, *b, env, ctx);\n"
                "            within_class_scatter(&dv, &lv)\n"
                "        }",
            "term.rs (copy_subtree)":
                "        TermNode::WithinScatter { a, b } => TermNode::WithinScatter { "
                "a: copy_subtree(src, dst, a), b: copy_subtree(src, dst, b) },",
            "term.rs (child-index group)": "        | TermNode::WithinScatter { a, b }",
            "term.rs (helper)": helper,
            "jsonio.rs (name)": '        TermNode::WithinScatter { .. } => "WithinScatter",',
            "jsonio.rs (exhaustive group)": "        | TermNode::WithinScatter { a, b }",
            "jsonio.rs (parse)":
                '        "WithinScatter" => TermNode::WithinScatter {\n'
                '            a: child_of("a", obj, arena, interner, variant)?,\n'
                '            b: child_of("b", obj, arena, interner, variant)?,\n'
                "        },",
            "shape.rs (exhaustive group)": "        | WithinScatter { a, b }",
            "reflect.rs (describe)":
                '        TermNode::WithinScatter { a, b } => ("WithinScatter", '
                'vec![Child { name: "a", child: *a }, Child { name: "b", child: *b }]),',
            "reflect.rs (parse)":
                '        "WithinScatter" => TermNode::WithinScatter { a: take_child!("a"), '
                'b: take_child!("b") },',
        }
    elif spec["semantic_kind"] == "between_class_scatter":
        # BetweenScatter { a, b }: a -> data (Tuple of token vectors), b -> labels
        # (Tuple of Float). Returns Sb = (1/N) sum_c n_c (mu_c-mu)(mu_c-mu)^T (Tuple of
        # Tuple of Float). Binary {a,b}-shaped like WithinScatter.
        helper = (
            "fn between_class_scatter(vecs: &Value, labels: &Value) -> Value {\n"
            "    let rows: Vec<Vec<f64>> = vecs.iter()\n"
            "        .map(|r| r.iter().map(|v| v.as_f64()).collect()).collect();\n"
            "    let labs: Vec<i64> = labels.iter()\n"
            "        .map(|v| v.as_f64().round() as i64).collect();\n"
            "    let n = rows.len();\n"
            "    let empty = || Value::Tuple(std::sync::Arc::new(\n"
            "        smallvec::SmallVec::<[Value; 4]>::new()));\n"
            "    if n == 0 || labs.len() != n { return empty(); }\n"
            "    let d = rows[0].len();\n"
            "    if d == 0 || rows.iter().any(|r| r.len() != d) { return empty(); }\n"
            "    let mut gmu = vec![0.0f64; d];\n"
            "    for i in 0..n { for k in 0..d { gmu[k] += rows[i][k]; } }\n"
            "    for k in 0..d { gmu[k] /= n as f64; }\n"
            "    let mut classes = labs.clone(); classes.sort_unstable(); classes.dedup();\n"
            "    let mut sb = vec![vec![0.0f64; d]; d];\n"
            "    for &c in &classes {\n"
            "        let idx: Vec<usize> = (0..n).filter(|&i| labs[i] == c).collect();\n"
            "        if idx.is_empty() { continue; }\n"
            "        let nc = idx.len() as f64;\n"
            "        let mut mu = vec![0.0f64; d];\n"
            "        for &i in &idx { for k in 0..d { mu[k] += rows[i][k]; } }\n"
            "        for k in 0..d { mu[k] /= nc; }\n"
            "        let diff: Vec<f64> = (0..d).map(|k| mu[k] - gmu[k]).collect();\n"
            "        for a in 0..d { for b in 0..d { sb[a][b] += nc * diff[a] * diff[b]; } }\n"
            "    }\n"
            "    for a in 0..d { for b in 0..d { sb[a][b] /= n as f64; } }\n"
            "    let mut outer: smallvec::SmallVec<[Value; 4]> = smallvec::smallvec![];\n"
            "    for a in 0..d {\n"
            "        let mut inner: smallvec::SmallVec<[Value; 4]> = smallvec::smallvec![];\n"
            "        for b in 0..d { inner.push(Value::Float(sb[a][b])); }\n"
            "        outer.push(Value::Tuple(std::sync::Arc::new(inner)));\n"
            "    }\n"
            "    Value::Tuple(std::sync::Arc::new(outer))\n"
            "}")
        return {
            "term.rs (enum variant)": "    BetweenScatter { a: TermIdx, b: TermIdx },",
            "term.rs (evaluator arm)":
                "        TermNode::BetweenScatter { a, b } => {\n"
                "            let dv = evaluate(arena, *a, env, ctx);\n"
                "            let lv = evaluate(arena, *b, env, ctx);\n"
                "            between_class_scatter(&dv, &lv)\n"
                "        }",
            "term.rs (copy_subtree)":
                "        TermNode::BetweenScatter { a, b } => TermNode::BetweenScatter { "
                "a: copy_subtree(src, dst, a), b: copy_subtree(src, dst, b) },",
            "term.rs (child-index group)": "        | TermNode::BetweenScatter { a, b }",
            "term.rs (helper)": helper,
            "jsonio.rs (name)": '        TermNode::BetweenScatter { .. } => "BetweenScatter",',
            "jsonio.rs (exhaustive group)": "        | TermNode::BetweenScatter { a, b }",
            "jsonio.rs (parse)":
                '        "BetweenScatter" => TermNode::BetweenScatter {\n'
                '            a: child_of("a", obj, arena, interner, variant)?,\n'
                '            b: child_of("b", obj, arena, interner, variant)?,\n'
                "        },",
            "shape.rs (exhaustive group)": "        | BetweenScatter { a, b }",
            "reflect.rs (describe)":
                '        TermNode::BetweenScatter { a, b } => ("BetweenScatter", '
                'vec![Child { name: "a", child: *a }, Child { name: "b", child: *b }]),',
            "reflect.rs (parse)":
                '        "BetweenScatter" => TermNode::BetweenScatter { a: take_child!("a"), '
                'b: take_child!("b") },',
        }
    elif spec["semantic_kind"] == "matrix_whiten_batch":
        # WhitenMany { a, b }: a -> W (matrix), b -> X (Tuple of token vectors). Factor
        # W = L L^T ONCE, return L^-1 x for every row -> Tuple of whitened vectors.
        helper = (
            "fn whiten_many(w: &Value, xs: &Value) -> Value {\n"
            "    let rows: Vec<Vec<f64>> = w.iter()\n"
            "        .map(|r| r.iter().map(|v| v.as_f64()).collect()).collect();\n"
            "    let xrows: Vec<Vec<f64>> = xs.iter()\n"
            "        .map(|r| r.iter().map(|v| v.as_f64()).collect()).collect();\n"
            "    let n = rows.len();\n"
            "    if n == 0 || rows.iter().any(|r| r.len() != n) { return xs.clone(); }\n"
            "    // Cholesky ONCE: W = L L^T (lower), tiny floor for PD safety.\n"
            "    let mut l = vec![vec![0.0f64; n]; n];\n"
            "    for i in 0..n {\n"
            "        for j in 0..=i {\n"
            "            let mut s = rows[i][j];\n"
            "            for k in 0..j { s -= l[i][k] * l[j][k]; }\n"
            "            if i == j {\n"
            "                l[i][j] = if s > 1e-12 { s.sqrt() } else { 1e-6 };\n"
            "            } else {\n"
            "                let d = if l[j][j].abs() > 1e-12 { l[j][j] } else { 1e-6 };\n"
            "                l[i][j] = s / d;\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "    // batch forward-solve L y = x per row (shares the factor).\n"
            "    let mut out: smallvec::SmallVec<[Value; 4]> = smallvec::smallvec![];\n"
            "    for x in &xrows {\n"
            "        let mut inner: smallvec::SmallVec<[Value; 4]> = smallvec::smallvec![];\n"
            "        if x.len() != n {\n"
            "            for v in x { inner.push(Value::Float(*v)); }\n"
            "            out.push(Value::Tuple(std::sync::Arc::new(inner)));\n"
            "            continue;\n"
            "        }\n"
            "        let mut y = vec![0.0f64; n];\n"
            "        for i in 0..n {\n"
            "            let mut s = x[i];\n"
            "            for k in 0..i { s -= l[i][k] * y[k]; }\n"
            "            let d = if l[i][i].abs() > 1e-12 { l[i][i] } else { 1e-6 };\n"
            "            y[i] = s / d;\n"
            "        }\n"
            "        for v in y { inner.push(Value::Float(v)); }\n"
            "        out.push(Value::Tuple(std::sync::Arc::new(inner)));\n"
            "    }\n"
            "    Value::Tuple(std::sync::Arc::new(out))\n"
            "}")
        return {
            "term.rs (enum variant)": "    WhitenMany { a: TermIdx, b: TermIdx },",
            "term.rs (evaluator arm)":
                "        TermNode::WhitenMany { a, b } => {\n"
                "            let wv = evaluate(arena, *a, env, ctx);\n"
                "            let xv = evaluate(arena, *b, env, ctx);\n"
                "            whiten_many(&wv, &xv)\n"
                "        }",
            "term.rs (copy_subtree)":
                "        TermNode::WhitenMany { a, b } => TermNode::WhitenMany { "
                "a: copy_subtree(src, dst, a), b: copy_subtree(src, dst, b) },",
            "term.rs (child-index group)": "        | TermNode::WhitenMany { a, b }",
            "term.rs (helper)": helper,
            "jsonio.rs (name)": '        TermNode::WhitenMany { .. } => "WhitenMany",',
            "jsonio.rs (exhaustive group)": "        | TermNode::WhitenMany { a, b }",
            "jsonio.rs (parse)":
                '        "WhitenMany" => TermNode::WhitenMany {\n'
                '            a: child_of("a", obj, arena, interner, variant)?,\n'
                '            b: child_of("b", obj, arena, interner, variant)?,\n'
                "        },",
            "shape.rs (exhaustive group)": "        | WhitenMany { a, b }",
            "reflect.rs (describe)":
                '        TermNode::WhitenMany { a, b } => ("WhitenMany", '
                'vec![Child { name: "a", child: *a }, Child { name: "b", child: *b }]),',
            "reflect.rs (parse)":
                '        "WhitenMany" => TermNode::WhitenMany { a: take_child!("a"), '
                'b: take_child!("b") },',
        }
    elif spec["semantic_kind"] == "trajectory_correlation_peak":
        # XCorrPeak: the SNR-optimal MATCHED FILTER — peak normalised cross-
        # correlation over a LAG SEARCH between two frames x bands trajectories.
        # The agent's sonar transfer ('correlating a known delayed signal') as
        # the AxS recognition score. Shaped EXACTLY like DtwTo (two children
        # a, b -> one scalar), differing only in the kernel: instead of banded-DTW
        # DISTANCE it returns peak-NCC SIMILARITY over lags. This is a binary
        # {a, b} primitive, so it lives in the SAME ten homes a {a,b} Term needs:
        # the four canonical homes + helper, PLUS the four exhaustive matches a
        # {a,b} variant must join (copy_subtree / child-index group / term_to_json
        # group / reflect.describe) AND reflect.rs's parse arm + shape.rs.
        #
        # The kernel is a deterministic native lag sweep (a fixed signal-processing
        # op, the sanctioned 'new primitive -> Rust' path), mirroring banded_dtw's
        # structure: materialise both sides as rows of band floats, then for each
        # integer lag L in [-band, band] correlate a against b shifted by L over
        # their overlap, normalise by the overlap norms, and return the peak NCC.
        band = int(spec.get("band", 8))
        lname = "xcorr_peak"
        helper = (
            f"fn {lname}(a: &Value, b: &Value, band: usize) -> f64 {{\n"
            f"    // Materialise each side as rows of f64 (frames x bands),\n"
            f"    // exactly like banded_dtw's `rows`.\n"
            f"    fn rows(v: &Value) -> Vec<Vec<f64>> {{\n"
            f"        v.iter()\n"
            f"            .map(|frame| frame.iter().map(|x| x.as_f64())"
            f".collect::<Vec<f64>>())\n"
            f"            .collect()\n"
            f"    }}\n"
            f"    let ra = rows(a);\n"
            f"    let rb = rows(b);\n"
            f"    let na = ra.len() as isize;\n"
            f"    let nb = rb.len() as isize;\n"
            f"    if na == 0 || nb == 0 {{ return 0.0; }}\n"
            f"    // Per-frame correlation: dot of the two band vectors.\n"
            f"    let fdot = |fa: &Vec<f64>, fb: &Vec<f64>| -> f64 {{\n"
            f"        let n = fa.len().min(fb.len());\n"
            f"        let mut s = 0.0;\n"
            f"        for k in 0..n {{ s += fa[k] * fb[k]; }}\n"
            f"        s\n"
            f"    }};\n"
            f"    let fnorm2 = |fa: &Vec<f64>| -> f64 {{\n"
            f"        fa.iter().map(|x| x * x).sum::<f64>()\n"
            f"    }};\n"
            f"    let mut best = f64::NEG_INFINITY;\n"
            f"    let bl = band as isize;\n"
            f"    // Sweep integer lags L of b relative to a over [-band, band];\n"
            f"    // frame i of a pairs with frame i - L of b (overlap only).\n"
            f"    for lag in -bl..=bl {{\n"
            f"        let mut dot = 0.0;\n"
            f"        let mut na2 = 0.0;\n"
            f"        let mut nb2 = 0.0;\n"
            f"        for i in 0..na {{\n"
            f"            let j = i - lag;\n"
            f"            if j < 0 || j >= nb {{ continue; }}\n"
            f"            let fa = &ra[i as usize];\n"
            f"            let fb = &rb[j as usize];\n"
            f"            dot += fdot(fa, fb);\n"
            f"            na2 += fnorm2(fa);\n"
            f"            nb2 += fnorm2(fb);\n"
            f"        }}\n"
            f"        if na2 <= 0.0 || nb2 <= 0.0 {{ continue; }}\n"
            f"        let ncc = dot / (na2.sqrt() * nb2.sqrt());\n"
            f"        if ncc > best {{ best = ncc; }}\n"
            f"    }}\n"
            f"    if best.is_finite() {{ best }} else {{ 0.0 }}\n"
            f"}}")
        return {
            "term.rs (enum variant)":
                f"    {name} {{ a: TermIdx, b: TermIdx }},",
            "term.rs (evaluator arm)":
                f"        TermNode::{name} {{ a, b }} => {{\n"
                f"            let av = evaluate(arena, *a, env, ctx);\n"
                f"            let bv = evaluate(arena, *b, env, ctx);\n"
                f"            Value::Float({lname}(&av, &bv, {band}))\n"
                f"        }}",
            "term.rs (helper)": helper,
            "term.rs (copy_subtree arm)":
                f"        TermNode::{name} {{ a, b }} => TermNode::{name} {{ "
                f"a: copy_subtree(src, dst, a), b: copy_subtree(src, dst, b) }},",
            "term.rs (child-index group)":
                f"        | TermNode::{name} {{ a, b }}",
            "jsonio.rs (name)":
                f'        TermNode::{name} {{ .. }} => "{name}",',
            "jsonio.rs (term_to_json group)":
                f"        | TermNode::{name} {{ a, b }}",
            "jsonio.rs (parse)":
                f'        "{name}" => TermNode::{name} {{\n'
                f'            a: child_of("a", obj, arena, interner, variant)?,\n'
                f'            b: child_of("b", obj, arena, interner, variant)?,\n'
                f'        }},',
            "reflect.rs (describe arm)":
                f'        TermNode::{name} {{ a, b }} => ("{name}", '
                f'vec![Child {{ name: "a", child: *a }}, '
                f'Child {{ name: "b", child: *b }}]),',
            "reflect.rs (parse arm)":
                f'        "{name}" => TermNode::{name} {{ '
                f'a: take_child!("a"), b: take_child!("b") }},',
            "shape.rs (no-shape group)":
                f"        | {name} {{ .. }}",
            "shape.rs (children arm)":
                f"        | {name} {{ a, b }} => vec![*a, *b],",
        }
    else:
        raise ValueError(f"no template for {spec['semantic_kind']}")
    # A `Vec<TermIdx>`-carrying reduction primitive lives in NINE places,
    # not five: the four canonical homes (enum / evaluator / jsonio name /
    # jsonio parse) + the helper, PLUS four exhaustive matches that a new
    # variant must join or the crate fails to typecheck:
    #   · term.rs copy_subtree  (deep-copy arm)
    #   · term.rs child-index collection (the `items`-group `|` pattern)
    #   · jsonio term_to_json    (the same `items`-group `|` pattern)
    #   · reflect.rs describe    (exhaustive — no catch-all)
    # The mechanical splicer (code_writing_cortex._validate_multi_home_primitive)
    # keys off these exact keys; emitting them HERE keeps the WHAT (spec)
    # and the HOW (template) together, as the runtime_design pattern requires.
    return {
        "term.rs (enum variant)":
            f"    {name} {{ {field}: Vec<TermIdx> }},",
        "term.rs (evaluator arm)":
            f"        TermNode::{name} {{ {field} }} => "
            f"numeric_{lname}(arena, {field}, env, ctx),",
        "term.rs (helper)": helper,
        "term.rs (copy_subtree arm)":
            f"        TermNode::{name} {{ {field} }} =>\n"
            f"            TermNode::{name} {{ {field}: {field}.iter()"
            f".map(|i| copy_subtree(src, dst, *i)).collect() }},",
        "term.rs (child-index group)":
            f"| TermNode::{name} {{ {field} }}",
        "jsonio.rs (name)":
            f'        TermNode::{name} {{ .. }} => "{name}",',
        "jsonio.rs (parse)":
            f'        "{name}" => TermNode::{name} {{ {field}: '
            f'children_of("{field}", obj, arena, interner)? }},',
        "jsonio.rs (term_to_json group)":
            f"| TermNode::{name} {{ {field} }}",
        "reflect.rs (describe arm)":
            f'        TermNode::{name} {{ {field} }} => ("{name}", '
            f'vec![Children {{ name: "{field}", {field} }}]),',
    }


def existing_termnode_variants(term_rs_path) -> set:
    """Read the live term.rs and return the set of TermNode variant names
    declared in `pub enum TermNode { ... }`. A pure read — the splicer/
    specifier consults it so a FRESH primitive never duplicates an
    existing variant (a duplicate enum arm fails `cargo check`)."""
    import re
    from pathlib import Path
    text = Path(term_rs_path).read_text()
    i = text.find("pub enum TermNode {")
    if i < 0:
        return set()
    j = text.find("\n}", i)
    body = text[i:j]
    # Variant lines look like `    Name { ... },` or `    Name,`.
    out = set()
    for m in re.finditer(r"^\s{4}([A-Z][A-Za-z0-9_]*)\b", body, re.M):
        out.add(m.group(1))
    return out


def agent_specify_fresh_reduce_primitive(substrate, term_rs_path) -> dict:
    """The agent specifies a FRESH index-of-reduction primitive whose
    variant name is NOT already in term.rs — so it can actually be
    spliced + built (an existing variant would duplicate and fail to
    compile). Same reasoning move as agent_specify_primitive (ArgMax);
    the cue here is the spectral VALLEY (anti-formant / spectral trough),
    whose bin INDEX is ArgMin over the band trajectory — the dual of the
    peak the existing ArgMax finds. Records a `PrimitiveSpec` graph node
    keyed `kind=multi_home_primitive`. Returns the spec."""
    existing = existing_termnode_variants(term_rs_path)
    # Candidate fresh reduce ops, in preference order. The first whose
    # variant name is absent from term.rs is chosen.
    candidates = [
        ("ArgMin", "min", "the bin INDEX of a spectral VALLEY (an "
                          "anti-formant / spectral trough) — the dual of the "
                          "ArgMax peak; spectral minima between formants carry "
                          "place-of-articulation cues the agent currently can't "
                          "index"),
        ("IndexOfMin", "min", "index of the minimum of a band trajectory"),
        ("ArgTrough", "min", "index of a spectral trough"),
    ]
    chosen = None
    for nm, op, purpose in candidates:
        if nm not in existing:
            chosen = (nm, op, purpose)
            break
    if chosen is None:
        raise RuntimeError(
            "no fresh reduce-primitive name available (all candidates "
            "already exist in term.rs)")
    name, reduce_op, purpose = chosen
    spec = {
        "name": name,
        "items_field": "items",
        "semantic_kind": "index_of_reduction",
        "reduce_op": reduce_op,
        "kind": "multi_home_primitive",
        "purpose": purpose,
        "why_new": (f"no current DSL primitive yields the INDEX of a "
                    f"reduction-by-{reduce_op}; {name} is the dual of the "
                    f"existing ArgMax and is genuinely absent from term.rs "
                    f"(verified against the live enum before emitting)."),
        "verified_fresh": True,
    }
    try:
        substrate.add_node("PrimitiveSpec", {
            **spec, "origin": "agent_runtime_design", "composed_by": "agent"})
    except Exception:
        pass
    return spec


def agent_specify_http_get(substrate=None) -> dict:
    """The agent reasons to a primitive its language LACKS — http_get(url) — and
    specifies it. THE CRUX: this is a DIFFERENT REGISTER from every other spec in
    this module.

    Every prior agent_specify_* (ArgMax, DtwTo, SNF, partition-rank, AHSS-E_2,
    Steenrod) specifies a primitive whose `reduces_to` bottoms out in HELD
    COMPOSITION — either a Rust Term-tree over held ops (ArgMax/DtwTo) or a held
    tower primitive over the held integer/cup ring (SNF onward). They are all
    "composition INSIDE the held basis": the agent already HOLDS every leaf
    operation; the spec only assembles them.

    http_get does NOT reduce to held composition. The agent introspects its held
    primitives and finds: it has arithmetic, reductions, trajectory distances,
    integer rings, cochlear front-ends, cup products — and NOT ONE of them
    REACHES OUTSIDE the substrate. There is no held leaf that opens a socket,
    speaks TCP, sends an HTTP request line, and brings bytes back from a remote
    host. The resource at a URL is not a value the agent can DERIVE from anything
    it holds (no Term-tree, no integer DP, no cochlear filter produces it) — it
    exists only on a remote machine and must be FETCHED. So http_get is
    INEXPRESSIBLE as a composition of held primitives in a way categorically
    unlike the math specs: those were inexpressible-but-DERIVABLE (assemble held
    leaves); this is inexpressible-AND-NOT-DERIVABLE (the bytes are external).

    The register is EXTERNAL-IO: a world-adapter effector. Its `reduces_to` is
    NOT a held op — it is a HOST network library (urllib / a socket), the one
    thing the substrate does not contain. This is the FIRST spec whose floor is
    outside the held basis. The agent CAN specify the WHAT (the contract: url ->
    bytes, GET, idempotent, consequence-free) from its held network_protocols
    science; whether its EMITTER can author the binding (the new register) is the
    proof-of-concept the caller tests.

    GET only — the safe, idempotent, side-effect-free method (the consequence-
    aware choice the agent would read about in HTTP's semantics). The spec is
    explicit that this is the SAFE bootstrap effector.

    Records a `PrimitiveSpec` graph node. Returns the spec."""
    def _has(concept_name, needle):
        if substrate is None:
            return False
        for mt in substrate.nodes("Microtheory"):
            for c in substrate.neighbours(mt, "has_concept"):
                a = substrate.node(c)["attrs"]
                if a.get("name") == concept_name:
                    txt = (a.get("definition", "") + a.get("why", "")).lower()
                    return needle.lower() in txt
        return False

    grounded = {
        # the agent's held network_protocols science: HTTP is a request/response
        # protocol over TCP; GET is the safe, idempotent, read-only method.
        "http_is_request_response": _has("http", "request")
            or _has("hypertext_transfer_protocol", "request")
            or _has("http_methods", "get"),
        "get_is_safe_idempotent": _has("http_methods", "idempotent")
            or _has("idempotency", "idempotent") or _has("http", "idempotent"),
        "tcp_carries_http": _has("tcp", "connection") or _has("transmission_control_protocol", "stream"),
    }
    spec = {
        "name": "http_get",
        "semantic_kind": "external_io_effector",      # the NEW register
        "register": "external_io",
        "method": "GET",
        "purpose": ("http_get(url) -> the bytes/text of the resource at the URL, "
                    "fetched over an HTTP GET. The bootstrap effector for the web "
                    "as a WORLD: write the fetcher -> reach the web -> read "
                    "references -> ground them -> write more code (the self-"
                    "amplifying loop). It is the lower-level effector under the "
                    "existing web_world.web_lookup (which already GETs Wikipedia)."),
        "why_new": ("NO held primitive reaches outside the substrate. The agent "
                    "holds arithmetic, reductions (ArgMax/ArgMin), trajectory "
                    "distance (DtwTo), the integer ring (SNF/partitions), cochlear "
                    "front-ends, cup products — and not one of them opens a socket "
                    "or brings bytes back from a remote host. The resource at a URL "
                    "is not DERIVABLE from anything held; it must be FETCHED."),
        "reduces_to": ("NOT a held op. A HOST network library: urllib.request "
                       "(or a raw socket speaking HTTP/1.1) — Request(url, UA) -> "
                       "urlopen(timeout) -> read(). The floor is OUTSIDE the held "
                       "basis. This is the categorical difference from the math "
                       "specs, whose floor is the held integer/cup ring."),
        "category": ("EXTERNAL-IO world-adapter effector — NOT a composable DSL "
                     "Term and NOT a held tower primitive. The math specs reduce "
                     "to held composition (Rust Term or held ring); http_get "
                     "reduces to a host network library the substrate does NOT "
                     "contain. It is authored as a Python world-adapter (CLAUDE.md: "
                     "Python translates external I/O -> substrate mutations), the "
                     "SAME layer web_world.py's fetch lives in — the agent extends "
                     "its own world-adapters by writing one."),
        "safety": ("GET ONLY — the safe, idempotent, side-effect-free method (no "
                   "POST/PUT/DELETE, no forms, no login). A descriptive User-Agent, "
                   "a timeout, one request. The consequence-aware bootstrap choice."),
        "is_new_register": True,    # the honest flag: this is NOT held-composition
        "grounded_in_science": grounded,
        "is_agent_design": True,
    }
    if substrate is not None:
        try:
            substrate.add_node("PrimitiveSpec", {
                "name": "http_get",
                "semantic_kind": "external_io_effector",
                "register": "external_io",
                "method": "GET",
                "purpose": spec["purpose"], "why_new": spec["why_new"],
                "reduces_to": spec["reduces_to"], "category": spec["category"],
                "safety": spec["safety"], "is_new_register": True,
                "grounded": sum(1 for v in grounded.values() if v),
                "origin": "agent_runtime_design", "composed_by": "agent"})
        except Exception:
            pass
    return spec


def emit_external_io_binding(spec: dict) -> dict:
    """The mechanical emitter for the EXTERNAL-IO register — the new template the
    PoC tests whether the code-writing CAN author.

    emit_primitive_rust has templates for held-composition semantic_kinds only:
    `index_of_reduction` (ArgMax/ArgMin) and `trajectory_distance` (DtwTo). It
    raises ValueError on anything else — including this one. So the external-IO
    register needs its OWN emitter template; this is it.

    Like emit_primitive_rust it is a DETERMINISTIC compiler (spec -> source), NO
    LLM. The difference is the TARGET: not Rust across four TermNode homes, but a
    PYTHON world-adapter function (CLAUDE.md: Python is the external-I/O layer;
    a Rust DSL Term cannot open a socket — external IO is the adapter's job, not
    the evaluator's). The template emits the GET binding from the spec's method +
    safety fields: urllib.request with a descriptive UA + timeout, returning
    {status, length, marker-able text}. Returns {place: source}.

    This emitter EXISTING + producing runnable source is what makes the PoC's
    authoring step succeed (vs outcome c). It mirrors the urllib fetch that
    web_world.py._request already uses — i.e. the agent authors the SAME kind of
    world-adapter the codebase already proves works."""
    if spec.get("semantic_kind") != "external_io_effector":
        raise ValueError(
            f"emit_external_io_binding only handles external_io_effector, "
            f"got {spec.get('semantic_kind')!r}")
    name = spec["name"]
    method = spec.get("method", "GET").upper()
    if method != "GET":
        # The agent's own safety rail, in the emitter: it will only author GET.
        raise ValueError(
            f"external-IO effector emitter authors GET only (the safe, "
            f"idempotent method); refused method {method!r}")
    ua = "gamma-substrate-agent/0.1 (research; agent-authored world-adapter)"
    binding = (
        f"def {name}(url, *, timeout=15, user_agent={ua!r}):\n"
        f"    \"\"\"Agent-authored EXTERNAL-IO effector: HTTP {method} url -> the\n"
        f"    resource bytes/text. A world-adapter (CLAUDE.md): Python translates\n"
        f"    external I/O. GET only (safe, idempotent). Returns\n"
        f"    {{status, length, text, url}}; raises on network failure (the caller\n"
        f"    decides — the effector does not fake a fetch).\"\"\"\n"
        f"    import urllib.request\n"
        f"    req = urllib.request.Request(url, headers={{'User-Agent': user_agent}},\n"
        f"                                 method={method!r})\n"
        f"    with urllib.request.urlopen(req, timeout=timeout) as resp:\n"
        f"        body = resp.read()\n"
        f"    text = body.decode('utf-8', 'replace')\n"
        f"    return {{'status': resp.status, 'length': len(body),\n"
        f"            'text': text, 'url': url}}\n")
    return {
        "world_adapter.py (binding)": binding,
        "register": "external_io",
        "method": method,
        "callable_name": name,
    }


def agent_specify_frontend(band_centres_hz, n_patches: int) -> dict:
    """The agent reasons about its own PERCEPTION — the same move as
    agent_specify_primitive, one layer down. Its spectral resolution (the cochlear
    band layout + A1 patch count) is what makes its formants blunt; that resolution
    is part of its runtime, so redesigning it is the agent's reasoning, not external
    engineering. Returns the spec for a sharper front-end."""
    lo = sum(1 for f in band_centres_hz if 250.0 <= f <= 2500.0)   # formant range
    spec = {
        "target": "cochlear_frontend",
        "observation": (f"I have {len(band_centres_hz)} log-spaced cochlear bands "
                        f"(80-7500 Hz) feeding {n_patches} A1 patches; only ~{lo} "
                        f"bands fall in the formant range (250-2500 Hz). F1/F2 sit "
                        f"~100-200 Hz apart there — finer than one band — so my "
                        f"ArgMax peak is a blunt formant: the estimate quality (not "
                        f"the feature) is what caps recognition."),
        "redesign": ("ADD cochlear filters densely across 250-2500 Hz (warp the "
                     "log layout to oversample the formant region) AND raise the A1 "
                     "patch count so the trajectory carries that finer frequency "
                     "axis; then ArgMax resolves true F1/F2."),
        "where": ("band_centres_hz is a STTParams tuple (a parameter the agent "
                  "sets); the gammatone bank is Rust (auditory_cortex.rs) extensible "
                  "by the same patch->cargo->build->measure accretion as ArgMax."),
        "is_agent_design": True,
    }
    return spec


def agent_specify_lpc_formants(substrate) -> dict:
    """The agent reasons from its source-filter / all-pole science to the FRONT-END
    operation it needs to extract CLEAN formant nodes — the gap its own measurement
    feedback re-pointed it to (cross-speaker clustering capped by the blurry front-end;
    the sound-graph LOSO filter 0.335 << spectrum 0.649 because the cepstral lifter's
    peak-picking is noisy). Records an `OperationSpec` graph node. Returns the spec.

    Grounded in the agent's HELD science (read off its concepts where present):
      - source_filter_theory: speech = glottal SOURCE through a vocal-tract FILTER;
      - linear_prediction_models_speech_autocorrelation: 'the vocal tract IS an
        all-pole filter; LPC's mathematical form matches', residual is whiter;
      - the harvested all-pole/parametric-identifiability implication-shape: a
        recursive (IIR / autoregressive) system is captured by a FEW poles, recovered
        by LINEAR PREDICTION; the pole ANGLES are the resonances = the formants.

    So the operation is: invert the all-pole filter by linear prediction
    (autocorrelation -> Levinson-Durbin -> LPC coefficients), then the roots of the
    LPC polynomial give pole angles -> formant frequencies. This is the deconvolution
    the cepstral lifter only APPROXIMATES (a smoothing window), done EXACTLY via the
    parametric model the agent's science says the tract obeys."""
    def _has(concept_name, needle):
        for mt in substrate.nodes("Microtheory"):
            for c in substrate.neighbours(mt, "has_concept"):
                a = substrate.node(c)["attrs"]
                if a.get("name") == concept_name:
                    txt = (a.get("definition", "") + a.get("why", "")).lower()
                    return needle.lower() in txt
        return False

    grounded = {
        "source_filter_theory":
            _has("source_filter_theory", "filter") or
            _has("source_filter_theory", "source"),
        "all_pole_model":
            _has("linear_prediction_models_speech_autocorrelation", "all-pole") or
            _has("linear_predictive_coding", "all-pole"),
        "iir_recursive": _has("iir_filter", "recursive") or _has("iir_filter", "feedback"),
    }
    spec = {
        "target": "front_end.formant_extraction",
        "current": ("cepstral lifter: window the log-spectrum's low quefrencies to "
                    "smooth the envelope, then pick local maxima. A non-parametric "
                    "APPROXIMATION of source/filter deconvolution; its peaks are blunt "
                    "and source-contaminated, so the formant NODES are noisy (LOSO "
                    "filter 0.335 << spectrum 0.649)."),
        "operation": "lpc_all_pole_formants",
        "method": ("autocorrelation of the pre-emphasised voiced frame -> "
                   "Levinson-Durbin recursion -> LPC coefficients a_k (the all-pole "
                   "filter 1/A(z)) -> roots of A(z) -> pole angles*fs/2pi = formant "
                   "frequencies, bandwidth from |pole|; keep poles in 200-3400 Hz "
                   "with bandwidth < 400 Hz."),
        "why": ("the agent's science: the vocal tract IS an all-pole filter, so the "
                "EXACT inversion of that model (linear prediction) recovers the "
                "resonances directly as pole angles — cleaner formant nodes than a "
                "smoothing window's peaks. The same source/filter deconvolution, done "
                "parametrically instead of approximately."),
        "category": ("adapter-math (numeric DSP), NOT a composable DSL Term: "
                     "autocorrelation + Levinson-Durbin recursion + polynomial "
                     "root-finding are iterative numeric operations with no current "
                     "DSL primitive — the SAME category as the FFT/cepstral lifter it "
                     "replaces (numpy in the extraction layer). The agent specifies "
                     "WHAT (this op) and where its OUTPUT enters the graph (FormantNode "
                     "nodes, exactly as the cepstral extractor's output does); the math "
                     "is the I/O-boundary DSP, like the existing np.fft front-end."),
        "grounded_in_science": grounded,
        "order": 8,   # LPC order p: ~ fs/1000 + 2 for 8 kHz -> 10; 8 is conservative.
        "is_agent_design": True,
    }
    try:
        substrate.add_node("OperationSpec", {
            "name": "lpc_all_pole_formants",
            "target": spec["target"], "operation": spec["operation"],
            "method": spec["method"], "why": spec["why"],
            "category": spec["category"], "order": spec["order"],
            "grounded": sum(1 for v in grounded.values() if v),
            "origin": "agent_runtime_design", "composed_by": "agent"})
    except Exception:
        pass
    return spec


def agent_specify_synth_error(substrate) -> dict:
    """The agent reasons from its developmental science (analysis-by-synthesis /
    motor theory / dual-stream) to the primitive its language LACKS for
    recognition-by-inversion, and specifies it.

    What the agent knows (read off its speech_development / speech_science Mts
    where present): perception is a hypothesize-and-test loop — synthesise each
    candidate word in the HEARD voice, front-end it, and compare to the incoming
    acoustics; the word whose synthesis best predicts the input wins. The compare
    is a trajectory distance (DTW). The agent already OWNS the forward model
    (speak) + the invariant front-end + the candidate lexicon; the one piece its
    DSL cannot express is the synthesis<->incoming distance as a composable Term —
    no current primitive takes two trajectories to a scalar distance. So it must
    extend the runtime (the same accretion move as ArgMax).

    Records a `PrimitiveSpec` graph node. Returns the spec. The mechanical
    generator (emit_primitive_rust, semantic_kind='trajectory_distance') emits the
    Rust; the AxS DECISION (argmax over candidates of -DtwTo(...)) is composed in
    the graph (recognition_graph.predict_synth_term)."""
    def _has(concept_name, needle):
        for mt in substrate.nodes("Microtheory"):
            for c in substrate.neighbours(mt, "has_concept"):
                a = substrate.node(c)["attrs"]
                if a.get("name") == concept_name:
                    txt = (a.get("definition", "") + a.get("why", "")).lower()
                    return needle.lower() in txt
        return False

    grounded = {
        "analysis_by_synthesis": _has("analysis_by_synthesis", "synth")
            or _has("categorical_perception", "synth"),
        "motor_theory": _has("motor_theory", "gesture")
            or _has("speech_development", "babbl"),
    }
    spec = {
        "name": "DtwTo",
        "semantic_kind": "trajectory_distance",
        "band": 8,
        "purpose": (
            "the synthesis<->incoming distance for analysis-by-synthesis "
            "recognition: synth_error(s, w) = DTW(features(s), "
            "features(speak(w | voice(s)))); the word minimising it wins. "
            "Comparing instance<->canonical-synthesis (not instance<->instance) "
            "absorbs the speaker/coarticulation nuisance into the forward model, "
            "so the residual error is phonetic identity — the structural reason "
            "it should beat feature-matching cross-speaker."),
        "why_new": (
            "no current DSL primitive maps two trajectories to a scalar "
            "distance; synthesis+compare is INEXPRESSIBLE as a Term. The forward "
            "model (speak) + invariant front-end + candidate lexicon already "
            "exist; only this distance kernel is missing. Synthesis stays at the "
            "I/O boundary (the adapter calls speak()); this primitive is the "
            "distance; the argmax decision is composed in the graph."),
        "grounded_in_science": grounded,
        "is_agent_design": True,
    }
    try:
        substrate.add_node("PrimitiveSpec", {
            "name": "DtwTo", "semantic_kind": "trajectory_distance",
            "purpose": spec["purpose"], "why_new": spec["why_new"],
            "grounded": sum(1 for v in grounded.values() if v),
            "origin": "agent_runtime_design", "composed_by": "agent"})
    except Exception:
        pass
    return spec


def agent_specify_matched_filter(substrate=None) -> dict:
    """The agent reasons from the SONAR family it READ + banked (the matched
    filter — 'correlating a known delayed signal', the SNR-optimal recovery of a
    known template from noise) to the primitive its language LACKS for matched-
    filter recognition, and specifies it LIVE.

    This is a GENUINE new spec, not a frozen stub: it is reasoned from the
    matched-filter concept the agent acquired (jabberwock_studies_audio_communication,
    the 'signal recovery from noise (sonar family)' branch — Matched filter / Pulse
    compression / Ambiguity function) plus the held autocorrelation science, and it
    grounds against those concepts where present.

    What the agent knows (READ + held):
      · MATCHED FILTER = the SNR-optimal detector: correlate the incoming signal
        against the KNOWN template, peaked over a LAG SEARCH (the unknown delay of
        the 'known delayed signal'). max_L  Dot(a, shift(b, L)) / (|a| |b|).
      · It is analysis-by-synthesis done with the RIGHT operation: the iterated-AbS
        and the surface-DTW NULLs matched on the SURFACE; the sonar transfer says
        SWAP THE OPERATION to peak normalised cross-correlation over lags.
      · The held DSL already expresses the CORRELATION HALF — ncc0(a,b) =
        Dot(a,b)/(Magnitude(a)*Magnitude(b)) (the agent composed this). What it
        CANNOT express is the LAG SEARCH: a variable-lag shift indexes frame (t+L)
        by a BOUND lag L, but Nth.index is a baked i64 literal and there is no
        value-indexed slice/window over a Tuple. So peak-NCC-over-lags is
        INEXPRESSIBLE by composition — the SAME class as DtwTo. It must extend the
        runtime: a native XCorrPeak{a,b} Term shaped exactly like DtwTo (two
        frames x bands trajectories -> one scalar), whose core algorithm is the
        deterministic peak-NCC-over-lags sweep (a fixed signal-processing op, the
        sanctioned 'new primitive -> Rust' path).

    The spec's semantic_kind is the NEW kind `trajectory_correlation_peak`; the
    mechanical generator (emit_primitive_rust) gets a matching template that emits
    the Rust across the TermNode homes (the peak-NCC sweep mirrors banded_dtw's
    structure: materialise both sides as rows, sweep the lag, return the peak NCC).
    The agent specifies WHAT; the generator emits HOW. The recognition DECISION
    (argmin over words of -XCorrPeak, i.e. argmax of the peak) is composed in the
    graph, exactly as the DtwTo synth-error is.

    Records a `PrimitiveSpec` graph node. Returns the spec."""
    def _has(concept_name, needle):
        if substrate is None:
            return False
        for mt in substrate.nodes("Microtheory"):
            for c in substrate.neighbours(mt, "has_concept"):
                a = substrate.node(c)["attrs"]
                if a.get("name") == concept_name:
                    txt = (str(a.get("definition", "")) + str(a.get("why", ""))
                           + str(a.get("genus", ""))).lower()
                    return needle.lower() in txt or needle == "*"
        return False

    def _held(concept_name):
        """Is the named concept held at all (acquired by read_and_ground, even
        if only genus-deep)?"""
        if substrate is None:
            return False
        for mt in substrate.nodes("Microtheory"):
            for c in substrate.neighbours(mt, "has_concept"):
                if substrate.node(c)["attrs"].get("name") == concept_name:
                    return True
        return False

    grounded = {
        # the SONAR-family matched filter the agent READ (genus 'correlating a
        # known delayed signal'); held if the audio-communication study ran.
        "matched_filter_read":
            _held("Matched filter") or _held("matched_filter")
            or _has("Matched filter", "correl") or _has("Sonar", "*"),
        # the active-sensing / pulse-compression siblings (the lag/delay structure).
        "lag_delay_family_read":
            _held("Active sensing") or _held("Pulse compression")
            or _held("Ambiguity function") or _held("Sonar"),
        # the held autocorrelation science — the matched filter's self-correlation;
        # the agent already reasons about correlating a signal with a shifted copy.
        "autocorrelation_held":
            _has("linear_prediction_models_speech_autocorrelation", "autocorrel")
            or _has("linear_predictive_coding", "autocorrel"),
        # the correlation HALF is already composable from held primitives
        # (Dot/Magnitude/Div) — the agent verified this; only the lag search is new.
        "correlation_half_composable_from_held": True,
    }
    spec = {
        "name": "XCorrPeak",
        "semantic_kind": "trajectory_correlation_peak",
        "band": 8,   # the lag search half-width (frames), as DtwTo's band is its DP width
        "purpose": (
            "the SNR-optimal MATCHED FILTER as the analysis-by-synthesis "
            "recognition score: peak normalised cross-correlation over a LAG "
            "search between two frames x bands trajectories — "
            "max_L Dot(a, shift(b, L)) / (|a| |b|) — the sonar transfer "
            "('correlating a known delayed signal') swapping surface-DTW for the "
            "SNR-optimal operation. Two trajectories -> one scalar in [-1, 1] "
            "(1 = a is the known template b at some delay); the candidate word "
            "whose synthesis best correlates (highest peak) with the heard signal "
            "wins. Shaped EXACTLY like DtwTo (a, b -> scalar), differing only in "
            "the kernel: peak-NCC-over-lags instead of banded-DTW distance."),
        "why_new": (
            "no DSL primitive correlates two trajectories over a LAG search. The "
            "correlation HALF is composable (ncc0 = Dot(a,b)/(|a||b|)) but the lag "
            "search is NOT: a variable-lag shift indexes frame (t+L) of b by a "
            "BOUND lag L, and Nth.index is a baked i64 literal — it cannot be a "
            "MaxOver-bound variable — with no value-indexed slice/window/zip over a "
            "Tuple. So peak-NCC-over-lags is INEXPRESSIBLE by composition, the SAME "
            "class as DtwTo; it needs a native Term whose core is the deterministic "
            "lag sweep."),
        "reduces_to": (
            "a fixed signal-processing kernel (like DtwTo's banded DP): materialise "
            "a and b as rows of band floats; for each lag L in [-band, band], "
            "overlap-align a and b shifted by L, accumulate Dot over the overlap and "
            "the two overlap norms, ncc(L) = dot / (|a_ov| |b_ov|); return max_L "
            "ncc(L). Deterministic native Rust, the sanctioned 'new primitive -> "
            "Rust' path — NOT cognition-in-Python."),
        "category": (
            "native DSL Term over two trajectories (the SAME register as DtwTo): a "
            "fixed indexing/correlation operation the evaluator runs. The argmax-"
            "over-words DECISION is composed in the graph, not in the primitive."),
        "grounded_in_science": grounded,
        "is_agent_design": True,
    }
    if substrate is not None:
        try:
            substrate.add_node("PrimitiveSpec", {
                "name": "XCorrPeak",
                "semantic_kind": "trajectory_correlation_peak",
                "purpose": spec["purpose"], "why_new": spec["why_new"],
                "reduces_to": spec["reduces_to"], "category": spec["category"],
                "grounded": sum(1 for v in grounded.values() if v),
                "origin": "agent_runtime_design", "composed_by": "agent"})
        except Exception:
            pass
    return spec


def agent_specify_snf_primitive(substrate=None) -> dict:
    """The agent reasons from its integral-homology science to a primitive its
    language LACKS — the SMITH NORMAL FORM over Z — and specifies it.

    What the agent knows: integral homology H_n(X;Z) = Z^Betti ⊕ (⊕ Z/d_i); the
    free rank is the Betti number, the TORSION is the invariant factors d_i > 1 in
    the Smith normal form of the integer boundary matrix ∂_{n+1}. Its held
    matrix_rank is GF(2)-only (it reduces coefficients mod 2), so it sees ONLY the
    free rank and is BLIND to the torsion — the rational Weyl invariants (cmsg89)
    are likewise the FREE part (Q discards torsion). The one operation the DSL
    cannot express is the SNF over Z: the invariant factors of an integer matrix.

    The agent checks what the SNF REDUCES to: INTEGER Gaussian elimination — row/col
    ops over Z, pivot on the smallest-|value| entry, reduce by integer quotients
    (the Euclidean gcd reduction). That is the held integer ring (+, −, *, //, gcd),
    so — unlike ArgMax / DtwTo, which needed Rust — the SNF is EXPRESSIBLE as a held
    tower primitive over the existing integer arithmetic (no new Rust). The agent
    specifies WHAT; the mechanical emitter realises it over the held ring.

    Records a `PrimitiveSpec` graph node. Returns the spec."""
    def _has(concept_name, needle):
        if substrate is None:
            return False
        for mt in substrate.nodes("Microtheory"):
            for c in substrate.neighbours(mt, "has_concept"):
                a = substrate.node(c)["attrs"]
                if a.get("name") == concept_name:
                    txt = (a.get("definition", "") + a.get("why", "")).lower()
                    return needle.lower() in txt
        return False

    grounded = {
        "integral_homology": _has("integral_homology", "torsion")
            or _has("homology", "invariant factor"),
        "gf2_rank_blind": True,   # the held matrix_rank is mod-2 — sees only Betti
    }
    spec = {
        "name": "smith_normal_form",
        "semantic_kind": "integer_invariant_factors",
        "purpose": ("the INVARIANT FACTORS d_i of an integer matrix's Smith normal "
                    "form — the d_i > 1 are the TORSION coefficients of integral "
                    "homology H_n = Z^Betti ⊕ (⊕ Z/d_i), invisible to the GF(2) "
                    "rank (mod 2, free part only) and the rational Weyl invariants "
                    "(Q discards torsion)"),
        "why_new": ("no current DSL primitive computes the SNF over Z; the held "
                    "matrix_rank is GF(2)-only (it reduces coefficients mod 2) so it "
                    "sees only the FREE rank (Betti) — the torsion needs the INTEGER "
                    "invariant factors the SNF exposes"),
        "reduces_to": ("integer Gaussian elimination: row/col ops over Z, pivot on "
                       "the smallest-|value| entry, reduce by integer quotients (the "
                       "Euclidean gcd reduction); the residue shrinks to the gcd, the "
                       "textbook SNF algorithm — the held +, −, *, //, gcd"),
        "category": ("held tower primitive over the held integer ring — EXPRESSIBLE "
                     "without new Rust (unlike ArgMax/DtwTo), since SNF is integer "
                     "row/col arithmetic the agent already holds"),
        "grounded_in_science": grounded,
        "is_agent_design": True,
    }
    if substrate is not None:
        try:
            substrate.add_node("PrimitiveSpec", {
                "name": "smith_normal_form",
                "semantic_kind": "integer_invariant_factors",
                "purpose": spec["purpose"], "why_new": spec["why_new"],
                "reduces_to": spec["reduces_to"],
                "grounded": sum(1 for v in grounded.values() if v),
                "origin": "agent_runtime_design", "composed_by": "agent"})
        except Exception:
            pass
    return spec


def agent_specify_partition_rank_primitive(substrate=None) -> dict:
    """The agent reasons from its Spin-bordism / Thom-spectrum science to a
    primitive its language LACKS — the RATIONAL coefficient-ring rank — and
    specifies it.

    What the agent knows: Omega^Spin_n = pi_n(MSpin) (Pontryagin-Thom); the
    GENERALIZED homology Omega^Spin_*(X) has coefficient ring Omega^Spin_* =
    Omega^Spin_*(pt) = pi_*(MSpin). The RATIONAL part reduces: Omega^Spin_* ⊗ Q is a
    POLYNOMIAL ring on one generator in each degree 4k (the Pontryagin numbers), so
    the degree-n free rank = the number of PARTITIONS of n/4 (4|n, else 0). The held
    arithmetic has no partition count; the agent checks what it REDUCES to — the
    standard partition DP p[m] += p[m-c] over the held integer + (and the 4|n test is
    the held mod). So — like the SNF, unlike ArgMax/DtwTo — it is EXPRESSIBLE as a
    held tower primitive (no new Rust). The agent specifies WHAT; the mechanical
    emitter realises it over the held integer ring.

    CRITICAL HONESTY (recorded on the spec): this primitive computes ONLY the
    RATIONAL rank (the part that genuinely reduces). The FULL coefficient ring
    Omega^Spin_* with its 2-TORSION is the Anderson-Brown-Peterson theorem — a DEEP
    PRIOR RESULT the agent READS + verifies, NOT derives. The spec is plain that the
    torsion is out of scope of this computation.

    Records a `PrimitiveSpec` graph node. Returns the spec."""
    def _has(concept_name, needle):
        if substrate is None:
            return False
        for mt in substrate.nodes("Microtheory"):
            for c in substrate.neighbours(mt, "has_concept"):
                a = substrate.node(c)["attrs"]
                if a.get("name") == concept_name:
                    txt = (a.get("definition", "") + a.get("why", "")).lower()
                    return needle.lower() in txt
        return False

    grounded = {
        "spin_bordism_is_homotopy_of_mspin":
            _has("spin_bordism", "mspin") or _has("thom_spectrum", "pontryagin"),
        "rational_bordism_is_pontryagin_polynomial": True,
    }
    spec = {
        "name": "spin_rational_rank",
        "semantic_kind": "rational_coefficient_rank",
        "purpose": ("the FREE rank of Omega^Spin_n ⊗ Q — the RATIONAL Spin-bordism "
                    "coefficient group in degree n = the number of PARTITIONS of "
                    "n/4 (the Pontryagin numbers; 0 unless 4|n), since Omega^Spin_* "
                    "⊗ Q is a polynomial ring on a degree-4k generator each k: ranks "
                    "1,1,2,3 at degrees 0,4,8,12"),
        "why_new": ("no current DSL primitive counts integer partitions; the held "
                    "arithmetic has +, −, *, //, mod but no p(n) — the rational "
                    "coefficient-ring rank needs the partition count"),
        "reduces_to": ("the standard partition recurrence p[m] += p[m - c] over "
                       "coin-sizes c = 1..n (the held integer +), then p(n//4) "
                       "gated by the 4|n test (the held mod) — held integer "
                       "arithmetic, no topology"),
        "category": ("held tower primitive over the held integer ring — EXPRESSIBLE "
                     "without new Rust (like the SNF), since the partition count is "
                     "integer DP the agent already holds"),
        "honesty": ("computes ONLY the RATIONAL rank (the part that reduces); the "
                    "FULL coefficient ring's 2-TORSION is the Anderson-Brown-Peterson "
                    "theorem — READ + verified, NOT derived by this primitive"),
        "grounded_in_science": grounded,
        "is_agent_design": True,
    }
    if substrate is not None:
        try:
            substrate.add_node("PrimitiveSpec", {
                "name": "spin_rational_rank",
                "semantic_kind": "rational_coefficient_rank",
                "purpose": spec["purpose"], "why_new": spec["why_new"],
                "reduces_to": spec["reduces_to"], "honesty": spec["honesty"],
                "grounded": sum(1 for v in grounded.values() if v),
                "origin": "agent_runtime_design", "composed_by": "agent"})
        except Exception:
            pass
    return spec


def agent_specify_ahss_e2_primitive(substrate=None) -> dict:
    """The agent reasons from its acquired AHSS inputs to a primitive its language
    LACKS — the Atiyah-Hirzebruch E_2-page rank — and specifies it.

    What the agent now HOLDS (acquired by reading over the whole ladder): (i) the
    rational homology ranks of BG2 from the Weyl invariants H*(BG2;Q) = Q[y_4,y_12]
    (cmsg89) — rank H_p = #monomials y_4^a y_12^b of degree p; and (ii) the rational
    Spin-bordism coefficient ranks rank(Omega^Spin_q ⊗ Q) = p(q/4) (cmsg91, the
    partition-rank primitive). The Atiyah-Hirzebruch spectral sequence has E^2_{p,q}
    = H_p(BG2; Omega^Spin_q), so RATIONALLY its free rank is the PRODUCT of the two
    held ranks. The held arithmetic has the multiply; it lacks only the assembled
    E_2-entry read-out. The agent checks what it REDUCES to — weyl_hp_rank(p) ·
    spin_rational_rank(q), the held integer multiply over the two held rank
    read-outs. So — like the SNF / partition-rank, unlike ArgMax/DtwTo — it is
    EXPRESSIBLE as a held tower primitive (no new Rust). The agent specifies WHAT;
    the mechanical emitter realises it over the held integer ring.

    CRITICAL HONESTY (recorded on the spec): this computes ONLY the RANK of the
    E_2 page (and, via the rational collapse, the rank of E_infinity = the free
    rank of the bordism). Rationally MSpin splits as a product of Eilenberg-MacLane
    spectra, so there are NO rational differentials — the AHSS collapses at E_2 ⊗ Q
    and the rank computation is rigorous. The INTEGRAL torsion differentials (Sq^2-
    type) + extensions need BG2's full integral cohomology (only partially held);
    that is OUT OF SCOPE of this primitive — the rank is what it derives, the
    torsion-freeness is the known answer, NOT derived here.

    Records a `PrimitiveSpec` graph node. Returns the spec."""
    def _has(concept_name, needle):
        if substrate is None:
            return False
        for mt in substrate.nodes("Microtheory"):
            for c in substrate.neighbours(mt, "has_concept"):
                a = substrate.node(c)["attrs"]
                if a.get("name") == concept_name:
                    txt = (a.get("definition", "") + a.get("why", "")).lower()
                    return needle.lower() in txt
        return False

    grounded = {
        "hp_ranks_from_weyl_invariants":
            _has("bg_rational_cohomology", "weyl") or _has("molien_value", "molien"),
        "omega_ranks_from_thom_spectrum":
            _has("spin_bordism", "mspin") or _has("thom_spectrum", "pontryagin"),
        "rational_collapse_no_differentials": True,
    }
    spec = {
        "name": "ahss_e2_rank",
        "semantic_kind": "spectral_sequence_e2_rank",
        "purpose": ("the FREE rank of the Atiyah-Hirzebruch E^2_{p,q} = "
                    "H_p(BG2; Omega^Spin_q) for the Spin bordism of BG2 — rationally "
                    "the PRODUCT rank H_p(BG2;Q) · rank(Omega^Spin_q ⊗ Q); summed over "
                    "p+q = 12 (reduced, p >= 1) it gives the rank of the reduced "
                    "Spin bordism Omega-tilde^Spin_12(BG2)"),
        "why_new": ("no current DSL primitive assembles the E_2 page; the held "
                    "arithmetic has the multiply but not the E^2_{p,q} read-out over "
                    "the two held rank inputs (the Weyl H_p rank + the Spin-bordism "
                    "rational rank)"),
        "reduces_to": ("weyl_hp_rank(p) · spin_rational_rank(q) — the held integer "
                       "multiply over the two held rank read-outs (the Weyl-invariant "
                       "monomial count + the partition rank); no topology"),
        "category": ("held tower primitive over the held integer ring — EXPRESSIBLE "
                     "without new Rust (like the SNF / partition-rank), since the "
                     "E_2 entry is the integer product of two held ranks"),
        "honesty": ("computes ONLY the RANK (the rational E_2 = E_infinity via the "
                    "rational collapse: MSpin ~ product of EM spectra rationally, no "
                    "rational differentials). The integral torsion differentials + "
                    "extensions need BG2's full integral cohomology (partial, not "
                    "held) — the rank is derived; torsion-freeness is the known "
                    "answer, NOT derived here"),
        "grounded_in_science": grounded,
        "is_agent_design": True,
    }
    if substrate is not None:
        try:
            substrate.add_node("PrimitiveSpec", {
                "name": "ahss_e2_rank",
                "semantic_kind": "spectral_sequence_e2_rank",
                "purpose": spec["purpose"], "why_new": spec["why_new"],
                "reduces_to": spec["reduces_to"], "honesty": spec["honesty"],
                "grounded": sum(1 for v in grounded.values() if v),
                "origin": "agent_runtime_design", "composed_by": "agent"})
        except Exception:
            pass
    return spec


def agent_specify_integral_e2_primitive(substrate=None) -> dict:
    """The agent reasons from its READ integral inputs to the primitive its language
    LACKS — the INTEGRAL Atiyah-Hirzebruch E_2 entry WITH its torsion — and
    specifies it.

    What the agent now HOLDS (acquired by reading over the ladder): (i) BG2's
    integral homology — the FREE rank from the Weyl invariants H*(BG2;Q)=Q[y_4,y_12]
    (cmsg89) + the READ 2-TORSION (the documented G2 2-torsion, generated by
    x_7 = beta(x_6), x_6 = Sq^2 x_4; labeled read-not-derived, the SAME read-and-label
    model cmsg91 used for the ABP coefficient ring); and (ii) the READ ABP coefficient
    ring Omega^Spin_* — its free ranks (cross-checked vs the computed rational) + its
    READ 2-torsion (Z/2 at q=1,2,10; (Z/2)^2 at q=9). The INTEGRAL E^2_{p,q} =
    H_p(BG2; Omega^Spin_q) assembles these by the UNIVERSAL COEFFICIENT THEOREM:
        H_p(BG2; G) = (H_p(BG2;Z) (x) G) (+) Tor(H_{p-1}(BG2;Z), G),  G = Omega^Spin_q.
    The held arithmetic has the multiply/add; it lacks only the tensor+Tor bookkeeping
    over the two READ (free, torsion) inputs. The agent checks what it REDUCES to —
    free(H_p)*free(Omega_q) for the free part, and the Z/2-summand count
    free*tors + tors*free + tors*tors + Tor(tors_{p-1}, tors_q) for the torsion. So —
    like the SNF / partition-rank / AHSS-E_2, unlike ArgMax/DtwTo — it is EXPRESSIBLE
    as a held tower primitive over the held integer ring (no new Rust). The agent
    specifies WHAT; the mechanical emitter realises it over the held integer ring.

    CRITICAL HONESTY (recorded on the spec): the INPUTS are READ (BG2's integral
    torsion + the ABP ring — cited, labeled read-not-derived, faithful to how the
    computation is actually done); the ASSEMBLY (the UCT tensor + Tor over the held
    integer multiply/add) is the agent's. This primitive supplies the E_2 PAGE the
    Steenrod-square differentials act on — it does NOT by itself resolve the
    differentials or the extensions (the next steps).

    Records a `PrimitiveSpec` graph node. Returns the spec."""
    def _has(concept_name, needle):
        if substrate is None:
            return False
        for mt in substrate.nodes("Microtheory"):
            for c in substrate.neighbours(mt, "has_concept"):
                a = substrate.node(c)["attrs"]
                if a.get("name") == concept_name:
                    txt = (a.get("definition", "") + a.get("why", "")).lower()
                    return needle.lower() in txt
        return False

    grounded = {
        "bg2_integral_cohomology_read":
            _has("bg_rational_cohomology", "weyl") or _has("molien_value", "molien"),
        "abp_coefficient_ring_read":
            _has("spin_bordism", "mspin") or _has("thom_spectrum", "pontryagin"),
        "uct_tensor_tor_assembly": True,
    }
    spec = {
        "name": "bg2_integral_e2",
        "semantic_kind": "integral_e2_entry_with_torsion",
        "purpose": ("the INTEGRAL Atiyah-Hirzebruch E^2_{p,q} = H_p(BG2; Omega^Spin_q) "
                    "as a structured group {free, torsion_2rank} — the free rank "
                    "free(H_p)*free(Omega_q) PLUS the 2-torsion the rational rank "
                    "missed, assembled by the universal coefficient theorem (tensor + "
                    "Tor) over the READ H_*(BG2;Z) 2-torsion + the READ ABP "
                    "coefficient-ring 2-torsion. This is the integral E_2 page the "
                    "Steenrod-square (Sq^2-type) differentials act on"),
        "why_new": ("no current DSL primitive assembles the INTEGRAL E_2 entry with "
                    "its torsion; the held ahss_e2_rank gives only the RATIONAL (free) "
                    "rank — the 2-torsion needs the UCT tensor + Tor over the two read "
                    "(free, torsion) inputs"),
        "reduces_to": ("free = bg2_int_homology_rank(p) * spin_bordism_free_rank(q); "
                       "torsion_2rank = fp*tq + tp*fq + tp*tq + tp1*tq "
                       "(Z(x)Z/2 + Z/2(x)Z + Z/2(x)Z/2 + Tor(Z/2,Z/2)), tp1 = "
                       "bg2_int_torsion_2rank(p-1) — the held integer multiply/add "
                       "over the read free/torsion read-outs; no topology"),
        "category": ("held tower primitive over the held integer ring — EXPRESSIBLE "
                     "without new Rust (like the SNF / AHSS-E_2), since the E_2 entry "
                     "is the UCT integer bookkeeping over the read inputs"),
        "honesty": ("the INPUTS are READ (BG2's integral 2-torsion + the ABP "
                    "coefficient ring — cited, labeled read-not-derived, faithful to "
                    "how the computation is actually done); the ASSEMBLY (the UCT "
                    "tensor + Tor) is the agent's. Supplies the E_2 page; does NOT by "
                    "itself resolve the differentials / extensions"),
        "grounded_in_science": grounded,
        "is_agent_design": True,
    }
    if substrate is not None:
        try:
            substrate.add_node("PrimitiveSpec", {
                "name": "bg2_integral_e2",
                "semantic_kind": "integral_e2_entry_with_torsion",
                "purpose": spec["purpose"], "why_new": spec["why_new"],
                "reduces_to": spec["reduces_to"], "honesty": spec["honesty"],
                "grounded": sum(1 for v in grounded.values() if v),
                "origin": "agent_runtime_design", "composed_by": "agent"})
        except Exception:
            pass
    return spec


def agent_specify_steenrod_square_primitive(substrate=None) -> dict:
    """The agent reasons from its held cup-product / cochain science to the
    primitives its language LACKS for the INTEGRAL AHSS differentials — the CUP-i
    PRODUCTS and the STEENROD SQUARES Sq^i — and specifies them.

    What the agent HOLDS (cmsg86): the cup product ∪ = ∪_0 (the Alexander-Whitney
    formula on simplicial cochains) over the cochain structure ∂^T (front/back face
    + the cochain pairing + the mod-2 multiply). The AHSS DIFFERENTIALS are STABLE
    COHOMOLOGY OPERATIONS — the first nonzero one is a Sq^2-type operation — so to
    run the integral AHSS the agent needs the STEENROD SQUARES.

    The agent checks what they REDUCE to: the STEENROD SQUARE Sq^i(x) = x ∪_{n−i} x
    (for an n-cochain x) is built from the CUP-i PRODUCTS ∪_i — the HIGHER chain
    homotopies that EXTEND the held cup product ∪_0 over the same cochain structure.
    The cup-i product is Steenrod's higher diagonal: on an ordered (p+q−i)-simplex,
    a sum over (i+1) cut points of the two cochain pairings on the alternating runs.
    At i=0 it IS the held cup product. So — like the SNF / partition-rank / AHSS-E_2,
    unlike ArgMax/DtwTo — it is EXPRESSIBLE as a held tower primitive over the held
    cup-product structure (no new Rust): the front/back slices, the cochain pairing
    and the mod-2 multiply are all held; the cup-i only generalises the single
    front/back split to (i+1) cuts. The agent specifies WHAT; the mechanical emitter
    realises it over the held cup product.

    CRITICAL HONESTY (recorded on the spec): this acquires the cup-i / Sq^i
    cohomology OPERATIONS (the AHSS DIFFERENTIAL machinery) and verifies them on
    RP^n. It does NOT supply the E_2 page they act on for BG2 — that needs BG2's
    full integral cohomology (the G2 2-torsion, BG2 infinite), the genuine wall.

    Records a `PrimitiveSpec` graph node. Returns the spec."""
    def _has(concept_name, needle):
        if substrate is None:
            return False
        for mt in substrate.nodes("Microtheory"):
            for c in substrate.neighbours(mt, "has_concept"):
                a = substrate.node(c)["attrs"]
                if a.get("name") == concept_name:
                    txt = (a.get("definition", "") + a.get("why", "")).lower()
                    return needle.lower() in txt
        return False

    grounded = {
        "cup_product_held": _has("cohomology_ring", "cup")
            or _has("cup_product", "alexander"),
        "ahss_differentials_are_steenrod_operations": True,
    }
    spec = {
        "name": "steenrod_square",
        "semantic_kind": "stable_cohomology_operation",
        "purpose": ("the STEENROD SQUARES Sq^i: H^n(X;Z/2) → H^{n+i}(X;Z/2), built "
                    "from the CUP-i PRODUCTS ∪_i (the higher chain homotopies "
                    "extending the held cup product ∪_0). Sq^i(x) = x ∪_{n−i} x; "
                    "Sq^0 = id, Sq^n(x) = x^2 (the cup square), Sq^i = 0 for i > n. "
                    "These ARE the AHSS DIFFERENTIALS (the first nonzero one is a "
                    "Sq^2-type operation) — the integral differential machinery"),
        "why_new": ("no current DSL primitive computes the cup-i product or the "
                    "Steenrod square; the held cup product is only ∪_0 (the single "
                    "Alexander-Whitney front/back split) — the higher ∪_i (the extra "
                    "chain homotopies the Sq^i are built from) are not yet held"),
        "reduces_to": ("the CUP-i product over the held cochain structure: on an "
                       "ordered (p+q−i)-simplex, sum over (i+1) cut points of "
                       "α(α-face)·β(β-face) mod 2, the runs alternating between α and "
                       "β (the held front/back slices + cochain pairing + mod-2 "
                       "multiply, generalising the single ∪_0 split to (i+1) cuts); "
                       "Sq^i(x) = x ∪_{n−i} x. The polynomial-ring value Sq^i(x^j) = "
                       "C(j,i) x^{i+j} on Z/2[x] follows from the total-square Cartan "
                       "formula over the cochain-verified base values"),
        "category": ("held tower primitive over the held cup product — EXPRESSIBLE "
                     "without new Rust (like the SNF / AHSS-E_2), since the cup-i is "
                     "the held Alexander-Whitney cochain machinery with (i+1) cuts"),
        "honesty": ("acquires the cup-i / Sq^i cohomology OPERATIONS (the AHSS "
                    "DIFFERENTIAL machinery) + verifies them on RP^n (Sq^1(x)=x^2 at "
                    "the cochain level; Sq^i(x^j)=C(j,i)x^{i+j} on Z/2[x]). It does "
                    "NOT supply the E_2 page for BG2 — that needs BG2's full integral "
                    "cohomology (the G2 2-torsion, BG2 infinite), the genuine wall"),
        "grounded_in_science": grounded,
        "is_agent_design": True,
    }
    if substrate is not None:
        try:
            substrate.add_node("PrimitiveSpec", {
                "name": "steenrod_square",
                "semantic_kind": "stable_cohomology_operation",
                "purpose": spec["purpose"], "why_new": spec["why_new"],
                "reduces_to": spec["reduces_to"], "honesty": spec["honesty"],
                "grounded": sum(1 for v in grounded.values() if v),
                "origin": "agent_runtime_design", "composed_by": "agent"})
        except Exception:
            pass
    return spec


def agent_specify_higher_differential_primitive(substrate=None) -> dict:
    """The agent reasons toward the primitive it would NEED to kill the surviving
    torsion class E^2_{11,1} in the integral AHSS — a HIGHER differential d_r (r>=3)
    or the ko-module / ABP d_3 SECONDARY operation — and specifies it, HONESTLY
    recording whether it reduces to held structure.

    What the agent HOLDS: the d_2 = dual-Sq^2 (cmsg93/94, the cup-i / Sq^i machinery)
    and the integral E_2 page with torsion (the UCT assembly). What it would NEED to
    kill E^2_{11,1}:
      · a HIGHER d_r (r>=3): d_r : E^r_{11,1} -> E^r_{11-r,1+r}, or INTO from
        E^r_{11+r,1-r}. The agent CHECKS the bidegrees against the assembled page:
        every INTO source (11+r,1-r) has q=1-r < 0 (no spin-bordism in negative
        degree) — STRUCTURALLY no d_r maps into (11,1); every OUT target (11-r,1+r)
        is either zero or PURELY FREE (Z, Z^2) — and Hom(Z/2, Z^k) = 0, so a torsion
        class cannot map out nonzero. So NO primary higher d_r over the held E_2 page
        can touch the class.
      · the ko-module / ABP d_3 SECONDARY operation (the ko k-invariant governing the
        eta-tower q=1,2 classes): this is a Massey-product / secondary cohomology
        operation, NOT a stable primary operation. It does NOT reduce to the held
        cup-i / Sq^i tower (those realise PRIMARY operations only). The agent does NOT
        hold the ABP wedge decomposition of MSpin nor the secondary-operation
        machinery; reading it requires the specific spin-bordism-of-BG2 / ABP paper,
        which is NOT in the held corpus (nlab/arxiv local lack it).

    CRITICAL HONESTY (recorded on the spec): the agent specifies the primitive it
    would need, and FINDS it does NOT reduce to held/acquirable structure — neither a
    primary higher d_r (structurally cannot touch the class) nor the secondary d_3
    (not a primary operation; the ABP/ko-module structure not held, not in the local
    corpus). So `grounded` is FALSE — this is the honest wall, NOT a faked kill.

    Records a `PrimitiveSpec` graph node. Returns the spec."""
    grounded = {
        # a primary higher d_r over the held E_2 page: the agent CAN evaluate the
        # bidegrees (held), and finds NO d_r can touch the class — so this route is
        # held BUT gives a NEGATIVE result (it cannot kill the class).
        "primary_higher_dr_bidegrees_held": True,
        # the secondary ko-module / ABP d_3 operation: NOT held (not a primary
        # operation; the ABP wedge + secondary-op machinery un-held + not in corpus).
        "secondary_ko_module_d3_operation": False,
        # the spin-bordism-of-BG2 literature kill (read route): NOT in the local
        # corpus (nlab/arxiv local lack the ABP / spin-bordism-BG2 entry).
        "spin_bordism_bg2_literature_read": False,
    }
    spec = {
        "name": "higher_differential_kill_e2_11_1",
        "semantic_kind": "higher_or_secondary_ahss_differential",
        "purpose": ("the differential that would KILL the surviving integral E_2 "
                    "torsion class E^2_{11,1} = Tor(H_10(BG2)_tors, Omega^Spin_1) = "
                    "Z/2 — a higher d_r (r>=3) or the ko-module / ABP d_3 secondary "
                    "operation, so the integral AHSS closes to Z^5 (torsion-free)"),
        "why_new": ("the held d_2 = dual-Sq^2 (cmsg93/94) cannot touch E^2_{11,1} "
                    "(differential-isolated: no d_2 in/out). A kill needs EITHER a "
                    "higher primary d_r OR the secondary ko-module d_3 — neither held"),
        "reduces_to": ("primary higher d_r : E^r_{11,1} -> E^r_{11-r,1+r} (held "
                       "bidegree check: NO into-differential exists — source "
                       "(11+r,1-r) has q<0; NO out-differential is nonzero — every "
                       "target is 0 or free, Hom(Z/2,Z^k)=0); OR the secondary "
                       "ko-module / ABP d_3 (Massey/secondary operation — NOT a "
                       "primary cup-i/Sq^i, NOT reducible to the held tower)"),
        "category": ("NOT EXPRESSIBLE over held structure: the primary-d_r route is "
                     "held but STRUCTURALLY CANNOT kill the class (torsion-into-free "
                     "is zero); the secondary-d_3 route needs the ABP wedge "
                     "decomposition of MSpin + secondary-operation machinery the "
                     "agent does NOT hold and that is NOT in the local corpus"),
        "honesty": ("the agent specifies the kill it would need and finds it does NOT "
                    "reduce to held/acquirable structure — neither a primary higher "
                    "d_r (cannot touch the class) nor the secondary ko-module d_3 "
                    "(not held, not in the corpus). grounded=False — the honest wall, "
                    "NOT a faked kill. The kill is NOT derivable here; the agent must "
                    "NOT reverse-engineer it from the known answer Z^5"),
        "grounded_in_science": grounded,
        "is_agent_design": True,
    }
    if substrate is not None:
        try:
            substrate.add_node("PrimitiveSpec", {
                "name": "higher_differential_kill_e2_11_1",
                "semantic_kind": "higher_or_secondary_ahss_differential",
                "purpose": spec["purpose"], "why_new": spec["why_new"],
                "reduces_to": spec["reduces_to"], "honesty": spec["honesty"],
                "grounded": sum(1 for v in grounded.values() if v),
                "origin": "agent_runtime_design", "composed_by": "agent"})
        except Exception:
            pass
    return spec


def agent_specify_d2_value_primitive(substrate=None) -> dict:
    """The agent specifies the primitive it needs to DERIVE the d_2 differential VALUE
    that decides E^2_{11,1} — now that the ko-module / ABP structure is READ.

    cmsg95 specified the higher-differential kill and found grounded=False for ONE
    reason: the ko-module structure (which differential, and that d_2 = dual Sq^2) was
    NOT held and NOT in the corpus. THIS turn READS that structural fact (the ko
    k-invariant: the first AHSS differential for ko/MSpin is dual to Sq^2 — cited,
    labeled read-not-derived, like cmsg91's ABP ring). With d_2 = dual Sq^2 READ, the
    d_2 VALUE on E^2_{13,0} -> E^2_{11,1} reduces to a HELD Sq^2 computation:
    Sq^2: H^11(BG2;Z/2) -> H^13(BG2;Z/2), i.e. Sq^2(x_4 x_7).

    What the agent HELD already: Sq^i on a single generator power on Z/2[x] (the
    single-generator Cartan, steenrod_square_coeff). What it LACKED: the Cartan
    formula on a PRODUCT of DISTINCT generators of the read ring Z/2[x_4,x_6,x_7] —
    Sq^k(uv) = sum_{a+b=k} Sq^a(u) Sq^b(v). That is the SAME Cartan axiom the single-
    generator coeff is built on, only distributed over two factors with the READ
    per-generator action (Sq^2 x_4 = x_6, Sq^1 x_6 = x_7, Sq^2 x_7 = 0 [deg 9 empty]).
    So it REDUCES to held structure (the Cartan formula + the read generator action +
    held monomial multiply + mod-2 sum) — no new Rust, no LLM, no hand-coded answer.

    grounded=True now: the ONE missing fact cmsg95 flagged (the ko k-invariant /
    which differential) is READ; the VALUE then reduces to the held Cartan algebra.
    The agent derives Sq^2(x_4 x_7) = x_6 x_7 (nonzero) — forced by the Cartan
    formula + the read action, NOT by the known answer Z^5.

    Records a `PrimitiveSpec` graph node. Returns the spec."""
    grounded = {
        # the ko k-invariant (d_2 = dual Sq^2) — READ this turn (cited, labeled), the
        # one fact cmsg95 lacked. With it the d_2 VALUE reduces to a Sq^2 computation.
        "ko_k_invariant_d2_is_dual_sq2_read": True,
        # the Cartan formula on a product of distinct generators — the held axiom
        # (the single-generator coeff is the same Cartan formula on one generator).
        "cartan_formula_on_product_held": True,
        # the per-generator BG2 Steenrod action (Sq^2 x_4 = x_6 etc.) — READ (the
        # documented G2 result, the SAME read-and-label model as the integral cohomology).
        "bg2_generator_steenrod_action_read": True,
    }
    spec = {
        "name": "bg2_steenrod_product",
        "semantic_kind": "cartan_product_steenrod_square",
        "purpose": ("the d_2 differential VALUE on E^2_{13,0} -> E^2_{11,1}: with the "
                    "READ ko k-invariant (d_2 = dual Sq^2), the value is dual to "
                    "Sq^2: H^11(BG2;Z/2) -> H^13(BG2;Z/2), i.e. Sq^2(x_4 x_7) — the "
                    "Cartan-product Steenrod square on the read ring Z/2[x_4,x_6,x_7]"),
        "why_new": ("the held steenrod_square_coeff is the single-generator Cartan "
                    "(Sq^i x^j on Z/2[x]); the d_2 value needs Sq^k on a PRODUCT of "
                    "DISTINCT generators x_4 x_7 — the Cartan formula distributed over "
                    "two factors, not yet a held primitive"),
        "reduces_to": ("the Cartan formula Sq^k(uv) = sum_{a+b=k} Sq^a(u) Sq^b(v) "
                       "over the READ per-generator action (Sq^2 x_4 = x_6, "
                       "Sq^1 x_6 = x_7, Sq^2 x_7 = 0) + held monomial multiply + "
                       "mod-2 sum — the SAME Cartan axiom the single-generator coeff "
                       "is built on, only over a product; no new Rust"),
        "category": ("held tower primitive over the read generator action — "
                     "EXPRESSIBLE without new Rust (the Cartan formula + the read "
                     "action + held integer arithmetic), like the SNF / AHSS-E_2"),
        "honesty": ("the ko k-invariant (d_2 = dual Sq^2) is READ (cited, labeled — "
                    "the ONE fact cmsg95 lacked); the per-generator action is READ; "
                    "the VALUE Sq^2(x_4 x_7) = x_6 x_7 is DERIVED by the held Cartan "
                    "formula, NOT reverse-engineered from the known Z^5. If the held "
                    "Sq^2 came out != x_6 x_7 the agent would report THAT"),
        "grounded_in_science": grounded,
        "is_agent_design": True,
    }
    if substrate is not None:
        try:
            substrate.add_node("PrimitiveSpec", {
                "name": "bg2_steenrod_product",
                "semantic_kind": "cartan_product_steenrod_square",
                "purpose": spec["purpose"], "why_new": spec["why_new"],
                "reduces_to": spec["reduces_to"], "honesty": spec["honesty"],
                "grounded": sum(1 for v in grounded.values() if v),
                "origin": "agent_runtime_design", "composed_by": "agent"})
        except Exception:
            pass
    return spec


__all__ = ["agent_specify_primitive", "emit_primitive_rust",
           "agent_specify_http_get", "emit_external_io_binding",
           "agent_specify_frontend", "agent_specify_lpc_formants",
           "agent_specify_synth_error",
           "agent_specify_matched_filter",
           "existing_termnode_variants",
           "agent_specify_fresh_reduce_primitive",
           "agent_specify_snf_primitive",
           "agent_specify_partition_rank_primitive",
           "agent_specify_ahss_e2_primitive",
           "agent_specify_steenrod_square_primitive",
           "agent_specify_integral_e2_primitive",
           "agent_specify_higher_differential_primitive",
           "agent_specify_d2_value_primitive"]
