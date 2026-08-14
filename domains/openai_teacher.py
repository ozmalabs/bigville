"""Stateless OpenAI teacher transport for graph-native supervision.

This is deliberately not a conversational partner and not a
``set_self_teacher`` callable.  That callable persists an ``answer`` as a
HeldAnswer; this transport returns only evidence a later graph step may adopt.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import requests

from domains.no_llm import assert_llm_allowed


MODEL = "gpt-5.6-terra"
RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_TIMEOUT_SECONDS = 30


class TeacherSchemaError(ValueError):
    """The service produced data outside the evidence-only contract."""


class TeacherTransportError(RuntimeError):
    """The teacher service could not provide a usable evidence lesson."""


@dataclass(frozen=True)
class TeacherQuestion:
    """A graph-selected request, serialized mechanically for the API."""

    instruction: str
    candidate_interpretation: Mapping[str, Any]
    context_projection: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TeacherQuestion":
        required = {"instruction", "candidate_interpretation", "context_projection"}
        if set(value) != required:
            raise TeacherSchemaError("TeacherQuestion must contain exactly instruction, "
                                     "candidate_interpretation, and context_projection")
        instruction = value["instruction"]
        candidate = value["candidate_interpretation"]
        context = value["context_projection"]
        if not isinstance(instruction, str) or not instruction.strip():
            raise TeacherSchemaError("TeacherQuestion.instruction must be non-empty text")
        if not isinstance(candidate, Mapping) or not isinstance(context, Mapping):
            raise TeacherSchemaError("TeacherQuestion graph projections must be objects")
        return cls(instruction, dict(candidate), dict(context))


@dataclass(frozen=True)
class TeacherEvidence:
    """Validated, non-renderable lesson material from the remote teacher.

    There is intentionally no ``answer``/``text`` field and no ``learn``
    payload. It therefore cannot be passed to ``learn_from_teacher`` or become
    a Message without a later graph-native adoption process.
    """

    verdict: str
    semantic_differences: tuple[str, ...]
    candidate_concepts: tuple[dict[str, str], ...]
    candidate_relations: tuple[dict[str, str], ...]
    candidate_frames: tuple[dict[str, Any], ...]
    candidate_constructions: tuple[dict[str, str], ...]
    missing_assumptions: tuple[str, ...]
    clarification_propositions: tuple[str, ...]
    evidence: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TeacherEvidence":
        if not isinstance(value, Mapping) or set(value) != set(TEACHER_EVIDENCE_SCHEMA["properties"]):
            raise TeacherSchemaError("teacher response does not match the evidence schema")
        verdict = value["verdict"]
        if verdict not in {"supported", "corrected", "ambiguous", "unknown"}:
            raise TeacherSchemaError("teacher verdict is invalid")
        return cls(
            verdict=verdict,
            semantic_differences=_strings(value["semantic_differences"]),
            candidate_concepts=_objects(value["candidate_concepts"], {"name", "definition"}),
            candidate_relations=_objects(value["candidate_relations"], {"subject", "predicate", "object"}),
            candidate_frames=_frames(value["candidate_frames"]),
            candidate_constructions=_objects(value["candidate_constructions"], {"name", "pattern"}),
            missing_assumptions=_strings(value["missing_assumptions"]),
            clarification_propositions=_strings(value["clarification_propositions"]),
            evidence=_strings(value["evidence"]),
        )


@dataclass(frozen=True)
class ShadowInterpretationQuestion:
    """A local graph interpretation presented for independent comparison."""

    utterance: str
    local_interpretation: Mapping[str, Any]
    context_projection: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ShadowInterpretationQuestion":
        required = {"utterance", "local_interpretation", "context_projection"}
        if not isinstance(value, Mapping) or set(value) != required:
            raise TeacherSchemaError(
                "ShadowInterpretationQuestion must contain exactly utterance, "
                "local_interpretation, and context_projection")
        if not isinstance(value["utterance"], str) or not value["utterance"].strip():
            raise TeacherSchemaError("shadow utterance must be non-empty text")
        if not isinstance(value["local_interpretation"], Mapping) \
                or not isinstance(value["context_projection"], Mapping):
            raise TeacherSchemaError("shadow graph projections must be objects")
        return cls(value["utterance"], dict(value["local_interpretation"]),
                   dict(value["context_projection"]))


_SHADOW_SPEECH_ACTS = {"question", "instruction", "statement", "request", "greeting", "feedback", "unknown"}
_SHADOW_TARGET_SCOPES = {"self_graph", "world", "topic", "conversation", "action", "unknown"}
_SHADOW_ANSWER_MODES = {"graph_state_description", "fact_retrieval", "action_execution", "clarification", "social", "unknown"}
_SHADOW_DIFFERENCE_DIMENSIONS = {
    "speech_act", "predicate", "content", "target_scope", "answer_mode", "requested_relations",
}


@dataclass(frozen=True)
class ShadowInterpretationEvidence:
    """An alternate parse only: evidence for comparison, never an answer."""

    verdict: str
    speech_act: str
    predicate: str
    content: str
    target_scope: str
    answer_mode: str
    requested_relations: tuple[str, ...]
    disagreement_dimensions: tuple[str, ...]
    ambiguities: tuple[str, ...]
    evidence_spans: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ShadowInterpretationEvidence":
        if not isinstance(value, Mapping) or set(value) != set(SHADOW_INTERPRETATION_SCHEMA["properties"]):
            raise TeacherSchemaError("shadow response does not match the interpretation schema")
        if value["verdict"] not in {"supported", "corrected", "ambiguous", "unknown"}:
            raise TeacherSchemaError("shadow verdict is invalid")
        if value["speech_act"] not in _SHADOW_SPEECH_ACTS:
            raise TeacherSchemaError("shadow speech act is invalid")
        if value["target_scope"] not in _SHADOW_TARGET_SCOPES:
            raise TeacherSchemaError("shadow target scope is invalid")
        if value["answer_mode"] not in _SHADOW_ANSWER_MODES:
            raise TeacherSchemaError("shadow answer mode is invalid")
        differences = _strings(value["disagreement_dimensions"])
        if any(item not in _SHADOW_DIFFERENCE_DIMENSIONS for item in differences):
            raise TeacherSchemaError("shadow disagreement dimension is invalid")
        if not isinstance(value["predicate"], str) or not isinstance(value["content"], str):
            raise TeacherSchemaError("shadow predicate and content must be strings")
        return cls(
            verdict=value["verdict"], speech_act=value["speech_act"],
            predicate=value["predicate"], content=value["content"],
            target_scope=value["target_scope"], answer_mode=value["answer_mode"],
            requested_relations=_strings(value["requested_relations"]),
            disagreement_dimensions=differences,
            ambiguities=_strings(value["ambiguities"]),
            evidence_spans=_strings(value["evidence_spans"]),
        )


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TeacherSchemaError("teacher evidence lists must contain only strings")
    return tuple(value)


def _objects(value: Any, required: set[str]) -> tuple[dict[str, str], ...]:
    if not isinstance(value, list):
        raise TeacherSchemaError("teacher evidence candidates must be arrays")
    out: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != required:
            raise TeacherSchemaError("teacher evidence candidate has an invalid shape")
        if any(not isinstance(item[key], str) for key in required):
            raise TeacherSchemaError("teacher evidence candidate values must be strings")
        out.append({key: item[key] for key in sorted(required)})
    return tuple(out)


def _frames(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        raise TeacherSchemaError("teacher frame candidates must be an array")
    out: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"name", "slots"}:
            raise TeacherSchemaError("teacher frame candidate has an invalid shape")
        if not isinstance(item["name"], str) or not isinstance(item["slots"], list):
            raise TeacherSchemaError("teacher frame candidate has invalid values")
        if any(not isinstance(slot, str) for slot in item["slots"]):
            raise TeacherSchemaError("teacher frame slots must be strings")
        out.append({"name": item["name"], "slots": list(item["slots"])})
    return tuple(out)


TEACHER_EVIDENCE_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "verdict": {"type": "string", "enum": ["supported", "corrected", "ambiguous", "unknown"]},
        "semantic_differences": {"type": "array", "items": {"type": "string"}},
        "candidate_concepts": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {"name": {"type": "string"}, "definition": {"type": "string"}}, "required": ["name", "definition"]}},
        "candidate_relations": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {"subject": {"type": "string"}, "predicate": {"type": "string"}, "object": {"type": "string"}}, "required": ["subject", "predicate", "object"]}},
        "candidate_frames": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {"name": {"type": "string"}, "slots": {"type": "array", "items": {"type": "string"}}}, "required": ["name", "slots"]}},
        "candidate_constructions": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {"name": {"type": "string"}, "pattern": {"type": "string"}}, "required": ["name", "pattern"]}},
        "missing_assumptions": {"type": "array", "items": {"type": "string"}},
        "clarification_propositions": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verdict", "semantic_differences", "candidate_concepts", "candidate_relations", "candidate_frames", "candidate_constructions", "missing_assumptions", "clarification_propositions", "evidence"],
}


SHADOW_INTERPRETATION_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "verdict": {"type": "string", "enum": ["supported", "corrected", "ambiguous", "unknown"]},
        "speech_act": {"type": "string", "enum": sorted(_SHADOW_SPEECH_ACTS)},
        "predicate": {"type": "string"},
        "content": {"type": "string"},
        "target_scope": {"type": "string", "enum": sorted(_SHADOW_TARGET_SCOPES)},
        "answer_mode": {"type": "string", "enum": sorted(_SHADOW_ANSWER_MODES)},
        "requested_relations": {"type": "array", "items": {"type": "string"}},
        "disagreement_dimensions": {"type": "array", "items": {
            "type": "string", "enum": sorted(_SHADOW_DIFFERENCE_DIMENSIONS)}},
        "ambiguities": {"type": "array", "items": {"type": "string"}},
        "evidence_spans": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verdict", "speech_act", "predicate", "content", "target_scope",
                 "answer_mode", "requested_relations", "disagreement_dimensions",
                 "ambiguities", "evidence_spans"],
}


def _main_repository_root() -> Path:
    """Find the main worktree in a linked-worktree checkout without git calls."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        dot_git = parent / ".git"
        if dot_git.is_file():
            try:
                line = dot_git.read_text(encoding="utf-8").strip()
                if line.startswith("gitdir: "):
                    gitdir = Path(line[8:]).expanduser()
                    if not gitdir.is_absolute():
                        gitdir = (parent / gitdir).resolve()
                    return gitdir.parents[1].parent
            except OSError:
                pass
        if dot_git.is_dir():
            return parent
    # Source distributions may not retain .git. In that case only, use the
    # closest explicit .env rather than silently failing to configure.
    for parent in here.parents:
        if (parent / ".env").is_file():
            return parent
    return here.parents[1]


def load_openai_api_key(*, environ: Mapping[str, str] | None = None,
                        env_path: Path | None = None) -> str | None:
    """Load only OPENAI_API_KEY, with process environment taking precedence.

    The source is never logged, serialized, or placed in graph data.
    """
    source = os.environ if environ is None else environ
    direct = source.get("OPENAI_API_KEY")
    if direct:
        return direct
    try:
        lines = (env_path or (_main_repository_root() / ".env")).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, sep, value = line.partition("=")
        if key.strip() == "OPENAI_API_KEY" and sep:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            return value or None
    return None


_SYSTEM_PROMPT = (
    "You are a bootstrap teacher for a graph-native cognitive system. Return only the requested JSON schema. "
    "Evaluate the candidate interpretation, not how to phrase an answer to a human. Supply provisional graph "
    "concepts, relations, frames, or constructions. Do not address the user, compose a reply, issue instructions, "
    "or propose executable code. Local dictionary and Wikipedia have already been consulted when relevant."
)

_SHADOW_SYSTEM_PROMPT = (
    "You are an independent interpretation sensor for a graph-native cognitive system. "
    "Return only the requested JSON schema. Interpret what the speaker is asking, compare it "
    "with the supplied local graph interpretation, and name every dimension on which they differ. "
    "The local interpretation remains authoritative; you are evidence, not an oracle. Do not answer "
    "the request, address the user, recommend actions, or emit executable code. Evidence spans must "
    "be short phrases copied from the utterance."
)


def _request_payload(question: TeacherQuestion) -> dict[str, Any]:
    evidence_request = {"instruction": question.instruction, "candidate_interpretation": question.candidate_interpretation, "context_projection": question.context_projection}
    return {
        "model": MODEL, "store": False, "reasoning": {"effort": "medium"},
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": _SYSTEM_PROMPT}]},
            {"role": "user", "content": [{"type": "input_text", "text": json.dumps(evidence_request, ensure_ascii=False, separators=(",", ":"))}]},
        ],
        "text": {"format": {"type": "json_schema", "name": "teacher_evidence", "strict": True, "schema": TEACHER_EVIDENCE_SCHEMA}},
    }


def _shadow_request_payload(question: ShadowInterpretationQuestion) -> dict[str, Any]:
    evidence_request = {
        "utterance": question.utterance,
        "local_interpretation": question.local_interpretation,
        "context_projection": question.context_projection,
    }
    return {
        "model": MODEL, "store": False, "reasoning": {"effort": "medium"},
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": _SHADOW_SYSTEM_PROMPT}]},
            {"role": "user", "content": [{"type": "input_text", "text": json.dumps(evidence_request, ensure_ascii=False, separators=(",", ":"))}]},
        ],
        "text": {"format": {"type": "json_schema", "name": "shadow_interpretation",
                            "strict": True, "schema": SHADOW_INTERPRETATION_SCHEMA}},
    }


def _response_text(payload: Mapping[str, Any]) -> str:
    status = payload.get("status")
    if isinstance(status, str) and status != "completed":
        # Structured Outputs only guarantees schema adherence for a completed
        # response. In particular, incomplete/refused responses must never be
        # treated as a partially valid lesson.
        raise TeacherTransportError(f"Responses API result is not completed: {status}")
    output = payload.get("output")
    if not isinstance(output, list):
        raise TeacherTransportError("Responses API result has no output")
    for item in output:
        if not isinstance(item, Mapping) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if isinstance(content, Mapping) and content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    raise TeacherTransportError("Responses API result has no structured output text")


class OpenAITeacher:
    """Final, explicitly selected teacher tier; returns evidence only."""

    def __init__(self, api_key: str | None = None, *, session: Any = None, timeout: int = DEFAULT_TIMEOUT_SECONDS):
        assert_llm_allowed("OpenAITeacher construction")
        self._api_key = api_key if api_key is not None else load_openai_api_key()
        self._session = session or requests.Session()
        self.timeout = timeout

    def is_available(self) -> bool:
        return bool(self._api_key)

    def ask(self, question: TeacherQuestion | Mapping[str, Any]) -> TeacherEvidence:
        """Request one stateless structured lesson. Never returns model prose."""
        assert_llm_allowed("OpenAITeacher.ask")
        if not self._api_key:
            raise TeacherTransportError("OPENAI_API_KEY is not configured")
        request = question if isinstance(question, TeacherQuestion) else TeacherQuestion.from_mapping(question)
        try:
            response = self._session.post(RESPONSES_URL, headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}, json=_request_payload(request), timeout=self.timeout)
            response.raise_for_status()
            response_payload = response.json()
            if not isinstance(response_payload, Mapping):
                raise TeacherTransportError("Responses API result is not an object")
            decoded = json.loads(_response_text(response_payload))
        except (requests.RequestException, ValueError, TypeError) as exc:
            raise TeacherTransportError("OpenAI teacher request failed") from exc
        return TeacherEvidence.from_mapping(decoded)

    def interpret(self, question: ShadowInterpretationQuestion | Mapping[str, Any]) \
            -> ShadowInterpretationEvidence:
        """Return a structured alternate interpretation, never response prose."""
        assert_llm_allowed("OpenAITeacher.interpret")
        if not self._api_key:
            raise TeacherTransportError("OPENAI_API_KEY is not configured")
        request = (question if isinstance(question, ShadowInterpretationQuestion)
                   else ShadowInterpretationQuestion.from_mapping(question))
        try:
            response = self._session.post(
                RESPONSES_URL,
                headers={"Authorization": f"Bearer {self._api_key}",
                         "Content-Type": "application/json"},
                json=_shadow_request_payload(request), timeout=self.timeout)
            response.raise_for_status()
            response_payload = response.json()
            if not isinstance(response_payload, Mapping):
                raise TeacherTransportError("Responses API result is not an object")
            decoded = json.loads(_response_text(response_payload))
        except (requests.RequestException, ValueError, TypeError) as exc:
            raise TeacherTransportError("OpenAI interpretation shadow failed") from exc
        return ShadowInterpretationEvidence.from_mapping(decoded)


__all__ = ["MODEL", "OpenAITeacher", "TeacherEvidence", "TeacherQuestion",
           "ShadowInterpretationEvidence", "ShadowInterpretationQuestion",
           "TeacherSchemaError", "TeacherTransportError", "TEACHER_EVIDENCE_SCHEMA",
           "SHADOW_INTERPRETATION_SCHEMA", "load_openai_api_key"]
