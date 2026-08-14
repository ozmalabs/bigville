"""Domain seed declarations — one place that names every shippable
seed, its version, its deps, and the captured JSON manifest that
defines its contents.

The earlier version of this module pointed each seed's installer at
the Python ``install_X`` function. Per CLAUDE.md (the agent is in
Rust, seeds are graph data), seeds now ship as JSON manifests
captured from a one-shot run of those installers — see
``tools/capture_seed.py``. The installers themselves remain in the
codebase as the source of truth for capture, but are no longer the
agent's boot path.

Adding a new seed:
  1. Write its installer in a domain module (or contribute one).
  2. Add a Seed entry here that points at the installer (for the
     capture tool's benefit) AND declares its deps + manifest.
  3. Run ``python -m tools.capture_seed <id>`` to produce the
     manifest at ``seeds/<id>.json``.

Composite seeds (`chat`, `voice`) declare deps only — no installer.
Loading them pulls the closure.
"""
from __future__ import annotations

from substrate.seeds import REGISTRY, Seed
from substrate.seed_loader import apply_manifest, manifest_for


def _installer_from_manifest(seed_id: str):
    """Build an installer callable that applies the captured manifest
    for `seed_id`. Late-binds the file read so the JSON is loaded once
    per boot rather than at module-import time."""
    def install(agent) -> None:
        apply_manifest(agent, manifest_for(seed_id))
    install.__name__ = f"apply_{seed_id}_manifest"
    return install


# --- atomic seeds ------------------------------------------------------

REGISTRY.register(Seed(
    id="decision_core", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("decision_core"),
    description="The agent's core decision faculties as graph data — "
                "goal-construction Rule (+ goal-pressure / action-score / "
                "recognition Terms). Migrated from CuriousAgent and "
                "parity-verified; has NO Python installer (it is migrated "
                "graph data, not captured from an install_X).",
))

REGISTRY.register(Seed(
    id="learning_core", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("learning_core"),
    description="The agent's causal-inference faculty as graph data — "
                "salience/lift, confound-screening (explaining-away), and "
                "interventional (do-contrast) predicate Terms, attached to "
                "agent_root by named edges. Migrated from CuriousAgent and "
                "parity-verified; NO Python installer (migrated graph data).",
))

REGISTRY.register(Seed(
    id="perception_core", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("perception_core"),
    description="The agent's perception/observe recognitions as graph "
                "data — gauge-type recognition (Argmax over BodyType "
                "net-shedding), turns-remaining clamp, novelty channel-1 "
                "(unseen scalar attr triples). Migrated from CuriousAgent "
                "and parity-verified; NO Python installer.",
))

REGISTRY.register(Seed(
    id="epistemics_core", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("epistemics_core"),
    description="The agent's epistemic/ontological judgment predicates as "
                "graph data — saturation ('I know this well enough'), "
                "ephemerality vs object-permanence, law-discovery, and "
                "conservation. Migrated from CuriousAgent and "
                "parity-verified; NO Python installer.",
))

REGISTRY.register(Seed(
    id="theorem_core", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("theorem_core"),
    description="The agent's theorems about its own behaviour (tau-3) as "
                "graph data — Theorem nodes (sensed_implies_modeled, "
                "quality_monotone, discovery_converges) each carrying a "
                "predicate Term-tree, asserted by agent_root. Captured from "
                "CuriousAgent; NO Python installer.",
))

REGISTRY.register(Seed(
    id="memory_core", version="1.1.0", depends_on=(),
    installer=_installer_from_manifest("memory_core"),
    description="Legacy episodic capture/retention rules with compatibility "
                "guards that defer rich episodes to replay-driven semantic "
                "consolidation in episodic_working_memory_core.",
))

REGISTRY.register(Seed(
    id="reflex_core", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("reflex_core"),
    description="Affect + reference reflexes as graph data — emotion EMA "
                "update, pointer-from-grounded-concept. Auto-captured from "
                "the agent's graph-native Rules; NO Python installer.",
))

REGISTRY.register(Seed(
    id="affective_state_core", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("affective_state_core"),
    description="Canonical graph-native affect and drive integration: "
                "continuous valence/arousal/resolution/competence state, "
                "drive competition with hysteresis, and action-selection "
                "threshold modulation.",
))

REGISTRY.register(Seed(
    id="dual_process_core", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("dual_process_core"),
    description="Core graph-native System 1/System 2 arbitration: grounded "
                "learned/default responses commit on the hard-real-time sheet; "
                "prediction error, novelty, uncertainty, conflict, or no safe "
                "default mint an explicit SystemTwoEscalation. Affect modulates "
                "fast valuation and escalation, and verified slow outcomes "
                "consolidate back into reusable defaults.",
))

REGISTRY.register(Seed(
    id="episodic_working_memory_core", version="1.1.0",
    depends_on=("memory_core",),
    installer=_installer_from_manifest("episodic_working_memory_core"),
    description="Executable episodic binding, cue-bounded reconstructive "
                "retrieval, prioritized replay/reconsolidation, and "
                "capacity-limited graph-native working/task-memory gates.",
))

REGISTRY.register(Seed(
    id="adaptive_control_core", version="1.0.0",
    depends_on=("affective_state_core", "dual_process_core", "motor_core"),
    installer=_installer_from_manifest("adaptive_control_core"),
    description="Graph-native temporal credit assignment, precision-separated "
                "learning control, sensorimotor forward prediction, allostatic "
                "forecasting, skill chunking, and bounded functional broadcast.",
))

REGISTRY.register(Seed(
    id="generative_world_model", version="1.0.0",
    depends_on=(),
    installer=_installer_from_manifest("generative_world_model"),
    description="Provenance-safe belief states and learned action-conditioned "
                "transition hypotheses supporting bounded, content-bearing "
                "counterfactual trajectories and prediction-error revision.",
))

REGISTRY.register(Seed(
    id="counterfactual_experiment", version="1.0.0",
    depends_on=("generative_world_model",),
    installer=_installer_from_manifest("counterfactual_experiment"),
    description="Graph-native epistemic-modality routing for self-tests: "
                "graph/rule hypotheses run through detached ungrounded "
                "cognition, while tests requiring observations or interaction "
                "remain external. Imagined results are evidence, never oracles.",
))

REGISTRY.register(Seed(
    id="default_mode_core", version="2.0.0",
    depends_on=("affective_state_core", "dual_process_core",
                "generative_world_model"),
    installer=_installer_from_manifest("default_mode_core"),
    description="Continuous graph-native intrinsic/default-mode control: "
                "overlapping network weights gate bounded, interruptible "
                "content-bearing prospective simulation and episodic replay "
                "with explicit imagined/predicted provenance.",
))

REGISTRY.register(Seed(
    id="self_monitoring", version="1.0.0", depends_on=("experimentation_core",),
    installer=_installer_from_manifest("self_monitoring"),
    description="The agent's surprise->investigation self-monitoring as "
                "graph data — the 3-rule cascade (construct investigation "
                "subroutine + recall query, execute query into causes_set, "
                "pick top cause by nested Argmax). Auto-captured from the "
                "agent's own graph-native Rules; NO Python callback.",
))

REGISTRY.register(Seed(
    id="goal_construction", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("goal_construction"),
    description="Parameterized goal construction as graph data — a generic "
                "achieve-attr satisfaction proto Term (reads the target's "
                "attr named by the goal's own target_attr, via AttrByName) + "
                "a Rule that mints a typed Goal from an achieve_attr_request. "
                "One Term + one Rule serve the whole achieve-attr goal "
                "family. NO Python installer.",
))

REGISTRY.register(Seed(
    id="experimentation_core", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("experimentation_core"),
    description="The agent's curiosity drives + active experimentation as "
                "graph data — order_n_curiosity (prediction-error pull), "
                "abs_info_gain, event_salience, intervention_lift "
                "(do-contrast), hypothesis_test, experiment_value (pull "
                "toward DOING the test). Captured from CuriousAgent's "
                "Term-builders; NO Python installer.",
))

REGISTRY.register(Seed(
    id="motor_core", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("motor_core"),
    description="The agent's spatial-motor + navigation value functions as "
                "graph data — motor_value (feedback control: turn toward "
                "target, move when aligned), attention_value (orient to a "
                "salient pop-out), exploration_value (recency + under-known "
                "+ door-to-unknown + salience). Captured from CuriousAgent's "
                "own Term-builders; NO Python installer.",
))

REGISTRY.register(Seed(
    id="somatomotor_waves", version="1.5.0",
    depends_on=("embodied_development",),
    installer=_installer_from_manifest("somatomotor_waves"),
    description="Body-plan-neutral spontaneous motor activity: integer "
                "homeostatic ignition, topology-local propagation, "
                "refractoriness, one compound wavefront outcome and verified "
                "reafferent learning. The body boundary publishes topology "
                "and a clock; every structured proposal is graph-native.",
))

REGISTRY.register(Seed(
    id="relations", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("relations"),
    description="Foundational binary semantic relations "
                "(uses / has / runs_on / is_a / depends_on / …).",
))

REGISTRY.register(Seed(
    id="grounding", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("grounding"),
    description="Opens the Γ productions admitting Concept->Concept "
                "structural-grounding edges (built_from / depends_on / "
                "grounds / genls) + the Microtheory->has_concept->Concept "
                "frame edge. The read-and-ground faculty's built_from "
                "mutation is inadmissible (silently dropped) without these; "
                "with the seed any seed-booted agent grounds concepts by "
                "reading. Productions only (admissible-edge schema), NO Rules.",
))

REGISTRY.register(Seed(
    id="frames", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("frames"),
    description="Frame / Microtheory register layer (FrameNet + CYC): inquiry "
                "Frames evoked_by surface forms, realised_by capability Concepts, "
                "scoped by holds_in Microtheories under genlMt inheritance.",
))

REGISTRY.register(Seed(
    id="lexical_ontology_roots", version="1.0.0", depends_on=("grounding",),
    installer=_installer_from_manifest("lexical_ontology_roots"),
    description="WordNet unique-beginners (entity / abstraction / "
                "physical_entity / psychological_feature / attribute / object "
                "/ group) as basis-primitive Concepts + is-a (built_from) edges "
                "mirroring WordNet hypernymy. The genus-deepening BEDROCK: every "
                "lexical-genus descent (wordnet_genus reader -> read_and_ground) "
                "bottoms out at the single root 'entity'. Depends on grounding "
                "(the built_from edges need its opened Γ productions).",
))

REGISTRY.register(Seed(
    id="psychology", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("psychology"),
    description="Mental-state vocabulary + theory-of-mind concepts.",
))

REGISTRY.register(Seed(
    id="design", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("design"),
    description="Design Mt + design_query_frame + propose_design "
                "capability.",
))

REGISTRY.register(Seed(
    id="llm_partner", version="1.0.0", depends_on=("relations",),
    installer=_installer_from_manifest("llm_partner"),
    description="Concepts the agent uses to reason about its "
                "conversation partner.",
))

REGISTRY.register(Seed(
    id="conversation", version="1.0.0", depends_on=("relations",),
    installer=_installer_from_manifest("conversation"),
    description="Speech-act taxonomy + adjacency-pair structure + "
                "Grice maxims + repair concepts + conversational signs.",
))

REGISTRY.register(Seed(
    id="intent", version="1.0.0",
    depends_on=("conversation", "psychology", "relations"),
    installer=_installer_from_manifest("intent"),
    description="Intent / Unknown / Mention types + the rewrite Rules "
                "that build an Intent for each Message.",
))

REGISTRY.register(Seed(
    id="conversation_reply", version="1.0.0", depends_on=("intent",),
    installer=_installer_from_manifest("conversation_reply"),
    description="Turn-taking reply Rule: an inbound Message whose Intent "
                "expects a response (adjacency pair) and isn't yet replied to "
                "gets the agent's outbound second-pair-part Message (speech act "
                "+ responds_to). The reply DECISION as graph data.",
))


# --- audio + speech ----------------------------------------------------

REGISTRY.register(Seed(
    id="audio", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("audio"),
    description="Cochlea / gammatone / STFT / A1 productions.",
))

REGISTRY.register(Seed(
    id="native_codec", version="1.0.0", depends_on=("audio",),
    installer=_installer_from_manifest("native_codec"),
    description="Native codec parser productions (MP3 / Vorbis / "
                "Opus / AAC / FLAC) — the bitstream-as-substrate "
                "graph types.",
))

REGISTRY.register(Seed(
    id="speech", version="1.0.0", depends_on=("audio",),
    installer=_installer_from_manifest("speech"),
    description="AcousticSign / Lexicon / Utterance productions "
                "+ ingest_speech-compatible types.",
))

REGISTRY.register(Seed(
    id="whisper_grounding_guard", version="1.0.0", depends_on=("speech",),
    installer=_installer_from_manifest("whisper_grounding_guard"),
    description="Graph-native encoder grounding for a borrowed Whisper "
                "proposal: Argmin chooses the closed-vocabulary candidate, "
                "its support-derived radius admits or refuses it, and graph "
                "rules accept/correct/abstain with explicit provenance.",
))

REGISTRY.register(Seed(
    id="published_net_causal_debugger", version="1.0.0",
    depends_on=("experimentation_core", "learning_core"),
    installer=_installer_from_manifest("published_net_causal_debugger"),
    description="Graph-native experiment selection, do-contrast causal "
                "hypothesis revision, and no-retraining patch authorship for "
                "instrumented published neural networks.",
))

REGISTRY.register(Seed(
    id="published_model_engineering", version="1.0.0",
    depends_on=("learning_core",),
    installer=_installer_from_manifest("published_model_engineering"),
    description="Deterministic program understanding and proof-carrying "
                "modification of published computational models.",
))

REGISTRY.register(Seed(
    id="contextual_model_edit", version="1.0.0",
    depends_on=("learning_core",),
    installer=_installer_from_manifest("contextual_model_edit"),
    description="Graph-authored contextual residual-state adapters with "
                "closed-form factors and protected-control proofs.",
))


# --- video + transcoding (non-agent seeds — graph-modularity proof) ---
#
# These are loadable into a bare substrate_rs.Substrate (no agent
# required). They demonstrate that the seed system isn't agent-
# coupled — transcoding pipelines, codec configurations, anything
# graph-resident composes from the same loader.

REGISTRY.register(Seed(
    id="video", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("video"),
    description="Video codec grammar: VideoContainer / VideoStream / "
                "Frame / MotionVector + their relationship edges.",
))

REGISTRY.register(Seed(
    id="transcoding", version="1.0.0", depends_on=("video",),
    installer=_installer_from_manifest("transcoding"),
    description="ABR ladder + transcode job ontology. TranscodeJob, "
                "Ladder, LadderRung node types + a default 3-tier HLS "
                "ladder as seed data (1080p/720p/480p).",
))

REGISTRY.register(Seed(
    id="transcription", version="1.0.0", depends_on=("speech",),
    installer=_installer_from_manifest("transcription"),
    description="Substrate-native STT: AcousticSign --labelled_as--> "
                "Transcription + Utterance --has_transcription--> "
                "Transcription productions. Pairs with "
                "TranscriptionPipeline (teach + transcribe + helpers).",
))

# --- biological auditory pathway -------------------------------------
# Each seed = one anatomical stage. Built layer-by-layer above the
# cochlea so each layer's output is independently testable.

REGISTRY.register(Seed(
    id="cochlear_nucleus", version="1.0.0", depends_on=("audio",),
    installer=_installer_from_manifest("cochlear_nucleus"),
    description="First stage above the cochlea. OnsetEvent + "
                "EnvelopeChannel + BroadbandOnset node types and "
                "their productions — graph schema for onset / "
                "sustained-response / cross-band coincidence "
                "channels. Compute lives in cochlear_nucleus_runtime.",
))

REGISTRY.register(Seed(
    id="categorical_perception", version="1.0.0",
    depends_on=("auditory_cortex",),
    installer=_installer_from_manifest("categorical_perception"),
    description="STG-style categorical perception: clusters A1 "
                "patch responses into emergent Phoneme nodes. "
                "Online leader-follower clustering with cosine "
                "distance; Phonemes persist across runs and "
                "accumulate samples.",
))

REGISTRY.register(Seed(
    id="lexical_access", version="1.0.0",
    depends_on=("categorical_perception", "speech"),
    installer=_installer_from_manifest("lexical_access"),
    description="Top of the auditory pathway: phoneme sequences "
                "bind to AcousticSign entries in an AcousticLexicon. "
                "Re-hearing audio reuses signs; lexicon grows "
                "monotonically. Pairs with the chat-side intent "
                "Rules via the existing speech-bridge.",
))

REGISTRY.register(Seed(
    id="inferior_colliculus", version="1.0.0",
    depends_on=("cochlear_nucleus",),
    installer=_installer_from_manifest("inferior_colliculus"),
    description="Modulation-rate analysis above the cochlear "
                "nucleus. ModulationChannel + ModulationEvent + "
                "SyllableNucleus node types. The 4-8 Hz modulation "
                "channel carries syllable rate; cross-band peaks "
                "there are syllable-nucleus events.",
))

REGISTRY.register(Seed(
    id="speech_bootstrap", version="1.0.0",
    depends_on=("speech", "categorical_perception",
                 "lexical_access", "sonority_valley",
                 "compositional_chunking"),
    installer=_installer_from_manifest("speech_bootstrap"),
    description="Speech-and-sound concept vocabulary as graph data. "
                "Mints abstract Concept nodes (phoneme / syllable / "
                "word / utterance / boundary / silence / voice / "
                "sequence) + their hierarchy (kind_of / composed_of "
                "/ bounded_by). Subsequent calls to "
                "bootstrap_speech_concepts add is_a edges from "
                "concrete substrate nodes (Phoneme, AcousticSign, "
                "Utterance, SonorityValley) to their abstract "
                "category, so alignment Rules can reason about kind.",
))

REGISTRY.register(Seed(
    id="reconsider", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("reconsider"),
    description="Substrate-level budget loop. SubstrateRoot "
                "carries per-tick wall-cost; Capability declares a "
                "tick_budget_ms + a current mode. Domain Rules opt "
                "into mode-gating by linking to a Capability via "
                "regulated_by. Reconsider Rules flip mode between "
                "active and passive based on observed cost vs "
                "budget — the agent's structural response to its "
                "own compute pressure.",
))

REGISTRY.register(Seed(
    id="tunable_parameter", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("tunable_parameter"),
    description="Graph-resident introspection of agent-tunable "
                "knobs. TunableParameter nodes record attr_name + "
                "min/max/step + owner; the agent walks has_tunable "
                "to discover what it can tune. Tuning Rules are "
                "per-knob (specific metric + attr) but read bounds "
                "+ step from the TP node — so the agent can edit "
                "its own learning rates as graph data.",
))

REGISTRY.register(Seed(
    id="reflex_net", version="1.0.0",
    depends_on=("tunable_parameter",),
    installer=_installer_from_manifest("reflex_net"),
    description="Graph-resident optional small nets, grounded basin gates, "
                "and the native surprise-collapse rule that trains a local "
                "readout from graph observations.",
))

REGISTRY.register(Seed(
    id="compositional_chunking", version="1.0.0",
    depends_on=("lexical_access",),
    installer=_installer_from_manifest("compositional_chunking"),
    description="Recurring sign sequences become compositional "
                "AcousticSigns. Rust chunk_discovery Op tracks "
                "BigramObservation counts; a graph Rule promotes a "
                "bigram into a sign once its count crosses threshold. "
                "Compositional signs then fire as runtime Utterances "
                "when the bigram pattern recurs. Recursion is free: "
                "compositional signs are AcousticSigns, so phrases-"
                "of-phrases emerge by the same mechanism.",
))

REGISTRY.register(Seed(
    id="sonority_valley", version="1.0.0",
    depends_on=("cochlear_nucleus",),
    installer=_installer_from_manifest("sonority_valley"),
    description="Sonority-valley word-boundary detector. SonorityValley "
                "node type + has_sonority_valley edge. Per-stream "
                "Operation sums envelope buffers, finds deep minima of "
                "the smoothed total envelope, emits boundary nodes that "
                "lexical_access consumes in place of BroadbandOnset "
                "gap-clustering. Robust to continuous-speech inputs.",
))

REGISTRY.register(Seed(
    id="auditory_cortex", version="1.0.0",
    depends_on=("inferior_colliculus",),
    installer=_installer_from_manifest("auditory_cortex"),
    description="A1 / belt cortex — spectro-temporal patches (STRFs). "
                "Installs a starter library of A1Patch nodes covering "
                "voiced / sibilant / burst / FM-glide features. Each "
                "patch is evaluated against cochlear envelopes; "
                "responses + discrete events land as graph data.",
))


# --- composite seeds — bundles of deps, no installer of their own. ----

REGISTRY.register(Seed(
    id="chat", version="1.0.0",
    depends_on=("intent", "design", "llm_partner"),
    installer=None,
    description="The chat agent's full prior-knowledge set. World "
                "adapters that need the chat surface request this.",
))

REGISTRY.register(Seed(
    id="voice", version="1.0.0",
    depends_on=("chat", "speech", "native_codec"),
    installer=None,
    description="Chat + ear. AudioWorld and other speech-capable "
                "adapters request this.",
))

REGISTRY.register(Seed(
    id="sensory_convolution", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("sensory_convolution"),
    description="Convolution as a graph-native sense-agnostic perceptual "
                "primitive (no Python): MaxOver(patches, Dot(kernel.weights, "
                "patch.vals)) evaluated in Rust. A kernel family is seed data; "
                "a sense KEEPS the kernels that discriminate via the "
                "keep_discriminative_kernel rule. Registered here so "
                "load_seeds_into can pull it as a vision_floor dependency.",
))

REGISTRY.register(Seed(
    id="math_capability_shapes", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("math_capability_shapes"),
    description="The ShapeSignature / CapabilityAxis codebook shapes the "
                "sd_* loop decodes against. Registered so load_seeds_into can "
                "pull it as a shape_decode_loop -> vision_floor dependency.",
))

REGISTRY.register(Seed(
    id="self_design_axis", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("self_design_axis"),
    description="The self-design axis data the sd_* loop grows against. "
                "Registered so load_seeds_into can pull it as a "
                "shape_decode_loop -> vision_floor dependency.",
))

REGISTRY.register(Seed(
    id="shape_decode_loop", version="1.0.0",
    depends_on=("math_capability_shapes", "self_design_axis"),
    installer=_installer_from_manifest("shape_decode_loop"),
    description="DYNAMIC QUANTIZATION as graph rules: sd_decode / sd_recognize "
                "/ sd_transform_decode / sd_infer_dimension / sd_mint_quantum "
                "/ sd_redecode / codebook_epoch. A residual mints a "
                "CapabilityAxis / LatentDimension; the run_rules fixpoint IS "
                "the decode->grow->re-decode loop. Registered so load_seeds_into "
                "can pull it as a vision_floor dependency.",
))

REGISTRY.register(Seed(
    id="continuous_pose", version="1.0.0",
    depends_on=("shape_decode_loop",),
    installer=_installer_from_manifest("continuous_pose"),
    description="CONTINUOUS POSE (FRONTIER rung T1): real-angle rotation as a "
                "cross-frame generator (Rotate, continuous theta) rendered to the "
                "stepped integer lattice, decided by the held continuous verdict "
                "PointSetDist over a discrete-codebook proposal (bins propose, "
                "continuous decides). Rules cp_recognize / cp_refuse gated on the "
                "NEW flag agent.cont_pose (OFF by default). No new Rust.",
))

REGISTRY.register(Seed(
    id="vision_floor", version="1.0.0",
    depends_on=("sensory_convolution", "shape_decode_loop", "motor_core",
                "reflex_core"),
    installer=_installer_from_manifest("vision_floor"),
    description="VISION FLOOR (S1.1-S1.4) — the developmental vision floor. A "
                "vision Sense is armed with the sensory_convolution candidate "
                "kernel pool (vf_arm_candidate_pool) and "
                "keep_discriminative_kernel SELECTS the ones whose response "
                "varies across the sense's fields. NOTE (corrected 2026-07-16): "
                "this is SELECTION FROM A HAND-DESIGNED POOL, not emergence — "
                "sensory_convolution ships six designed:1.0 kernels (including "
                "centre_surround and edge_axis1) and no rule mints a Kernel, so "
                "the earlier 'biology emerges from image statistics' claim was "
                "finding what the seed planted (an injected garbage kernel is "
                "kept just as readily). Genuine growth lives in the "
                "`vision_growth` seed (mint-on-residual + Oja's rule). Also "
                "here: foveated sampling via the Foveate Term over an agent-"
                "revisable SamplingGeometry node; dorsal motion (TemporalDiff) "
                "/ ventral identity dual codebook_scope split; figure-ground-"
                "as-surprise; region-as-belief. Every threshold is graph data. "
                "NO vision_*.json encyclopedic seeds are in the boot.",
))

REGISTRY.register(Seed(
    id="vision_waves", version="1.0.0",
    depends_on=(),
    installer=_installer_from_manifest("vision_waves"),
    description="RUNG 1 — SPONTANEOUS RETINAL WAVES + burst-based Hebbian. The "
                "agent generates its OWN structured training signal before it "
                "perceives anything: the adapter supplies only unstructured "
                "entropy (random ignition) + a clock, and wv_propagate / "
                "wv_refract / wv_recover turn that noise into spatiotemporally "
                "correlated travelling waves. bh_potentiate / bh_depress are "
                "the MEASURED burst rule (+21.3% coincident / -5.9% "
                "non-overlapping, ~1s window, Butts/Kanold/Shatz 2007) on "
                "Synapse NODES. The noise control arm is the same entropy with "
                "WaveParams.propagate=0 — an ablation as data, not a code path.",
))

REGISTRY.register(Seed(
    id="vision_settle", version="1.0.0",
    depends_on=("vision_waves",),
    installer=_installer_from_manifest("vision_settle"),
    description="THE CORTICAL SETTLING LOOP — the layer nine Hebbian rungs "
                "were missing. The wave-isotropy rung measured WHY they "
                "failed: E[xx^T]'s leading eigenvector is a DC BLOB "
                "(leading_OI 0.0855, lambda1/lambda2 3.52) and removing the "
                "DC leaves a near-degenerate oriented pair "
                "(lambda2/lambda3 1.09), so Oja converges to a blob and "
                "whitening hands the oriented modes over as a coin flip. "
                "GCAL escapes this via NEITHER its stimulus (verified from "
                "the primary: noisy disks, MORE isotropic than our waves) "
                "NOR its rule (Hebbian + divisive normalisation = Oja), but "
                "via the SETTLING STEPS that run WITHIN a pattern BEFORE the "
                "Hebbian step. st_settle relaxes the sheet to a fixed point "
                "under local excitation (the committed adjacency, each edge "
                "counted once) and global competition (the sheet's OWN mean "
                "— a RELATIVE threshold), and the step count is not a "
                "constant at all: run_rules IS the fixpoint, terminating "
                "exactly when activity stops changing, which is GCAL's own "
                "stated criterion for its 16. NONE of GCAL's constants are "
                "imported (PROTOCOL 13). Ships INERT (settle=0, bubble=0) so "
                "every committed result reproduces byte-identically.",
))

REGISTRY.register(Seed(
    id="vision_maps", version="1.0.0",
    depends_on=("vision_waves",),
    installer=_installer_from_manifest("vision_maps"),
    description="RUNG 4 — ORIENTATION MAP TOPOGRAPHY: the LATERAL INTERACTION "
                "without which no map could form. Under the committed hard "
                "global winner-take-all exactly one Unit learns per step, so "
                "cortically adjacent units can never co-tune — there is no "
                "mechanism by which nearby units could know about each other. "
                "vm_burst_lateral additionally bursts every Unit that is a "
                "`cortical_neighbour` of the Argmax winner, so the winner's "
                "neighbourhood learns the SAME input on the SAME step (the "
                "Kohonen/SOM neighbourhood update; local excitation + retained "
                "global competition = a Mexican hat). The cortical sheet's "
                "geometry is wired by `domains/cortex_sheet.py` exactly as the "
                "retina's own 4-neighbourhood is. MapParams.lateral=0 default "
                "— the ablation is DATA, not a code path, and every result "
                "committed before rung 4 reproduces byte-identically.",
))

REGISTRY.register(Seed(
    id="vision_onoff", version="1.0.0",
    depends_on=("vision_waves",),
    installer=_installer_from_manifest("vision_onoff"),
    description="RUNG 6 — THE SIGNED SIMPLE LAYER via an ON/OFF RETINAL SPLIT. "
                "Rung 5 measured why the Units have no orientation-selective "
                "RESPONSE (OSI 0.004 vs an ideal Gabor's 1.000): Oja on "
                "non-negative input keeps weights strictly positive "
                "(frac(w<0)=0.0000) => a DC-dominated response, so the oriented "
                "structure that IS in the weights never reaches it (GABOR vs "
                "GABOR+DC: identical anisotropy 0.8672, OSI 1.0000 vs 0.0000). "
                "Biology does not force the sign into the WEIGHT: it splits the "
                "retina into ON and OFF pathways and keeps synapses sign-constant "
                "(Dale), so a cell's EFFECTIVE RF w+ - w- is signed while every "
                "weight stays >= 0. ONE wave field drives BOTH channels "
                "(oo_bipolar_burst: ON = x, OFF = 1-x off the same RetinaCell), "
                "so aligned adjacent ON/OFF subregions (Hubel & Wiesel; Reid & "
                "Alonso) are an OUTCOME to grow, never an input — hand-segregating "
                "the waves would be the bolt-on error. Learning is Miller & MacKay "
                "1994 subtractive normalisation (oo_sunit_xbar -> oo_learn_sub: "
                "dw = eta*y*(x - xbar), clipped to [0, wmax]), the canonical rule "
                "for ON/OFF segregation: it projects out the uniform/DC mode that "
                "multiplicative/divisive normalisation — our Oja, == GCAL's to "
                "first order — preserves. Ablations are DATA: split=0 collapses "
                "OFF onto ON (a single non-negative channel = rung 5's condition, "
                "identical anatomy); subnorm=0 runs plain Oja on the split; "
                "frozen=1 is A REAL FREEZE gating every learning rule here (the "
                "fix for `oja=0` IS NOT A FREEZE, which switches the fixed-sign "
                "rule ON and moved weights 47.9 per probe). onoff=0.0 default => "
                "the layer is inert and every result committed before rung 6 "
                "reproduces byte-identically.",
))

REGISTRY.register(Seed(
    id="vision_compose", version="1.0.0",
    depends_on=("vision_waves", "vision_lateral", "vision_onoff"),
    installer=_installer_from_manifest("vision_compose"),
    description="RUNG 8 — COMPOSE rung 7's eye with rung 6's cortex. Rung 6's "
                "signed simple layer failed to develop on its OWN channels "
                "(OSI 0.283 -> 0.329 vs a 0.3168 floor) and diagnosed its own "
                "split as DEGENERATE: x_OFF = 1 - x_ON forces C_ON,OFF(d) = "
                "-C_ON,ON(d) identically, so the channels carry no independent "
                "correlation structure — exactly what Miller 1994 consumes. "
                "Rung 7 supplies channels that DO have different spatial "
                "dependence (SD 0.3601; sigma ratio 2.007) but claimed no "
                "orientation selectivity ('a precondition is not a result'), "
                "and the two seeds were never composed. This seed composes "
                "them and re-runs rung 6's own convergence gate and OSI "
                "measure UNCHANGED, testing whether the precondition was the "
                "blocker. It adds NO rule: rung 6's SUnit rules bind their "
                "presynaptic channel by an UNTYPED traversal and read only "
                "bursting/bstep, which rung 7's LBipolar carries — so the "
                "cortex is grain-agnostic about its retina and composition is "
                "pure ANATOMY (verified, not assumed). vision_lateral and "
                "vision_onoff are NOT edited: compose, don't modify. "
                "compose=0.0 default => inert, and every result committed "
                "before rung 8 reproduces byte-identically.",
))

REGISTRY.register(Seed(
    id="vision_theta", version="1.0.0",
    depends_on=("vision_waves", "vision_onoff"),
    installer=_installer_from_manifest("vision_theta"),
    description="RUNG 8B — THETA IS NOT GCAL's THETA. Rung 8 stopped at the "
                "PROTOCOL 1 gate: an IDEAL split-Gabor scored OSI 0.1290 on the "
                "composed pathway vs 1.0000 on rung 6's own, so the probe was "
                "blind and no arm was interpretable. Cause measured: theta is an "
                "EMA of the cell's own drive on the FORMATIVE input, and rung "
                "7's retina is a predictive coder — waves are cheap (act 0.861), "
                "an out-of-distribution grating is expensive (1.902, 2.21x), so "
                "theta lands at 0.774 BELOW the probe drive and the iceberg "
                "never bites. THE FIX IS A FIDELITY CLAIM, NOT A SEARCH: rung "
                "6's oo_sunit_adapt_theta CITES GCAL and implements something "
                "structurally different. GCAL (Stevens 2013, Eqs 7-8) integrates "
                "the error between an EMA of the cell's OUTPUT and a SETPOINT "
                "mu; rung 6's rule low-pass-FOLLOWS the INPUT drive and "
                "regulates nothing. A follower is scale-LOCKED to the ensemble "
                "it last saw; a setpoint regulator has an operating point BY "
                "CONSTRUCTION. Rung 6 kept GCAL's PLACEMENT (where theta cannot "
                "flip dw's sign) and dropped GCAL's SETPOINT — which is what "
                "rung 8's I.1 named: 'nothing there pins its SCALE across "
                "distributions'. Constants are GCAL's published values, literal "
                "and unmodified, ONE set for both pathways. theta_mode=0.0 "
                "default => inert, and every result committed before rung 8B "
                "reproduces byte-identically. vision_onoff is NOT edited: the "
                "arm sets its existing homeo=0, which pins the EMA rule.",
))

REGISTRY.register(Seed(
    id="vision_sdloop", version="1.0.0",
    depends_on=("shape_decode_loop",),
    installer=_installer_from_manifest("vision_sdloop"),
    description="THE SD-LOOP VISION RUNG (seeds 18000-18999, "
                "VISION_SDLOOP_PREREG.md) — point the substrate's OWN "
                "dynamic-quantization loop at rung 7's decorrelated ON/OFF "
                "channels. Every vision rung before this used a BORROWED "
                "learning rule (Oja/BCM/Butts/GCAL); this one uses none, and "
                "no vision-specific machinery: the retina's ON/OFF support is "
                "ingested as an Observation signature and the EXISTING sd loop "
                "decides everything. Adds exactly ONE rule (vq_grow_quantum), "
                "because exactly one thing was missing — sd_mint_quantum mints "
                "a CapabilityAxis but installs no ShapeSignature, so a minted "
                "quantum could never be re-recognized and the codebook could "
                "not grow from the loop's own mints. Guarded on obs.vq==1 so "
                "the seed is INERT on every boot that is not this rung's "
                "(PROTOCOL §9).",
))

REGISTRY.register(Seed(
    id="vision_lateral", version="1.0.0",
    depends_on=("vision_waves",),
    installer=_installer_from_manifest("vision_lateral"),
    description="RUNG 7 — RETINAL LATERAL INHIBITION, so CENTRE-SURROUND "
                "EMERGES. Rung 6's measured diagnosis: the complementary split "
                "x_OFF = 1 - x_ON is ITSELF degenerate — it determines OFF "
                "exactly, so C_ON,OFF(d) = -C_ON,ON(d) IDENTICALLY and the two "
                "channels carry no independent correlation structure. Miller "
                "1994 gets ON/OFF segregation precisely from correlation "
                "functions with DIFFERENT spatial dependence (centre-surround "
                "RFs of different sizes), so the ON/OFF sign is NECESSARY (it "
                "removed rung 5's blocker) but NOT SUFFICIENT. This seed gives "
                "the channels their own spatial dependence by GROWING "
                "centre-surround: a horizontal cell pools the RetinaCell's "
                "radius-1/radius-2 rings along the `neighbour` edges rung 1 "
                "declared and left unused (wv_propagate was the sole consumer), "
                "the bipolar transmits the RESIDUAL centre - g1*h1 - g2*h2, and "
                "ON/OFF are its two rectified non-negative halves (Dale intact; "
                "no signed weight, no hand-built DoG — substrate_rs/vision.py's "
                "lgn_pair/dog is the bolt-on error PROTOCOL §0 names and is "
                "rejected: its output is already signed, assuming away the very "
                "thing rung 5 measured). THE GAIN IS LEARNED, never hand-set: "
                "lat_learn_gain runs anti-Hebbian decorrelation dg = "
                "eta*resid*h, whose fixed point E[resid*h]=0 IS the normal "
                "equations — Srinivasan/Laughlin/Dubs 1982's optimal linear "
                "predictor of centre from surround, DERIVED not received. That "
                "is why Atick & Redlich's SNR-dependent surround (weakens in "
                "the dark, sharpens in the light) is a falsifiable PREDICTION "
                "here rather than a fitted constant — a hand-set gain cannot "
                "make it and a learned gain can fail it. Centre-surround IS "
                "predictive coding, i.e. the substrate's own "
                "prediction_minus_observation shape in the first synapse. "
                "Ablations are DATA: learn_gain=0 pins g at lat_g0 (the "
                "fixed-gain control); radius2=0 pins g2=0 with the anatomy "
                "standing; frozen=1 is A REAL FREEZE gating every learning rule "
                "here. lat_g0=0.0 => the layer starts as a PURE CENTRE with no "
                "surround, so the profile is grown. lateral=0.0 default => the "
                "layer is inert and every result committed before rung 7 "
                "reproduces byte-identically.",
))

REGISTRY.register(Seed(
    id="vision_complex", version="1.0.0",
    depends_on=("vision_waves",),
    installer=_installer_from_manifest("vision_complex"),
    description="RUNG 5 — COMPLEX CELLS: phase invariance. A CUnit population "
                "POOLS the simple Units (Unit -cpre-> CSynapse -cpost-> CUnit; "
                "the pooling anatomy is wired by `domains/complex_cells.py` "
                "exactly as retinotopy is), with TEMPORAL SLOWNESS (Foldiak "
                "1991) on an Oja-normalised update: cx_trace keeps a leaky "
                "running average of the CUnit's own activity and cx_learn runs "
                "Oja on that TRACE, so the attractor is the leading PC of the "
                "TIME-SMOOTHED input covariance rather than the instantaneous "
                "one. That is the mechanism: same-orientation different-phase "
                "simple cells are ANTI-correlated at zero lag, so only a "
                "time-lagged covariance can bind them. ComplexParams.trace_delta"
                "=1.0 default => trace == cact, i.e. NO memory: the ablated, "
                "instantaneous-Oja arm. complex=0.0 default => the layer is "
                "inert and every result committed before rung 5 reproduces "
                "byte-identically. STATUS: the rung is NOT BUILT — the model's "
                "simple Units have no orientation-selective RESPONSE to pool "
                "(response OSI ~0.002 vs an ideal Gabor's 0.758 through the "
                "identical probe), because Oja on nonneg binary input yields "
                "strictly-positive weights and hence a DC-dominated response. "
                "The pooling rule itself is proven capable by a positive "
                "control on a hand-installed Gabor bank. See "
                "VISION_RUNG5_PREREG.md.",
))

REGISTRY.register(Seed(
    id="vision_ground", version="1.0.0",
    depends_on=("vision_waves",),
    installer=_installer_from_manifest("vision_ground"),
    description="THE BLIND SPOT — a GROUNDED retinal field, not a sample array. "
                "The optic disc (gsensed=0: no photoreceptors, no data) is FILLED "
                "FROM the surround by grounding, so the absence is invisible and a "
                "contour crossing it is bridged AS a contour. Pure seed rules "
                "reusing vision_lateral's LOCAL Neighbours/Filter/Count/Sum "
                "machinery (O(N) per run_rules sweep, NOT the O(N^2) "
                "apply_rule_once drive): gr_label marks a sensed contour by its "
                "own axis (constant along one axis, differs along the other — no "
                "magic number); gr_fill_contour_h/v CONTINUE a contour along its "
                "carried axis (structure, not blur); gr_fill_surface fills the "
                "rest from the surround mean; gr_ambig HOLDS OPEN a conflicting "
                "(two-continuation) surround (anti-confabulation); gr_interp is "
                "the interpolation CONTROL (mean of all neighbours, blurs and "
                "confabulates — graph DATA, not a Python fork). The blind-spot "
                "geometry is a STRUCTURAL construction parameter (the optic nerve "
                "must exit somewhere); the FILLING falls out and the confidence "
                "decay is RELATIVE to surround support (no gap-size constant). "
                "Ships INERT (ground=0, interp=0) so every committed result "
                "reproduces byte-identically (PROTOCOL 9). See "
                "VISION_GROUND_PREREG.md.",
))

REGISTRY.register(Seed(
    id="vision_stream", version="1.0.0",
    depends_on=(),
    installer=_installer_from_manifest("vision_stream"),
    description="THE STREAM — perception spends a BOUNDED budget, ordered by "
                "SALIENCE x SCALE. Vision is STREAMED, not delivered all-at-once: "
                "coarse-to-fine by scale (large low-frequency structure first; "
                "detail refines on the residual, order-N), allocated by salience "
                "(the bounded budget goes to the largest-residual region first), "
                "and PREEMPTIBLE (a maximally-salient 'spear' captures the budget "
                "and the rest degrades to the render — tunnel vision). ONE "
                "water-filling rule (stream_resolve_salient) over a residual-mass "
                "region field: the order is a pure Argmax, the budget is a Scene "
                "attr counted up as graph data, and coarse-first / "
                "budget-allocation / preemption all fall OUT with ZERO magic "
                "numbers (no preemption threshold — §13). NO new Rust (reuses "
                "Argmax/Plus/Neighbours/Filter + run_rules). Salience = the "
                "render-vs-input residual mass of the just-landed bidirectional "
                "loop; in-frame/integer only. Flag-gated on StreamParams.stream, "
                "OFF by default (§9). See VISION_STREAM_PREREG.md.",
))

REGISTRY.register(Seed(
    id="vision_colour", version="1.0.0",
    depends_on=(),
    installer=_installer_from_manifest("vision_colour"),
    description="COLOUR SALIENCE — colour is the pop-out channel for the "
                "EQUILUMINANT target, where luminance salience is ZERO. Two rules "
                "generalise the eye's surround-relative difference "
                "(vision_lateral's centre-surround) to the cone-opponent axes L−M "
                "and S−(L+M): cc_contrast computes the CONTINUOUS opponent-space "
                "distance of a cell from its surround (the salience magnitude) and "
                "the same difference on the achromatic axis (luminance salience); "
                "cc_salience combines them INTERACTIVELY (lsal + csal + lsal·csal, "
                "the parameter-free superadditive form — NOT strict addition) into "
                "Region.residual, which the unchanged vision_stream rule streams a "
                "bounded budget over. A near-equiluminant target (zero luminance "
                "contrast) with high cone-opponent contrast becomes salient via "
                "COLOUR and is streamed in, where a luminance-only salience MISSES "
                "it. NOT categorical colour (the identity sign is the named "
                "frontier). NO new Rust. In-frame colour coordinate is integer; "
                "only the contrast MAGNITUDE is continuous. Flag-gated on "
                "ColourParams.{salience,colour}, both OFF by default (§9). See "
                "VISION_COLOUR_PREREG.md.",
))

REGISTRY.register(Seed(
    id="vision_colour_identity", version="1.1.0",
    depends_on=(),
    installer=_installer_from_manifest("vision_colour_identity"),
    description="COLOUR IDENTITY — categorical colour as a MINTED, MDL-GATED SIGN "
                "over the opponent-colour VALUE. Downstream of colour-salience "
                "(WHERE to look) it answers WHAT COLOUR IT IS: it instantiates the "
                "sd loop's DYNAMIC-QUANTIZATION pattern (decode → recognize → mint → "
                "re-decode on codebook_epoch growth) for the 2-D integer "
                "opponent-colour subspace, NO new Rust. ci_opponent computes the "
                "integer opponent coordinate (crg=cL−cM, cby=cS−(cL+cM)); "
                "ci_mint_category MINTS a ColourCategory quantum where a colour "
                "value CLUSTERS and MDL COMPRESSES (Count(same exact colour) ≥ 3 = "
                "m_min, which FALLS OUT of d=2: a category pays iff m·d > d+m ⟺ m > "
                "d/(d−1) = 2 — no magic number); ci_assign writes each region's SIGN "
                "= its NEAREST minted quantum (Argmin by opponent Sqrt-distance) and "
                "re-decodes on growth. Categories EMERGE from the distribution via "
                "MDL, not hand-set (Witzel & Gegenfurtner). In-frame colour "
                "coordinate is INTEGER; the continuous lives only in the cross-frame "
                "assignment distance. NOT object colour re-ID / constancy / the "
                "'what' layer (the objecthood wall, out of scope). Flag-gated on "
                "ColourIdentityParams.identity, OFF by default (§9). See "
                "VISION_COLOUR_IDENTITY_PREREG.md. v1.1.0 adds the ACHROMATOPSIA "
                "LESION flag (ColourIdentityParams.achromatopsia, OFF by default = "
                "INTACT): armed, it suppresses ONLY ci_mint_category + ci_assign "
                "(the colour SIGN), leaving ci_opponent (the chromatic SIGNAL) and "
                "the vision_colour salience seed (chromatic structure) intact — the "
                "colour-STRUCTURE / colour-SIGN dissociation of cerebral "
                "achromatopsia. Default 0 ⇒ byte-identical to v1.0.0. See "
                "VISION_ACHROMATOPSIA_PREREG.md.",
))

REGISTRY.register(Seed(
    id="vision_category", version="1.0.0",
    depends_on=(),
    installer=_installer_from_manifest("vision_category"),
    description="CATEGORY-LEVEL RECOGNITION (FRONTIER T2) — a category as an "
                "MDL-minted AXIS-CODEBOOK REGION. Generalization to a KIND: a NEW "
                "instance never seen before is recognized as a member of a known "
                "category by its PROJECTION falling into a held category subspace (a "
                "chair you have never seen, known as a chair). Generalizes the "
                "colour-identity MDL mint from a POINT (an exact colour value) to a "
                "REGION (a MinOver/MaxOver box over object axes), the Chang–Tsao "
                "axis-code picture at the abstract-coordinate grain: an ObjItem is a "
                "projection split into a DISCRETE part-signature (d0,d1 — the "
                "grouping key, shared exactly by a kind) and CONTINUOUS proportion "
                "axes (v0,v1 — the within-category variation and generalization "
                "extent). cat_mint mints an ObjCategory where a kind's instances "
                "cluster (Count(same signature) ≥ 3 = m_min, FALLS OUT of d_disc=2) "
                "and MDL compresses, recording signature+exemplar+REGION box; "
                "cat_recognize recognizes by signature-match AND box-containment (the "
                "generalization readout AND the floor); cat_memorize is the "
                "exact-exemplar MEMORIZATION control. NO new Rust. In-frame "
                "coordinate INTEGER; the continuous lives only in the cross-frame "
                "containment comparison. UNSUPERVISED (no label read). BOUNDED: axes "
                "GIVEN not learned from pixels; axis-aligned BOX; interpolation "
                "within the box (extrapolation refused); discrete-similarity regime "
                "— NOT lighting/deformation/style, NOT the learned axis-codebook at "
                "natural-image scale (the named frontiers). Flag-gated on "
                "CategoryParams.identity, OFF by default (§9). See "
                "VISION_CATEGORY_PREREG.md.",
))

REGISTRY.register(Seed(
    id="vision_style", version="1.0.0",
    depends_on=("vision_category",),
    installer=_installer_from_manifest("vision_style"),
    description="STYLE AS A DISCOVERED DIMENSION (FRONTIER T5) — a style as a "
                "per-SOURCE COHERENT offset on a DISCOVERED continuous axis. "
                "Category (T2) captures the KIND (the discrete part-signature) and "
                "leaves the CONTINUOUS within-category variation unexplained; STYLE "
                "is the claim that this variation has structure — part of it is a "
                "coherent offset shared by everything ONE source makes and DIFFERING "
                "across sources, orthogonally to the kind. sty_project projects a "
                "recognized ObjItem into its own category's frame (dv = v − the "
                "MinOver box origin, the anchor that makes offsets comparable ACROSS "
                "KINDS; containment-gated, so T2's floor is inherited); "
                "sty_mint_a0/a1 — ONE RULE PER AXIS, both running on every source, so "
                "THE AXIS IS DISCOVERED — mint an ObjStyle where ≥ 3 of one source's "
                "offsets agree EXACTLY on that axis (m_min = 3 FALLS OUT of "
                "d_style = 2: a style is an (axis,delta) PAIR and membership is FREE "
                "because the source is observed); sty_recognize_a0/a1 recognize by "
                "offset, SOURCE-BLIND (no rule reads the produced edge), which makes "
                "discrimination a RISKED test; sty_memorize is the exact-raw-"
                "coordinate MEMORIZATION control. The Omniglot writer-dimension mint "
                "one level up ('the writer's physical limits become IMPLIED "
                "dimensions'). NO new Rust (Minus/MinOver/Neighbours + T2's Terms). "
                "Integer in-frame throughout; EXACT agreement, no radius/tolerance. "
                "BOUNDED: axes GIVEN not learned from pixels; a style is a CONSTANT "
                "offset on ONE axis; two sources sharing a delta ARE one style; the "
                "anchor is the box origin, so cross-kind coherence needs consistent "
                "per-kind coverage; chance-level false agreement exists. Flag-gated "
                "on StyleParams.style, OFF by default (§9). See "
                "VISION_STYLE_PREREG.md.",
))

REGISTRY.register(Seed(
    id="vision_mccollough", version="1.0.0",
    depends_on=(),
    installer=_installer_from_manifest("vision_mccollough"),
    description="McCOLLOUGH CONTINGENT AFTEREFFECT — the DECISIVE predictive-coding "
                "gate. After adapting to colour⊗orientation pairings (red-vertical, "
                "green-horizontal), an ACHROMATIC vertical grating is perceived "
                "greenish and a horizontal one pinkish: an orientation-CONTINGENT, "
                "OPPONENT, persistent, error-driven colour aftereffect. Mechanism "
                "(VISION_VENTRAL_GROUNDING.md): the aftereffect is the negative "
                "residual of an over-fit contingency prior — the system learns the "
                "joint E[colour|orientation] (mcc_learn: running MEAN colour given "
                "orientation, NO learning rate / NO magic number §13) and the percept "
                "is render-from-prior + opponent-residual (mcc_percept_pred: observed "
                "− prior, vision_lateral's predict-then-residual shape with the "
                "orientation prior as predictor). THE CRUX (§1.1): the predictive "
                "readout PRODUCES the aftereffect; the FEEDFORWARD control "
                "(mcc_percept_ff: direct colour read, no render-from-prior) does NOT "
                "— both are seeded, mcc_mode selects (ablation = graph data, §0). NO "
                "new Rust: reuses vision_colour's opponent coordinates (rg=L−M, "
                "by=S−(L+M)). VALIDATION gate for predictive/opponent joint "
                "colour-orientation coding, NOT a recognition capability; orientation "
                "is a stimulus feature (theta), not grown. Flag-gated on "
                "MccoughParams.mcc_enabled, OFF by default (§9). See "
                "VISION_MCCOLLOUGH_PREREG.md.",
))

REGISTRY.register(Seed(
    id="vision_border_ownership", version="1.0.0",
    depends_on=(),
    installer=_installer_from_manifest("vision_border_ownership"),
    description="BORDER-OWNERSHIP / PROTO-OBJECT — a local edge becomes a DIRECTED "
                "boundary that OWNS its figure, and a bounded, owned, PRE-IDENTITY "
                "region is minted as a ProtoObject (NO category — the near side of the "
                "objecthood 'what' wall). The Zhou/Friedman/von der Heydt 2000 "
                "signature: for an IDENTICAL local edge, ownership FLIPS with the GLOBAL "
                "figure (contextual, not local). All seed rules, NO new Rust: bo_bgflood "
                "computes SURROUNDEDNESS as a same-value reachability flood from the "
                "frame (bg=1 ground / bg=0 enclosed) — iterated by run_rules to a "
                "fixpoint, the grouping↔ownership RECURRENCE; bo_label labels same-value "
                "components; bo_mint_enclosed mints ONE ProtoObject per enclosed, closed, "
                "SINGLY-SURROUNDED figure (the closure test refuses iid speckle — no "
                "size threshold, closure FALLS OUT of 'a hole in one surface', §13); "
                "bo_mint_gestalt handles the ambiguous bipartition (figure = smaller "
                "region; tie held open); bo_own adds the directed owns_figure edge. "
                "In-frame integer coords; ownership is a RELATION; surroundedness is "
                "discrete reachability. NOT object identity/recognition (the named "
                "frontier). Flag-gated on BorderOwnParams.bown, OFF by default (§9). See "
                "VISION_BORDER_OWNERSHIP_PREREG.md.",
))

REGISTRY.register(Seed(
    id="vision_paint", version="1.0.0",
    depends_on=(),
    installer=_installer_from_manifest("vision_paint"),
    description="PAINT-FROM-SAMPLE — appearance as an order-k code SAMPLED from a "
                "contour-bounded region, PAINTED over the whole region as a cheap pass, "
                "and the RESIDUAL taken where the paint was wrong. The order k FALLS OUT "
                "of the residual (PROTOCOL §13): paint flat (k=1), and escalate to a "
                "gradient (k=2) only where the paint is REFUTED at the field's own "
                "alphabet resolution (|obs-paint| >= pquant/2 — a resolution, not a "
                "tolerance). Boundaries are STRICT LOCAL MAXIMA of |Δ| — an exact "
                "comparison with NO threshold and NO scale — so a uniform field and a "
                "LINEAR RAMP stay one region while a step and a Craik-O'Brien cusp split. "
                "Luminance is STRUCTURE (it defines the regions); appearance is a SIGN "
                "(it is sampled and painted). Pure seed rules (pt_delta / pt_block / "
                "pt_seed / pt_flood / pt_fit1 / pt_fit2 / pt_paint / pt_resid / "
                "pt_escalate / pt_verdict), NO new Rust. Flag PaintParams.paint OFF by "
                "default (§9). See VISION_PAINT_PREREG.md.",
))

REGISTRY.register(Seed(
    id="vision_crowding", version="1.0.0",
    depends_on=(),
    installer=_installer_from_manifest("vision_crowding"),
    description="CROWDING (T8) — eccentricity-scaled statistical pooling, validating the "
                "eye's foveation / eccentricity-decay prior (Bouma 1970). Recognition "
                "READS a pooled summary over a region whose radius R=bouma*ecc grows with "
                "eccentricity from the fixation (the ungrounded gaze origin): an isolated "
                "peripheral target survives (pool={target}), a flanked one is JUMBLED "
                "(pool=target+flankers, the mean ident mixes). A FOVEAL target is SPARED "
                "(R~0 at the fovea) even by the SAME flankers (the risked dissociation); "
                "critical spacing grows with eccentricity (Bouma's law; ENTAILED by "
                "R=bouma*ecc, reported not banked per PROTOCOL §13.1). Pure seed rules "
                "(cr_ecc / cr_pool) over the LOCAL co_item fold, NO new Rust. Flag "
                "CrowdParams.crowd OFF by default (§9). See VISION_CROWDING_PREREG.md.",
))

REGISTRY.register(Seed(
    id="vision_dorsal", version="1.0.0",
    depends_on=("vision_waves",),
    installer=_installer_from_manifest("vision_dorsal"),
    description="RUNG 3 — THE DORSAL/MOTION STREAM: direction selectivity. A "
                "DUnit population reads the SAME retina as rung 1's ventral "
                "Units, in PARALLEL (the verified research established 3-0 that "
                "the dorsal stream is EARLY and parallel — V1/MT co-earliest, "
                "marmoset layer-4 CB+ dense in both at E130 prenatal, a "
                "retina->inferior-pulvinar->MT route BYPASSING V1 — not a rung "
                "above V1). dv_unit_activate is a DELAY-LINE COINCIDENCE "
                "DETECTOR: each DSynapse carries its own conduction delay and "
                "fires only when its pre cell burst exactly that many steps ago, "
                "so order becomes readable — the ventral rule's SHARED window is "
                "order-blind by construction (a->b and b->a give the identical "
                "in-window burst set). Delays are UNIFORM RANDOM adapter entropy, "
                "never a tuned gradient; dv_oja_learn has to grow any direction "
                "preference from the input's own motion statistics. Tests the "
                "research's explicit differential warning: unlike orientation, "
                "direction is ABSENT at eye opening and REQUIRES experience "
                "(Li 2006). Gated OFF by DorsalParams.dorsal=0 (default).",
))

REGISTRY.register(Seed(
    id="vision_eye", version="1.0.0",
    depends_on=(),
    installer=_installer_from_manifest("vision_eye"),
    description="THE EYE'S CALIBRATION FRONT END — the layer that establishes "
                "the REFERENCE everything later is defined against. Three "
                "mechanisms, each an arm selected by DATA on EyeParams: (1) a "
                "LOG RECEPTOR (Weber-Fechner) — `logr`, and the frame fix for "
                "this ladder, since in log space an illumination change x k is "
                "an ADDITIVE constant log k rather than a gain; (2) an ADAPTIVE "
                "REFERENCE theta (GCAL Eqs. 7-8, beta=0.991/lam=0.01/mu=0.024) "
                "placed on the ACTIVATION FUNCTION, OUTSIDE the learning rule "
                "where it cannot flip dw's sign — `theta_mode` also ships the "
                "BCM (theta-INSIDE) placement so the comparison that annihilated "
                "this tree to 0.004 is measured, not asserted; (3) ENGBERT's "
                "self-avoiding-walk fixational drift (2011 PNAS 108:E765) — a "
                "trail the gaze avoids plus a quadratic potential, in the "
                "STOCHASTIC variant (an adapter-supplied IID Gumbel draw makes "
                "the argmin an exact Boltzmann sample), because the "
                "deterministic 4-connected argmin is a cardinal-axis artifact. "
                "The adapter supplies only unstructured entropy + a clock. "
                "EyeParams.eye=0 default — not one rule fires, so every result "
                "committed before this seed reproduces byte-identically.",
))

REGISTRY.register(Seed(
    id="vision_growth", version="1.0.0",
    depends_on=("sensory_convolution", "vision_floor"),
    installer=_installer_from_manifest("vision_growth"),
    description="KERNEL GROWTH (Stage 2, L0) — the agent grows its OWN "
                "receptive fields instead of selecting from the designed pool: "
                "vg_mint_kernel_from_patch mints a Kernel whose weights ARE a "
                "real unexplained image patch (scale-aware residual test), and "
                "vg_learn_kernel_oja runs Oja's rule (local Hebbian with self-"
                "normalisation) winner-take-all against the image stream, "
                "inside the run_rules fixpoint. No new Rust: the update "
                "factors into two MapList scalar-x-vector maps + VecAdd. "
                "Whether center-surround / oriented structure actually emerges "
                "is then an open MEASUREMENT over real data, not a planted "
                "assumption.",
))

REGISTRY.register(Seed(
    id="curiosity_agent", version="1.0.0",
    depends_on=("decision_core", "learning_core", "perception_core",
                "epistemics_core", "motor_core", "experimentation_core",
                "goal_construction", "self_monitoring", "memory_core",
                "reflex_core", "theorem_core"),
    installer=None,
    description="The migrated CuriousAgent's genuine cognition as graph "
                "data: goal-pressure + action-choice (decision_core), "
                "causal inference + implied-rule induction (learning_core), "
                "observe recognitions + aesthetic goal-prior "
                "(perception_core), and the epistemic/ontological judgment "
                "predicates (epistemics_core). A world adapter requests this "
                "one seed to boot the whole curiosity agent — no Python "
                "agent class. See docs/migration_ledger.md.",
))


REGISTRY.register(Seed(
    id="vision_agnosia", version="1.0.0",
    depends_on=(),
    installer=_installer_from_manifest("vision_agnosia"),
    description="APPERCEPTIVE / ASSOCIATIVE AGNOSIA (FRONTIER T9) — the two "
                "LESION FLAGS for the FORM<->RECOGNITION seam, and nothing "
                "else. Carries ONE node, AgnosiaParams{associative, "
                "apperceptive}, both 0.0 = INTACT by default (PROTOCOL §9). "
                "The guards that READ them live in the rules they lesion: "
                "`associative` guards ONLY shape_decode_loop's sd_recognize / "
                "sd_recognize_transformed / sd_recognize_dim (the sole writers "
                "of covered_by — the IDENTITY assignment), leaving sd_decode / "
                "TransformDecode / sd_mint_quantum live; `apperceptive` guards "
                "ONLY vision_ground's gr_fill (percept COMPLETION), leaving "
                "gr_label live. Both guards are absence-tolerant "
                "(Count(Filter(NodesOfType(AgnosiaParams), …)) < 1), so a graph "
                "that never loads this seed is intact. See "
                "VISION_AGNOSIA_PREREG.md.",
))


__all__ = []  # pure side-effects — registrations happen at import

REGISTRY.register(Seed(
    id="vision_lighting", version="1.0.0",
    depends_on=(),
    installer=_installer_from_manifest("vision_lighting"),
    description="LIGHTING / APPEARANCE INVARIANCE (FRONTIER T3) — the illuminant as "
                "a low-D CROSS-FRAME map, DISCOVERED and FACTORED, with recognition "
                "invariant to what it leaves fixed. An ObjSurface carries integer "
                "cones (reflectance × illuminant): reflectance is the stable IN-FRAME "
                "property, the illuminant a diagonal (von Kries) cross-frame map. "
                "li_frame_stats reads the frame's OWN anchor (max) + sum; li_inclass "
                "DISCOVERS in-class-ness by an order-statistic consistency test "
                "needing no surface correspondence and REFUSES a spatially-varying "
                "change; li_mint MDL-mints a SurfaceIdentity (m_min=2 falls out of "
                "d=3) carrying the prototype AND its frame's anchor; li_recognize "
                "matches by ANCHOR-RELATIVE reflectance via exact integer "
                "cross-multiplication; li_raw_recognize is the no-discounting RAW "
                "BASELINE control. NO new Rust, NO magic number. BOUNDED to the "
                "diagonal illuminant class — multi-illuminant / shadows / "
                "spatially-varying light are NOT solved, only refused (the named "
                "frontier). Flag-gated on LightingParams.lighting, OFF by default "
                "⇒ byte-identical, seed inert. See VISION_LIGHTING_PREREG.md.",
))

REGISTRY.register(Seed(
    id="vision_lighting_l1", version="1.0.0",
    depends_on=("vision_lighting",),
    installer=_installer_from_manifest("vision_lighting_l1"),
    description="ADVANCED LIGHTING RUNG L1 — REAL-VALUED ILLUMINANT GAINS. T3 "
                "crossed lighting-invariance for the EXACT-RENDERING "
                "(integer-ratio) diagonal class and REFUSED real gains, NAMING the "
                "resolution-derived identifiability bound; L1 BUILDS it by "
                "continuous pose's mechanism transposed from rotation to gain — the "
                "gain is a CONTINUOUS parameter in the CROSS-FRAME map (the "
                "surfaces' cones stay integers), the held prototype is RENDERED at "
                "it onto the stepped lattice, and recognition is decided by a "
                "CONTINUOUS VERDICT (L∞ residual) over a proposal from the DISCRETE "
                "codebook T3's integer li_mint minted: bins propose, continuous "
                "decides. l1_frame_stats (own anchor/sum/min/count, hub-scoped, "
                "L1-only attr namespace so T3's arm reads from the SAME graph); "
                "l1_inclass (T3's exact order-statistic equality replaced by the "
                "ROUNDING ENVELOPE THE LATTICE IMPLIES — a sum clause and a tighter "
                "min clause, both derived — minting the REAL gain); l1_recognize "
                "(admit iff the best rendered candidate is within ONE LATTICE "
                "STEP); l1_refuse (a refusal as a POSITIVE datum, §1.1). NO new "
                "Rust. NO magic number: the bound falls out as ½ + ½·(r/a) with "
                "r/a ≤ 1 BY THE DEFINITION OF THE ANCHOR AS THE MAXIMUM — the "
                "analogue of continuous pose's √2/2 — so it is pinned to "
                "OBSERVATIONAL RESOLUTION and MUST fail at a dimming gain where "
                "distinct materials render onto the same lattice points. BOUNDED to "
                "the GLOBAL diagonal class: spatially-varying illuminant / Retinex, "
                "global illuminant inference, shadow-vs-reflectance edges and "
                "multi-illuminant scenes are NOT solved, only refused. Flag-gated "
                "on LightingL1Params.lighting_l1, OFF by default ⇒ byte-identical, "
                "seed inert; the flag is read ABSENCE-TOLERANTLY via "
                "MaxOver(default 0), never PickUnique. See "
                "VISION_LIGHTING_L1_PREREG.md.",
))

REGISTRY.register(Seed(
    id="vision_lighting_l2", version="1.0.0",
    depends_on=("vision_lighting",),
    installer=_installer_from_manifest("vision_lighting_l2"),
    description="ADVANCED LIGHTING RUNG L2 — SPATIALLY-VARYING ILLUMINANT "
                "(RETINEX). T3 crossed the exact-integer-ratio GLOBAL diagonal "
                "illuminant and L1 widened it to REAL-VALUED GLOBAL gains; BOTH "
                "REFUSE a spatially-varying scene as out-of-class (0/20, twice "
                "measured). L2 makes that case ADMISSIBLE by Land's Retinex first "
                "step — reflectance from SPATIAL RATIOS of neighbouring cone "
                "activity. The ANCHOR IS LOCALIZED: l2_locale_stats reads a "
                "per-channel max/min/count over the LOCALE's own membership "
                "(hub-scoped Neighbours, never a global grab); l2_pair mints the "
                "test↔reference locale pairing AS A RULE (an Eq(pos,pos) join "
                "across compares_to — the adapter draws no cross-frame edge); "
                "l2_inclass admits PER LOCALE under L1's inherited MIN-clause "
                "rounding envelope, which is exactly what a frame-level test "
                "cannot do; l2_recognize renders the held prototype at the LOCAL "
                "illuminant estimate a_loc/pa_loc and admits within ONE LATTICE "
                "STEP, so the field cancels LOCALLY with NO global estimate and "
                "NO path integration; l2_refuse makes a refusal a POSITIVE datum; "
                "l2_recognize_globalanchor is the ABLATION CONTROL (spatial-ratio "
                "step removed, everything else identical, always computed on the "
                "SAME graph); l2_ncand records the candidate count INSIDE the "
                "bound so the bound's discriminativeness is reported rather than "
                "assumed (rung L1b's lesson). NO new Rust, NO new constant — the "
                "bound is L1's own falls-out ONE LATTICE STEP, valid at locale "
                "grain because the locale contains its own centre, and 'slowly "
                "varying' itself falls out as the lattice step over the frame's "
                "own measured dynamic range. BOUNDED: a SLOWLY-VARYING SINGLE "
                "field via LOCAL ratios — global illuminant inference (L3), "
                "shadow-vs-reflectance ATTRIBUTION (L4) and multi-illuminant "
                "scenes are NOT solved; reflectance GIVEN at the cone-triple "
                "grain; adjacency GIVEN not grown; locale-grain spatial "
                "registration GIVEN (stronger than T3/L1's frame-level "
                "assumption) while IDENTITY correspondence is NOT. Flag-gated on "
                "LightingL2Params.lighting_l2, OFF by default ⇒ byte-identical, "
                "seed inert; read ABSENCE-TOLERANTLY via MaxOver(default 0), "
                "never PickUnique. See VISION_LIGHTING_L2_PREREG.md.",
))

REGISTRY.register(Seed(
    id="vision_lighting_l3", version="1.0.0",
    depends_on=("vision_lighting_l2",),
    installer=_installer_from_manifest("vision_lighting_l3"),
    description="ADVANCED LIGHTING RUNG L3 — GLOBAL ILLUMINANT INFERENCE. L2 "
                "crossed the spatially-varying illuminant by LOCALIZING the "
                "anchor, and its noise floor FAILED its own pre-registered rule "
                "at 13/1300 (1.0%) with an ARCHITECTURAL diagnosis: 12 of 13 "
                "leaks are surfaces that ARE their own locale's MAXIMUM, matched "
                "at residual EXACTLY 0.0, because ĝ = a_loc/ra_loc renders the "
                "reference locale's maximum prototype onto a local maximum "
                "identically — the WHITE-PATCH (ANCHOR) ASSUMPTION, localized. "
                "L3 CORROBORATES THE ANCHOR, which L2 named as a necessarily "
                "GLOBAL statement. l3_ghat makes each locale's illuminant "
                "estimate explicit (a CROSS-FRAME map, so a real value is "
                "correct); l3_pool forms ONE SCENE-LEVEL estimate by POOLING "
                "every locale's — the CHEBYSHEV CENTER, the local estimate MOST "
                "CORROBORATED BY THE WHOLE SCENE (Argmin over locales of the "
                "MaxOver L∞ disagreement with every other locale), robust where "
                "a mean would be dragged by the very outlier it must catch, and "
                "the V4/PIT step over L2's V1/V2 local contrast; l3_corroborate "
                "requires each locale's estimate to agree with the scene's "
                "within an envelope that FALLS OUT of L2's own per-adjacency "
                "drift budget scaled by the locale COUNT READ FROM THE DATA; "
                "l3_recognize is L2's verdict AND corroboration — term for term "
                "l2_recognize plus ONE conjunct, so L3 can only SUBTRACT claims "
                "and L2's own arm on the SAME graph IS the exact pooling "
                "ABLATION; l3_refuse_uncorroborated / l3_refuse_bound make "
                "refusal a POSITIVE datum SPLIT BY REASON; and "
                "l3_recognize_lesioned is THE V4 DISSOCIATION — the constancy "
                "stage removed entirely (ĝ ≡ 1), always computed on the same "
                "graph, so that colour DISCRIMINATION surviving while CONSTANCY "
                "is ABOLISHED is a MEASUREMENT. NO new Rust, NO new constant — "
                "literal set {0.0, 0.5, 1.0, 1.0e9}, identical to L2's; the "
                "bound is L1's own falls-out ONE LATTICE STEP inherited through "
                "L2. BOUNDED: ONE scene-level illuminant estimate with anchor "
                "corroboration — shadow-vs-reflectance EDGE ATTRIBUTION (L4) and "
                "MULTI-ILLUMINANT scenes are NOT solved; reflectance GIVEN at "
                "the cone-triple grain; locale-grain registration and adjacency "
                "GIVEN, not grown; IDENTITY correspondence NOT given. Flag-gated "
                "on LightingL3Params.lighting_l3, OFF by default ⇒ "
                "byte-identical, seed inert; read ABSENCE-TOLERANTLY via "
                "MaxOver(default 0), never PickUnique. See "
                "VISION_LIGHTING_L3_PREREG.md.",
))

REGISTRY.register(Seed(
    id="vision_lighting_l3b", version="1.0.0",
    depends_on=("vision_lighting_l3",),
    installer=_installer_from_manifest("vision_lighting_l3b"),
    description="ADVANCED LIGHTING RUNG L3b — THE ANCHOR OF THE ANCHOR. L3's "
                "pool is a CHEBYSHEV CENTRE (a MEDOID), so Ĝ IS some locale's "
                "own ĝ, that locale's deviation is EXACTLY 0, and it "
                "corroborates UNCONDITIONALLY — all five of L3's surviving "
                "leaks sat exactly there, so the white-patch assumption had "
                "been PUSHED UP ONE LEVEL, not eliminated. This rung audits SIX "
                "candidate certifiers for Ĝ and finds exactly ONE that is "
                "neither CIRCULAR (the Chebyshev centre; the per-channel "
                "MEDIAN, measurably still self-membered on every coherent "
                "scene) nor EXTERNAL (temporal persistence assumes "
                "stationarity; the dynamic-range ceiling is a white patch under "
                "another name, already killed as NON-LOCAL by the k=1 rung; "
                "cone-channel achromaticity assumes an achromatic illuminant "
                "and is UNSOUND at the substrate's own landed chromatic gain): "
                "LEAVE-ONE-OUT MUTUAL CORROBORATION. l3b_pool_loo forms, PER "
                "LOCALE, the Chebyshev centre of EVERY OTHER locale's estimate "
                "(exclusion Not(Eq(j,loc)), Eq comparing Value::Node by id), so "
                "a locale can NEVER be its own certifier — self-membership is "
                "broken BY CONSTRUCTION; l3b_corroborate applies L3's OWN "
                "envelope UNCHANGED against that pool; l3b_recognize is "
                "l3_recognize with the corroboration conjunct SWAPPED and "
                "nothing else, so L3's own l3_* arm on the SAME graph IS the "
                "exact ABLATION and L3b can only SUBTRACT claims; l3b_dev "
                "writes BOTH deviations as floats so the circularity and "
                "leave-one-out's own TWIN-LOCALE residual are EXHIBITED ON THE "
                "GRAPH rather than asserted; l3b_refuse_* make refusal a "
                "POSITIVE datum SPLIT BY REASON. WHAT IT DOES NOT DO: it "
                "removes every locale's SELF-certification but does NOT certify "
                "the SET — a scene whose locales are all wrong IN THE SAME WAY "
                "corroborates unanimously (measured by scaling reflectances by "
                "κ: 13/13 corroboration with a recovered Ĝ wrong by exactly κ). "
                "CONSTANCY ON THIS SUBSTRATE IS ANCHOR-RELATIVE AND THE ANCHOR "
                "IS A DECLARED CHOICE, NOT A MEASUREMENT. NO new Rust and NO "
                "new constant (literal set {0.0, 0.5, 1.0, 1.0e9}, identical to "
                "L2's and L3's). T3, L1, L1b, L2 and L3 are NOT modified. "
                "BOUNDED: MULTI-ILLUMINANT scenes remain unsolved; reflectance "
                "GIVEN at abstract cone-triple grain; locale-grain registration "
                "and adjacency GIVEN, not grown; IDENTITY correspondence NOT "
                "given. Flag-gated on LightingL3bParams.lighting_l3b, OFF by "
                "default ⇒ byte-identical, seed inert; read ABSENCE-TOLERANTLY "
                "via MaxOver(default 0), never PickUnique. See "
                "VISION_LIGHTING_L3B_PREREG.md.",
))

REGISTRY.register(Seed(
    id="vision_lighting_l4", version="1.0.0",
    installer=_installer_from_manifest("vision_lighting_l4"),
    description="ADVANCED LIGHTING RUNG L4 — SHADOW vs REFLECTANCE EDGES. L2 "
                "measured that a shadow EDGE is NOT refused by a LOCAL "
                "mechanism (10/12 correct, 0 false, only the two straddling "
                "locales refused — a discontinuity is out-of-class for a GLOBAL "
                "mechanism and IN-class for a LOCAL one), but that identities "
                "are recovered on both sides WITHOUT THE SYSTEM EVER KNOWING AN "
                "EDGE EXISTS. L4 closes exactly that gap: it ATTRIBUTES the "
                "edge. An ILLUMINANT edge scales every channel by ONE factor and "
                "so PRESERVES chromatic ratios; a REFLECTANCE edge changes the "
                "ratios themselves. THE PREDICATE IS L2'S OWN _slowvar_clause "
                "WITH THE QUANTIFIER MOVED FROM SPACE TO WAVELENGTH — the same "
                "cross-multiplied ratio-agreement test with the index pair "
                "(locale,locale) replaced by (channel,channel), so no ratio is "
                "ever divided into a float. l4_classify_illuminant / "
                "_reflectance PARTITION the real edges (horizontal verdict on "
                "the LEFT cell, vertical on the UPPER — unambiguous, one right "
                "and one lower neighbour each); l4_flat makes 'not an edge' a "
                "POSITIVE datum so a silent classifier cannot score a flawless "
                "floor; l4_flood is bo_label's min-flood with Eq(val,val) "
                "replaced by the ratio-preserving predicate, so cells joined "
                "through illuminant edges share a component and cells across a "
                "material boundary do not — which is how a SHADOW BOUNDARY IS "
                "PREVENTED FROM BECOMING AN OBJECT BOUNDARY in the UNMODIFIED "
                "vision_border_ownership seed. L4's ASSUMPTIONS ARE STRICTLY "
                "WEAKER THAN L2's AND L3's: no reference frame, no compares_to, "
                "no SurfaceIdentity codebook, no locale pairing, no spatial "
                "registration, no per-locale gain, no pooled scene estimate — it "
                "sits BESIDE them, not on top. NO new Rust, NO new constant — "
                "literal set {0.0, 0.5, 1.0}, a STRICT SUBSET of L2's and L3's; "
                "the envelope is the four half-step roundings the four "
                "observations entering the cross-product carry, and the edge "
                "threshold is L1's own falls-out ONE LATTICE STEP. BOUNDED: "
                "SINGLE-ILLUMINANT, NEUTRAL-SHADOW attribution. CHROMATIC "
                "shadows are NOT handled and PROPORTIONAL materials are "
                "IRREDUCIBLY ambiguous — both MEASURED as predicted failures, "
                "not hidden. MULTI-ILLUMINANT unsolved; L3's 'anchor of the "
                "anchor' untouched (L4 uses no anchor); reflectance GIVEN at the "
                "cone-triple grain; adjacency GIVEN not grown; the "
                "ratio-preserving relation is NOT transitive and l4_flood takes "
                "its transitive closure. L4 CLASSIFIES EDGES; IT DOES NOT "
                "RECOVER REFLECTANCE — no L2/L3 arm consumes an L4 attribute. "
                "Flag-gated on LightingL4Params.lighting_l4, OFF by default "
                "(§9 — default 0 ⇒ byte-identical, seed inert), read "
                "ABSENCE-TOLERANTLY via MaxOver(default 0), never PickUnique. "
                "See VISION_LIGHTING_L4_PREREG.md.",
))

REGISTRY.register(Seed(
    id="vision_uniqueness", version="1.0.0",
    depends_on=("vision_lighting_l1",),
    installer=_installer_from_manifest("vision_uniqueness"),
    description="RUNG L1b — THE UNIQUENESS GATE for the SILENT-ARGMIN HAZARD. L1 "
                "measured that below the resolution floor recognition returns a "
                "CONFIDENT WRONG IDENTITY (refused=0 in every failing row) while ≥2 "
                "candidates lie INSIDE the verdict bound — the ambiguity is VISIBLE "
                "IN THE GRAPH and Argmin resolves it SILENTLY (T3's PickUnique "
                "lesson one level up, in the continuous verdict). This seed makes "
                "the verdict's UNIQUENESS a gate: uq_admit fires iff EXACTLY ONE "
                "candidate is within the bound (identity = L1's own Argmin winner, "
                "term-for-term, so an admitted row is byte-identical to L1's "
                "answer); uq_refuse_ambiguous fires iff ≥2 are, recording the tied "
                "count so a refusal is a POSITIVE datum (§1.1). PURE COMPOSITION — "
                "Count/Filter/Lte/Gte/Neighbours, NO new Rust — and NO NEW CONSTANT: "
                "the ONE-LATTICE-STEP bound is L1's own falls-out number, inherited "
                "unchanged, and the count 2 is the definition of 'more than one', "
                "not a threshold. The residual is EXTRACTED VERBATIM from "
                "l1_recognize, so the gate counts EXACTLY the candidates the "
                "recognizer would admit. It fires only where L1 already claimed, so "
                "it can ONLY turn a claim into a refusal — it NEVER widens an "
                "invariance class (§8). Writes only uq_* (never l1_*), which keeps "
                "both verdicts readable from ONE graph AND makes the fixpoint "
                "terminate (§2.1). BOUNDED: built on L1 only — the audit measured "
                "that the count-within-bound predicate does NOT transfer to "
                "continuous pose, whose bound is near-vacuous (≥2 in bound in 63/63 "
                "trials in BOTH the aliasing and the clean regime); the MARGIN "
                "instrument that would need is NAMED, NOT BUILT (§5). Flag-gated on "
                "UniquenessParams.uniqueness, OFF by default ⇒ byte-identical, seed "
                "inert; the flag is read ABSENCE-TOLERANTLY via MaxOver(default 0), "
                "never PickUnique. See VISION_UNIQUENESS_PREREG.md.",
))

REGISTRY.register(Seed(
    id="vision_margin", version="1.0.0",
    depends_on=("continuous_pose",),
    installer=_installer_from_manifest("vision_margin"),
    description="RUNG L1c — THE DERIVED ADMISSION BOUND, and the T1 RECORD "
                "CORRECTION. L1b measured that T1's sqrt(2)/2 verdict bound is "
                "NEAR-VACUOUS (≥2 candidates inside it in 63/63 of T1's OWN "
                "headline regime, median 4), so T1's clean 63/63 rests entirely on "
                "the Argmin RANKING and the bound discriminates nothing — §13.2's "
                "'works' vs 'is load-bearing' applied to a threshold. L1b named a "
                "MARGIN instrument and refused to build it, because a threshold "
                "separating the measured 0.025 from the measured 0.180 is a magic "
                "number chosen after seeing both (§13). THIS RUNG'S PART A IS A "
                "DERIVED NEGATIVE ON THE MARGIN: all six margin candidates are "
                "REJECTED BY MEASUREMENT — sqrt(2)/2-as-margin refuses 63/63 at "
                "every resolution; any ABSOLUTE margin fails because the margin "
                "SCALES with resolution; exact ties are 0/63 (vacuous); the "
                "angle-grid resolution jitter is two orders of magnitude below the "
                "margins it would separate; the codebook PACKING RADIUS (the colour "
                "rung's own winner, transplanted) is UNSOUND at the aliasing floor "
                "and near-vacuous above it, because T1's lattice-rounding residual "
                "EXCEEDS its packing radius; and a scale-free RATIO separates only "
                "via a threshold chosen after seeing both regimes. WHAT DOES FALL "
                "OUT IS A BOUND, NOT A MARGIN: eta_c, the codebook's OWN "
                "self-rounding residual — the largest residual a TRUE instance of c "
                "can produce, computed from codebook × lattice × the agent's own "
                "cp_angles ALONE, never from the test observations. sqrt(2)/2 is "
                "merely the WORST-CASE PER-POINT displacement; eta is the MHD "
                "rounding actually induces, per-shape and resolution-adapted. "
                "Inside it, L1b's count predicate transfers UNCHANGED (mg_admit iff "
                "exactly one candidate, mg_ambiguous iff ≥2, mg_none iff none). "
                "PURE COMPOSITION — Count/Filter/Lte/MaxOver/MinOver/PointSetDist/"
                "Rotate/MapList, NO new Rust, NO new constant (the bound is "
                "COMPUTED; the literal set is {0.0,0.5,1.0,2.0}), and NO Times "
                "anywhere. The residual and the winner are EXTRACTED VERBATIM from "
                "cp_recognize, so an admitted row is byte-identical to T1's answer. "
                "eta_c <= sqrt(2)/2 by construction and the rules fire only where "
                "T1 already claimed, so this can ONLY turn a claim into a refusal — "
                "it NEVER widens an invariance class (§8). Writes only mg_* (never "
                "cp_*/status/covered_by), which keeps both verdicts readable from "
                "ONE graph AND makes the fixpoint terminate (§2.1). Flag-gated on "
                "MarginParams.margin, OFF by default ⇒ byte-identical, seed inert; "
                "read ABSENCE-TOLERANTLY via MaxOver(default 0), never PickUnique. "
                "See VISION_MARGIN_PREREG.md.",
))

REGISTRY.register(Seed(
    id="fallback_vocabulary", version="1.0.0",
    depends_on=(),
    installer=_installer_from_manifest("fallback_vocabulary"),
    description="THE VOCABULARY THAT MAKES DEGRADED OPERATION SAYABLE. "
                "VISION_REDUNDANCY_RESULTS.md Arm 4 measured observability 0/2 "
                "with the marker inventory EMPTY in all 26 probe runs INCLUDING "
                "BASELINE — 'the finding is not that the markers didn't fire, it "
                "is that there are none to fire'. Ablating vision_lateral drives "
                "channels_on 51.976 → 0.000 and every learned gain to exactly "
                "0.0, leaving no trace in graph state. This seed is the missing "
                "trace, and it exists for a structural reason rather than an "
                "instrumental one: A LAYER IS ONLY A LAYER IF IT HAS DEFINED "
                "BEHAVIOUR IN THE ABSENCE OF ITS NEIGHBOURS AND DECLARES IT — "
                "without a declared fallback, 'layer B is independent of A' "
                "cannot be told apart from 'nothing in B was running', which is "
                "exactly the vacuous result Arm 5 hit. Three rules split the one "
                "reading an ablation harness sees ('no test loss') into the three "
                "it conflates: silent (progress==0 — INERT BECAUSE DEAD, 38 such "
                "rules in the audit), degraded (progress>0 WITH a DefaultedRead — "
                "ran on values nobody wrote, the signature of vision_waves' "
                "non-monotone curve), and healthy (progress>0, nothing defaulted "
                "— the only state in which 'no effect' means genuine "
                "independence). The engine supplies the FACTS (rule progress; "
                "reads that missed); THESE RULES MAKE THE DECISION — no Python "
                "conditional over graph state is involved. Ships INERT: the seed "
                "installs one doc node and no RuleActivity, so nothing matches "
                "until a reader explicitly mints a report (§9 byte-identity). "
                "See VISION_FALLBACK_VOCAB_PREREG.md.",
))

REGISTRY.register(Seed(
    id="vision_identity_seam", version="1.0.0",
    depends_on=("shape_decode_loop",),
    installer=_installer_from_manifest("vision_identity_seam"),
    description="THE PERCEPT->IDENTITY SEAM, arm B (seeds 72000-72999, "
                "VISION_IDENTITY_SEAM_PREREG.md) — a region recognised in one "
                "frame is decided to be THE SAME HELD IDENTITY in the next, or "
                "is minted as a new one and the codebook grows. Keeps the sd "
                "loop's topology (decode -> gate -> mint -> grow -> epoch -> "
                "re-decode) and replaces exactly ONE thing: the recognition "
                "verdict. The stock loop accepts an observation as already-held "
                "when Count(residual)==0 over a COMPOSITIONAL decode, which a "
                "large enough parts library satisfies for anything; arm B "
                "accepts it when its best NCC score strictly EXCEEDS the score "
                "the same comparator achieves on calibration noise against the "
                "SAME codebook, re-armed on every codebook_epoch bump. The "
                "floor is MEASURED, never chosen — no numeric threshold appears "
                "in the seed (section 13), and no new Rust or Term is added. "
                "seam=0.0 default => inert; not in any default boot set.",
))

REGISTRY.register(Seed(
    id="vision_motion_group", version="1.0.0",
    depends_on=(),
    installer=_installer_from_manifest("vision_motion_group"),
    description="COMMON MOTION AS THE OBJECT CRITERION — a thing is what MOVES "
                "TOGETHER (Spelke's cohesion/continuity/contact; common fate "
                "before boundary or appearance). Static-form criteria — "
                "enclosure, border ownership — fragment a scene into however "
                "many enclosed regions it happens to contain; common fate "
                "should yield FEW and LARGE. Motion is carried as a VECTOR "
                "MATRIX (one `v = [vy, vx]` attribute per MCell) and every "
                "question is a direct `Magnitude(VecSub(..))` read, never a "
                "coherence statistic rebuilt from per-component scalars. The "
                "agreement tolerance FALLS OUT of the field's own adjacent-pair "
                "dispersion (Otsu over the observed values, precedent ca_otsu) "
                "and the reference frame FALLS OUT as the largest group, so no "
                "motion constant appears in the seed (section 13). "
                "marm=0.0 default => inert; not in any default boot set. "
                "VISION_MOTION_OBJECTS_PREREG.md.",
))

REGISTRY.register(Seed(
    id="parallax_efference", version="1.0.0",
    depends_on=("vision_motion_group",),
    installer=_installer_from_manifest("parallax_efference"),
    description="EFFERENCE-COPY reference frame for common-fate grouping — the "
                "eye moves ITSELF by a KNOWN shift and subtracts the reference/"
                "fixation plane's predicted field, so the fixated surface reads "
                "STATIONARY (space constancy) and parallax carves the residual "
                "into surfaces. Replaces mo_dominant's ESTIMATED reference (the "
                "largest group's velocity) with the SUPPLIED efference copy "
                "(field.efference_v). ONE rule (pe_efference_ref), gated by "
                "MotionParams.mo_efference, DEFAULT OFF => byte-identical to "
                "vision_motion_group (section 9); no new constant (section 13); "
                "efference_v is an adapter input, never estimated. "
                "VISION_PARALLAX_PREREG.md.",
))

REGISTRY.register(Seed(
    id="fovea_salience_bridge", version="1.0.0",
    depends_on=(),
    installer=_installer_from_manifest("fovea_salience_bridge"),
    description="Graph-native Gamma-admissible fovea candidate vocabulary "
                "and exact-tie-refusing salience selection.",
))

REGISTRY.register(Seed(
    id="retinal_attention_graph", version="1.0.0",
    depends_on=("fovea_salience_bridge",),
    installer=_installer_from_manifest("retinal_attention_graph"),
    description="Projects current retinal salience through the graph-native "
                "fovea resolver into a current allocentric attention verdict.",
))

REGISTRY.register(Seed(
    id="held_prediction_attention", version="1.0.0",
    depends_on=("retinal_attention_graph",),
    installer=_installer_from_manifest("held_prediction_attention"),
    description="Graph-native attention over held photometric prediction "
                "residuals, with explicit unique-selection refusal.",
))

REGISTRY.register(Seed(
    id="retinal_focus_control", version="1.0.0",
    depends_on=("held_prediction_attention",),
    installer=_installer_from_manifest("retinal_focus_control"),
    description="Publishes the current uniquely selected retinal focus as "
                "epoch-scoped graph state for mechanical sensor control.",
))

REGISTRY.register(Seed(
    id="optic_flow_spatial_grounding", version="1.0.0",
    depends_on=(),
    installer=_installer_from_manifest("optic_flow_spatial_grounding"),
    description="Default-off graph-native spatial grounding of photon-eye "
                "motion into uncertainty-bearing world-relative evidence.",
))

REGISTRY.register(Seed(
    id="saccade_motor_control", version="1.0.0",
    depends_on=("retinal_focus_control",),
    installer=_installer_from_manifest("saccade_motor_control"),
    description="Default-off graph-native eye-motor command apparatus: "
                "tie-refusing presaccadic selection, explicit stale-command "
                "rejection, efference copy, and later sensor-confirmed Fixation. "
                "The authoritative adapter seam is a single set of eye_motor_* "
                "Agent scalars; historical command nodes require no host ranking.",
))

REGISTRY.register(Seed(
    id="transsaccadic_feature_memory", version="1.0.0",
    depends_on=("saccade_motor_control", "optic_flow_spatial_grounding"),
    installer=_installer_from_manifest("transsaccadic_feature_memory"),
    description="Default-off graph-native transsaccadic VisualTile memory. "
                "Confirmed fixations update world-relative feature tiles only "
                "from same-epoch uncertainty-bounded optic range evidence; "
                "missing, stale, and uncertain registrations explicitly refuse.",
))

REGISTRY.register(Seed(
    id="allocentric_world_view", version="1.0.0",
    depends_on=("optic_flow_spatial_grounding",
                "transsaccadic_feature_memory"),
    installer=_installer_from_manifest("allocentric_world_view"),
    description="Default-off generic persistent allocentric visible-surface "
                "memory. Current graph-admitted optic range evidence is "
                "associated by uncertainty support and graph-native "
                "ArgminUnique; exact ties refuse, while novel support grows "
                "the view and revisits refresh it. Exact-one current optic or "
                "transsaccadic photometry supplies an epoch-scoped render "
                "value. No Doom grid or occupancy claim.",
))

REGISTRY.register(Seed(
    id="foveal_predictive_coding", version="1.0.0",
    depends_on=("reflex_net", "allocentric_world_view"),
    installer=_installer_from_manifest("foveal_predictive_coding"),
    description="Default-off dense foveal predictive coding: shared retinal "
                "tile encoder, locally self-training decoder, allocentric "
                "latent priors, and exact-tie-refusing residual settlement.",
))

REGISTRY.register(Seed(
    id="global_illumination_eye", version="1.0.0",
    depends_on=("allocentric_world_view",),
    installer=_installer_from_manifest("global_illumination_eye"),
    description="Default-off split-eye illumination inference: rapid foveal "
                "gain proposals, sparse broad-field corroboration, explicit "
                "observed/predicted provenance, and whole-view predictive "
                "appearance reconditioning.",
))

REGISTRY.register(Seed(
    id="instruction_understanding", version="1.0.0",
    depends_on=("intent",),
    installer=_installer_from_manifest("instruction_understanding"),
    description="Graph-native instruction lifecycle: candidate interpretation, "
                "ambiguity hold, local verification, dictionary/Wikipedia/LLM "
                "teacher escalation, structured evidence staging, replay-gated "
                "lesson adoption, and integer-only self-weaning metrics.",
))

REGISTRY.register(Seed(
    id="goal_residuals", version="1.0.0", depends_on=(),
    installer=_installer_from_manifest("goal_residuals"),
    description="MEASURED CEILINGS, GRAPH-RESIDENT: GoalResidual + "
                "ResidualCondition nodes ingested mechanically from the arc-6 "
                "results artifacts, plus the gr_* staleness / penalty rules. A "
                "held residual is a strong NEGATIVE WEIGHT in the existing "
                "ps_move_select collapse, never a veto; a residual whose "
                "condition no longer holds goes stale.",
))
