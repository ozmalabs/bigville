"""Durable, immutable local configuration template versions."""
from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .drafts import ALLOWED_FIELDS, DRAFT_FIELDS, resolve_draft


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class TemplateError(Exception):
    code = "template_error"


class TemplateNotFound(TemplateError):
    code = "template_not_found"


class TemplateInvalid(TemplateError):
    code = "invalid_template"


class TemplateUnavailable(TemplateError):
    code = "template_unavailable"


def _synchronized(method):
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapped


class TemplateRegistry:
    """Stores validated non-secret drafts in an atomic, versioned JSON file."""

    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path, *, profile_registry=None):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.profile_registry = profile_registry
        self._templates = self._load()

    def _load(self):
        if not self.path.exists():
            return {"schema_version": self.SCHEMA_VERSION, "templates": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Template registry is malformed; refusing to overwrite {self.path}") from exc
        if (not isinstance(data, dict) or data.get("schema_version") != self.SCHEMA_VERSION or
                not isinstance(data.get("templates"), dict)):
            raise ValueError(f"Template registry schema is incompatible; refusing to overwrite {self.path}")
        for template_id, template in data["templates"].items():
            if (not isinstance(template_id, str) or not template_id.startswith("tpl_") or
                    not isinstance(template, dict) or template.get("id") != template_id or
                    not isinstance(template.get("versions"), list)):
                raise ValueError(f"Template registry contains an invalid record; refusing to overwrite {self.path}")
            for index, version in enumerate(template["versions"], start=1):
                if (not isinstance(version, dict) or version.get("version") != index or
                        version.get("schema_version") != self.SCHEMA_VERSION or
                        not isinstance(version.get("draft"), dict) or
                        any(not isinstance(key, str) for key in version["draft"]) or
                        not ALLOWED_FIELDS.issubset(set(version["draft"])) or
                        not set(version["draft"]).issubset(DRAFT_FIELDS)):
                    raise ValueError(f"Template registry contains an invalid version; refusing to overwrite {self.path}")
        return data

    def _persist(self):
        encoded = json.dumps(self._templates, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
        fd, temp = tempfile.mkstemp(prefix=".templates-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as target:
                target.write(encoded)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temp, self.path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    @staticmethod
    def _clean_draft(resolution: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(resolution["template_draft"])

    @_synchronized
    def save(self, *, name: Any, draft: Any, template_id: str | None = None) -> dict[str, Any]:
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
            raise TemplateInvalid("Template name must contain 1 to 80 characters.")
        if template_id is not None and (not isinstance(template_id, str) or not template_id.startswith("tpl_")):
            raise TemplateInvalid("Template ID is invalid.")
        resolution = resolve_draft(draft, profile_registry=self.profile_registry)
        if not resolution["valid"]:
            error = TemplateInvalid("Template draft is invalid for current capabilities.")
            error.fields = resolution["errors"]
            raise error
        previous_state = copy.deepcopy(self._templates)
        if template_id is not None:
            existing = self._templates["templates"].get(template_id)
            if existing is None:
                raise TemplateNotFound(f"Template {template_id!r} was not found.")
        else:
            template_id = "tpl_" + uuid.uuid4().hex
            existing = {"id": template_id, "created_at": _now(), "versions": []}
        version_number = len(existing["versions"]) + 1
        version = {"schema_version": self.SCHEMA_VERSION, "version": version_number,
                   "name": name.strip(), "draft": self._clean_draft(resolution),
                   "configuration_hash": resolution["configuration_hash"],
                   "capability_revision": resolution["capability_revision"],
                   "created_at": _now()}
        updated = copy.deepcopy(existing)
        updated["name"] = name.strip()
        updated["updated_at"] = version["created_at"]
        updated["versions"] = [*updated["versions"], version]
        self._templates["templates"][template_id] = updated
        try:
            self._persist()
        except Exception:
            self._templates = previous_state
            raise
        return {"id": template_id, **copy.deepcopy(version)}

    @_synchronized
    def list_templates(self) -> list[dict[str, Any]]:
        result = []
        for template in self._templates["templates"].values():
            latest = template["versions"][-1]
            result.append({"id": template["id"], "name": template["name"],
                           "created_at": template["created_at"],
                           "updated_at": template.get("updated_at"),
                           "latest_version": latest["version"],
                           "configuration_hash": latest["configuration_hash"]})
        return sorted(result, key=lambda item: (item["name"].casefold(), item["id"]))

    @_synchronized
    def inspect(self, template_id: str) -> dict[str, Any]:
        template = self._templates["templates"].get(template_id)
        if template is None:
            raise TemplateNotFound(f"Template {template_id!r} was not found.")
        return {"id": template["id"], "name": template["name"],
                "created_at": template["created_at"], "updated_at": template.get("updated_at"),
                "versions": [{"version": item["version"], "name": item["name"],
                              "created_at": item["created_at"],
                              "configuration_hash": item["configuration_hash"],
                              "capability_revision": item["capability_revision"]}
                             for item in template["versions"]]}

    @_synchronized
    def get_version(self, template_id: str, version_number: int) -> dict[str, Any]:
        template = self._templates["templates"].get(template_id)
        if template is None:
            raise TemplateNotFound(f"Template {template_id!r} was not found.")
        if isinstance(version_number, bool) or not isinstance(version_number, int) or version_number < 1:
            raise TemplateNotFound("Template version was not found.")
        if version_number > len(template["versions"]):
            raise TemplateNotFound("Template version was not found.")
        return {"id": template_id, **copy.deepcopy(template["versions"][version_number - 1])}

    @_synchronized
    def load(self, template_id: str, version_number: int) -> dict[str, Any]:
        version = self.get_version(template_id, version_number)
        if version["schema_version"] != self.SCHEMA_VERSION:
            raise TemplateUnavailable("This template uses an unsupported draft schema.")
        if (not ALLOWED_FIELDS.issubset(set(version["draft"])) or
                not set(version["draft"]).issubset(DRAFT_FIELDS)):
            raise TemplateUnavailable("This template draft schema is incompatible with this version of the service.")
        resolution = resolve_draft(version["draft"], profile_registry=self.profile_registry)
        if not resolution["valid"]:
            error = TemplateUnavailable("Template capabilities are unavailable in this checkout.")
            error.fields = resolution["errors"]
            raise error
        if (resolution["configuration_hash"] != version["configuration_hash"] or
                resolution["capability_revision"] != version["capability_revision"]):
            raise TemplateUnavailable(
                "Template capability, backend profile, or scenario identity changed. This immutable version remains inspectable but cannot be loaded; save a compatible version from a current draft.")
        if self._clean_draft(resolution) != version["draft"]:
            raise TemplateUnavailable("This template draft is not in its exact canonical form; it was not normalized.")
        return version

    @_synchronized
    def verify_run_source(self, template_id: str, version_number: int) -> dict[str, Any]:
        version = self.load(template_id, version_number)
        return {"id": template_id, "version": version_number,
                "configuration_hash": version["configuration_hash"],
                "capability_revision": version["capability_revision"]}
