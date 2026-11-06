"""Server-owned backend profiles and adapters for management-created runs."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable


PROFILE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")
CONFIG_FIELDS = {"id", "name", "kind", "revision", "adapter", "secret_ref", "enabled"}


class ProfileError(ValueError):
    def __init__(self, message: str, *, code="invalid_profile", fields=None):
        super().__init__(message)
        self.code = code
        self.fields = fields or {}


class BackendAdapterRegistry:
    """Explicit adapter allowlist. Adapters build backends using server-side profile data."""

    def __init__(self):
        self._factories: dict[str, Callable[..., Any]] = {}

    def register(self, adapter_id: str, factory: Callable[..., Any]) -> None:
        if not isinstance(adapter_id, str) or not PROFILE_ID.fullmatch(adapter_id):
            raise ValueError("Adapter IDs must be stable identifier strings.")
        if not callable(factory):
            raise TypeError("Backend adapter factory must be callable.")
        self._factories[adapter_id] = factory

    def unregister(self, adapter_id: str) -> None:
        self._factories.pop(adapter_id, None)

    def contains(self, adapter_id: str | None) -> bool:
        return isinstance(adapter_id, str) and adapter_id in self._factories

    def build(self, profile: dict[str, Any], world, character):
        adapter_id = profile.get("adapter")
        factory = self._factories.get(adapter_id)
        if factory is None:
            raise ProfileError("The configured backend adapter is unavailable.", code="profile_unavailable")
        # `profile` may contain a local secret reference. It never leaves this server-side call.
        try:
            backend = factory(world, character, copy.deepcopy(profile))
        except Exception:
            raise ProfileError("The server-side provider adapter could not initialize.",
                               code="profile_initialization_failed") from None
        from ..backends.llm import LLMBackend
        if not isinstance(backend, LLMBackend):
            raise ProfileError("An LLM profile adapter must construct an LLMBackend.",
                               code="invalid_profile_adapter")
        provider = backend.provider

        class SanitizedProvider:
            @property
            def last_cost(self):
                value = getattr(provider, "last_cost", None)
                return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

            def complete(self, payload):
                try:
                    complete = getattr(provider, "complete", None)
                    if callable(complete):
                        return complete(payload)
                    if callable(provider):
                        return provider(payload)
                    raise TypeError("provider has no completion method")
                except Exception:
                    raise RuntimeError("configured provider request failed") from None

        backend.provider = SanitizedProvider()
        return backend


class BackendProfileRegistry:
    """Loads non-secret profile metadata and reports readiness from actual adapters."""

    def __init__(self, config_path: str | Path | None = None,
                 adapters: BackendAdapterRegistry | None = None):
        self.config_path = Path(config_path).expanduser().resolve() if config_path else None
        self.adapters = adapters or BackendAdapterRegistry()
        self._configured = self._load_config()

    def _load_config(self) -> list[dict[str, Any]]:
        if self.config_path is None or not self.config_path.exists():
            return []
        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Backend profile configuration is malformed: {self.config_path}") from exc
        if (not isinstance(payload, dict) or set(payload) != {"schema_version", "profiles"} or
                payload.get("schema_version") != 1 or not isinstance(payload.get("profiles"), list)):
            raise ValueError("Backend profile configuration must use schema_version 1 and a profiles list.")
        profiles = []
        seen = {"simple.default", "ocelot.default"}
        for index, value in enumerate(payload["profiles"]):
            if not isinstance(value, dict) or set(value) - CONFIG_FIELDS:
                raise ValueError(f"Backend profile entry {index} has unsupported fields.")
            profile_id, kind, revision = value.get("id"), value.get("kind"), value.get("revision")
            if not isinstance(profile_id, str) or not PROFILE_ID.fullmatch(profile_id) or profile_id in seen:
                raise ValueError(f"Backend profile entry {index} has an invalid or duplicate ID.")
            if kind != "llm":
                raise ValueError(
                    f"Configured profile {profile_id!r} uses an unsupported custom kind; "
                    "simple and Ocelot use only their built-in profiles.")
            if not isinstance(revision, str) or not revision.strip() or len(revision) > 80:
                raise ValueError(f"Backend profile {profile_id!r} needs a revision string.")
            if "enabled" in value and not isinstance(value["enabled"], bool):
                raise ValueError(f"Backend profile {profile_id!r} enabled must be boolean.")
            if "secret_ref" in value and not isinstance(value["secret_ref"], str):
                raise ValueError(f"Backend profile {profile_id!r} secret_ref must be a local reference string.")
            adapter = value.get("adapter")
            if kind == "llm" and (not isinstance(adapter, str) or not PROFILE_ID.fullmatch(adapter)):
                raise ValueError(f"LLM profile {profile_id!r} needs a registered adapter ID.")
            profiles.append({"id": profile_id, "name": str(value.get("name") or profile_id),
                             "kind": kind, "revision": revision.strip(), "adapter": adapter,
                             "secret_ref": value.get("secret_ref"),
                             "enabled": value.get("enabled", True)})
            seen.add(profile_id)
        return profiles

    def _ocelot_available(self) -> tuple[bool, str | None]:
        try:
            from ..backends.ocelot import ocelot_resident_class
            ocelot_resident_class()
        except Exception as exc:
            return False, str(exc)
        return True, None

    def _private_profiles(self) -> list[dict[str, Any]]:
        builtins = [
            {"id": "simple.default", "name": "Simple default", "kind": "simple",
             "revision": "builtin-1", "adapter": None, "secret_ref": None, "enabled": True},
            {"id": "ocelot.default", "name": "Ocelot default", "kind": "ocelot",
             "revision": "builtin-1", "adapter": None, "secret_ref": None, "enabled": True},
        ]
        return builtins + copy.deepcopy(self._configured)

    def _readiness(self, profile: dict[str, Any]) -> tuple[bool, str | None]:
        if not profile["enabled"]:
            return False, "This profile is disabled in the server configuration."
        if profile["kind"] == "simple":
            return True, None
        if profile["kind"] == "ocelot":
            return self._ocelot_available()
        if not self.adapters.contains(profile.get("adapter")):
            return False, "No server-side provider adapter is registered for this profile."
        return True, None

    def public_profiles(self) -> dict[str, Any]:
        profiles = []
        private_revision_data = []
        for profile in self._private_profiles():
            ready, reason = self._readiness(profile)
            profiles.append({"id": profile["id"], "name": profile["name"],
                             "kind": profile["kind"], "revision": profile["revision"],
                             "available": ready, "reason": reason})
            private_revision_data.append({"public": profiles[-1], "adapter": profile.get("adapter"),
                                          "secret_ref": profile.get("secret_ref"),
                                          "enabled": profile.get("enabled", True)})
        profiles.sort(key=lambda item: (item["kind"], item["name"].casefold(), item["id"]))
        private_revision_data.sort(key=lambda item: item["public"]["id"])
        revision = hashlib.sha256(json.dumps(private_revision_data, sort_keys=True,
                                               separators=(",", ":")).encode()).hexdigest()
        return {"schema_version": 1, "revision": revision, "profiles": profiles}

    def get(self, profile_id: str) -> dict[str, Any]:
        profile = next((item for item in self._private_profiles() if item["id"] == profile_id), None)
        if profile is None:
            raise ProfileError(f"Backend profile {profile_id!r} was not found.", code="profile_not_found")
        available, reason = self._readiness(profile)
        if not available:
            raise ProfileError(reason or "Backend profile is unavailable.", code="profile_unavailable",
                               fields={"profile": reason or "Unavailable."})
        return profile

    def default_id_for_kind(self, kind: str) -> str | None:
        choices = [item for item in self._private_profiles() if item["kind"] == kind]
        ready = [item for item in choices if self._readiness(item)[0]]
        return ready[0]["id"] if len(ready) == 1 else None

    def build_backend(self, profile_id: str, world, character):
        profile = self.get(profile_id)
        if profile["kind"] != "llm":
            raise ProfileError("Only LLM profiles use a provider adapter.")
        return self.adapters.build(profile, world, character)
