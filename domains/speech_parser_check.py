"""speech_parser_check.py -- self-test checks for the SPEECH_PARSER table (Phase 061).

Called from bigville_entities.check_consistency with the pack path. It checks the caps and the confidence
figure, that the fixed prefix names every understood act of SPEECH_ACTS (the prefix is built from that table),
and that every example reply passes the same reply check the model's answers pass
(bigville/backends/speech_parser.check_reply). The examples' speakers and listeners are the names the reply
may use.
"""
from __future__ import annotations

from domains.pack import load_pack

CAP_KEYS = ("max_calls_per_run", "max_spend", "timeout_s", "repair_attempts", "max_utterance_chars")
PREFIX_KEYS = ("intro", "schema", "examples")


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value


def check_speech_parser(pack_path, errors, warnings, info):
    from bigville.backends.speech_parser import check_reply, fixed_prefix, reference_hash
    pack = load_pack(pack_path)
    where = "SPEECH_PARSER"
    if "SPEECH_PARSER" not in pack.names():
        errors.append(f"{where}: the pack has no speech parser table (world/speech_parser.json)")
        return
    spec = pack["SPEECH_PARSER"]
    if not isinstance(spec.get("enabled"), bool):
        errors.append(f"{where}.enabled: must be true or false")
    elif spec["enabled"]:
        warnings.append(f"{where}.enabled is true: the parser is meant to be off until a provider is configured")
    if not isinstance(spec.get("schema_version"), int) or spec["schema_version"] < 1:
        errors.append(f"{where}.schema_version: must be a whole number of at least 1")

    caps = spec.get("caps", {})
    for key in CAP_KEYS:
        if key not in caps:
            errors.append(f"{where}.caps.{key}: missing")
    calls = caps.get("max_calls_per_run")
    if calls is not None and (not isinstance(calls, int) or isinstance(calls, bool) or calls < 0):
        errors.append(f"{where}.caps.max_calls_per_run: must be null or a whole number of at least 0")
    spend = caps.get("max_spend")
    if spend is not None and (not _number(spend) or spend < 0):
        errors.append(f"{where}.caps.max_spend: must be null or a number of at least 0")
    if not _number(caps.get("timeout_s")) or caps.get("timeout_s", 0) <= 0:
        errors.append(f"{where}.caps.timeout_s: must be a number above 0")
    repairs = caps.get("repair_attempts")
    if not isinstance(repairs, int) or isinstance(repairs, bool) or not 0 <= repairs <= 3:
        errors.append(f"{where}.caps.repair_attempts: must be a whole number from 0 to 3")
    chars = caps.get("max_utterance_chars")
    if not isinstance(chars, int) or isinstance(chars, bool) or chars < 1:
        errors.append(f"{where}.caps.max_utterance_chars: must be a whole number of at least 1")

    confidence = spec.get("confidence", {}).get("model")
    if not _number(confidence) or not 0.0 <= confidence <= 1.0:
        errors.append(f"{where}.confidence.model: must be a number from 0 to 1")

    prefix = spec.get("prefix", {})
    for key in PREFIX_KEYS:
        if key not in prefix:
            errors.append(f"{where}.prefix.{key}: missing")
    if any(key not in prefix for key in PREFIX_KEYS):
        return
    for key in ("intro", "schema"):
        if not str(prefix[key]).strip():
            errors.append(f"{where}.prefix.{key}: needs text")
    examples = prefix["examples"]
    if not isinstance(examples, list) or not examples:
        errors.append(f"{where}.prefix.examples: needs at least one example")
        examples = []
    for index, example in enumerate(examples):
        label = f"{where}.prefix.examples[{index}]"
        missing = [key for key in ("speaker", "listener", "utterance", "reply") if key not in example]
        if missing:
            errors.append(f"{label}: missing {', '.join(missing)}")
            continue
        answer, reason = check_reply(example["reply"], text=example["utterance"],
                                     allowed_names=[example["speaker"], example["listener"]], pack=pack_path)
        if answer is None:
            errors.append(f"{label}: its reply is not valid ({reason})")

    prefix_text = fixed_prefix(pack_path)
    for row in pack["SPEECH_ACTS"]:
        if row["understood_by"] == "simple" and f"- {row['act']}:" not in prefix_text:
            errors.append(f"{where}: the fixed prefix does not name the understood act {row['act']!r}")
    info.append(f"SPEECH_PARSER: off by default ({'on' if spec.get('enabled') else 'off'} in the pack), "
                f"{len(examples)} examples, the fixed prefix is {len(prefix_text.encode('utf-8'))} bytes, "
                f"reference sha256 {reference_hash(prefix_text)[:12]}")
