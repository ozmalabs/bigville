"""OZMA_NO_LLM — the hard kill-switch for hosted-LLM assistance at runtime.

Adapter POLICY, not an agent decision (per CLAUDE.md this is mechanical host
I/O — an env check at the teacher-construction/invocation boundary): when the
environment variable ``OZMA_NO_LLM`` is truthy, every LLM link in a teacher
chain is skipped — the chain falls through to its existing honest-miss path
(the human-gated close: the agent replies it can't ground the topic and
invites teaching) — and any code that would STILL attempt a hosted call
raises ``RuntimeError`` so violations are loud.

Guarded touchpoints (see docs/llm_touchpoint_audit.md for the full audit):
  - domains/libraries.py        _llm() / attach_libraries (the "llm" partner spec)
  - domains/llm_partner.py      LLMPartner construction + ask()
  - domains/rust_runtime_world.py  invoke_teacher (hosted anthropic call)
  - domains/structured_data_world.py  teacher_via_claude (`claude --print`)
  - domains/language_world.py   teacher_via_claude (`claude --print`)
  - domains/phonology_teacher.py  PhonologyTeacher (LLM path nulled; expert fallback)
  - scripts/claude_teacher.py   make_ask (`claude -p`)
"""
from __future__ import annotations

import os

_FALSY = {"", "0", "false", "no", "off"}


def no_llm() -> bool:
    """True when the OZMA_NO_LLM kill-switch is set (truthy).

    Truthy = set to anything other than "", "0", "false", "no", "off"
    (case-insensitive)."""
    return os.environ.get("OZMA_NO_LLM", "").strip().lower() not in _FALSY


def assert_llm_allowed(context: str) -> None:
    """Raise loudly if a hosted-LLM call is attempted under OZMA_NO_LLM.

    Call this at the exact point a hosted call would be made. Under the
    switch, chains must instead skip their LLM link and fall through to the
    non-LLM links / the honest-miss path."""
    if no_llm():
        raise RuntimeError(
            f"OZMA_NO_LLM is set: refusing hosted-LLM call from {context}. "
            "The teacher chain must fall through to its non-LLM links / the "
            "honest-miss path instead.")


__all__ = ["no_llm", "assert_llm_allowed"]
