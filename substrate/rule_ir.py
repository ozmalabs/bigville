"""Canonical executable-rule representation.

This is mechanical boundary code, not an alternate rule engine or a Python
oracle.  A rule is first compiled and exported by the Rust runtime; the result
is then normalised only where the runtime itself defines representations as
equivalent:

* match-clause order is ignored because the Rust installer reorders clauses;
* integer/float JSON spellings compare by their Rust ``Value`` numeric value;
* fields whose wire contract is JSON text compare by decoded content.

Consumers use this for hashes, refresh detection, and graph-composer parity.
The returned object is diagnostic data and must not be installed as a rule.
"""
from __future__ import annotations

import json
import math
from typing import Any


# These SeedDelta fields are explicitly JSON-on-the-wire.  A Python builder
# uses json.dumps while a graph composer uses ToJsonString; key order and
# numeric spelling in that text are not executable differences.
_JSON_TEXT_FIELDS = frozenset({
    "add_concepts",
    "add_rules",
    "remove_rules",
    "set_node_attrs",
    "skip_seeds",
})

# Runtime-generated identity/provenance fields describe the installed copy, not
# its executable body.  They can legitimately differ when identical source is
# compiled in separate scratch substrates.
_INSTALL_METADATA_FIELDS = frozenset({
    "active",
    "content_hash",
    "mutation_protected",
    "revision",
    "rule_uid",
})


def _number_key(value: int | float) -> str:
    """Canonicalise with the runtime's mixed Int/Float comparison semantics."""
    number = float(value)
    if math.isnan(number):
        return "nan"
    if math.isinf(number):
        return "inf" if number > 0 else "-inf"
    return number.hex()


def _semantic_value(value: Any, *, field: str | None = None) -> Any:
    if field in _JSON_TEXT_FIELDS and isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    if field == "add_rules" and isinstance(value, list):
        # Compiled rules may themselves be transported inside a SeedDelta.
        # Rust attaches per-install identities to those nested documents too.
        value = [
            {
                key: item
                for key, item in nested.items()
                if key not in _INSTALL_METADATA_FIELDS
            }
            if isinstance(nested, dict) else nested
            for nested in value
        ]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return {"__numeric_value__": _number_key(value)}
    if isinstance(value, list):
        return [_semantic_value(item) for item in value]
    if isinstance(value, dict):
        normalised = {
            key: _semantic_value(item, field=key)
            for key, item in sorted(value.items())
        }
        # And/Or are pure boolean folds in the Rust evaluator.  Their operands
        # have no effects and every Term is total, so authored order cannot
        # alter their value; graph composers and builders may append guards in
        # different orders without changing the executable predicate.
        if normalised.get("type") in {"And", "Or"}:
            items = normalised.get("items")
            if isinstance(items, list):
                normalised["items"] = sorted(
                    items, key=lambda item: json.dumps(item, sort_keys=True))
        return normalised
    return value


def canonical_rule(rule_json: dict[str, Any]) -> dict[str, Any] | None:
    """Return one deterministic semantic IR, or ``None`` if Rust rejects it."""
    try:
        import substrate_rs

        body = {
            key: value for key, value in rule_json.items()
            if key not in _INSTALL_METADATA_FIELDS
        }
        scratch = substrate_rs._native.Substrate()
        scratch.import_rules([{**body, "active": True}])
        exported = scratch.export_rules()[0]
        exported = {
            key: value for key, value in exported.items()
            if key not in _INSTALL_METADATA_FIELDS
        }
        match = exported.get("match")
        if isinstance(match, list):
            exported["match"] = sorted(
                match, key=lambda clause: json.dumps(clause, sort_keys=True))
        return _semantic_value(exported)
    except Exception:  # noqa: BLE001 - invalid/unavailable rules have no canonical IR
        return None


def canonical_rule_body(rule_json: dict[str, Any]) -> str:
    """Return the stable JSON encoding of :func:`canonical_rule`, or ``""``."""
    canonical = canonical_rule(rule_json)
    if canonical is None:
        return ""
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"))


def rules_semantically_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Whether two executable rule documents compile to the same canonical IR."""
    left_ir = canonical_rule(left)
    return left_ir is not None and left_ir == canonical_rule(right)


__all__ = ["canonical_rule", "canonical_rule_body", "rules_semantically_equal"]
