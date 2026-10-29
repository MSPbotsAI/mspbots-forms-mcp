"""Pure-function helpers for cross-tenant form export/import (PRD-21397).

Isolated from transfer.py (the tool-registration module) so these can be
unit-tested without any FormsAPIClient/network dependency — same split as
_common.py's NO_TOKEN constant, just for logic instead of a literal.
"""

import copy
from typing import Any

from .._json import error_envelope

# Export envelope format version. Bump this and add a new validate/transform
# path when the envelope shape changes (e.g. a future version carrying
# share/theme settings) — see Tech design SS5 "Backward compatibility".
EXPORT_SCHEMA_VERSION = 1

# Keys that mark a static choice option as tenant-scoped (PRD-21397 ticket:
# tenantId, haloClientId, rewstOrgId — e.g. Ginko's client_org options).
# Extend this set here for future integrations (Open questions, design doc).
TENANT_SCOPED_CHOICE_KEYS = {"tenantId", "haloClientId", "rewstOrgId"}


class TransferError(Exception):
    """Mirrors FormsAPIError's to_envelope() shape for transfer-specific
    validation failures that happen before any network call is made."""

    def __init__(self, code: str, message: str, retryable: bool = False):
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(message)

    def to_envelope(self) -> str:
        return error_envelope(self.code, self.message, self.retryable)


def validate_export_version(payload: dict) -> None:
    """Raise TransferError if payload's export_version isn't one this
    server supports. Must be called before any create/patch call — a half
    import (shell form created, then refused) is worse than refusing up
    front (AC6)."""
    version = payload.get("export_version")
    if version != EXPORT_SCHEMA_VERSION:
        raise TransferError(
            "invalid_argument",
            f"Unsupported export_version: {version!r}. This server supports: {EXPORT_SCHEMA_VERSION}.",
            retryable=False,
        )


def _field_label(node: dict) -> str:
    """Best-effort human-readable name for a report entry. SurveyJS-shaped
    question dicts carry "name" (the generated q1/q2 id) and/or "title" (the
    friendly label) — prefer name since it's stable and always present on a
    real question node; fall back to title, then a generic placeholder."""
    return node.get("name") or node.get("title") or "<unnamed field>"


def strip_tenant_specific(definition: dict) -> tuple[dict, list[dict]]:
    """Recursively walk a form definition tree (generic walk, not assuming
    a fixed pages[].elements[] shape — the SurveyJS shape this server
    produces is itself unverified, see Tech design SS Option analysis),
    removing anything tenant-specific and returning a report of what was
    removed.

    Two cases, each independently detected on every dict in the tree:
      - a dict with "choicesByUrl" -> that key is dropped and "choices" (if
        present) is cleared; reported as "data-source-bound (choicesByUrl)".
      - a dict with a "choices" list whose items are themselves dicts
        containing any key in TENANT_SCOPED_CHOICE_KEYS -> "choices" is
        cleared; reported as "static tenant-scoped options (<matched keys>)".

    Returns a deep copy — the caller's original definition is never mutated.
    """
    working = copy.deepcopy(definition)
    report: list[dict] = []
    _walk(working, report)
    return working, report


def _walk(node: Any, report: list[dict]) -> None:
    if isinstance(node, dict):
        if "choicesByUrl" in node:
            node.pop("choicesByUrl", None)
            node["choices"] = []
            report.append(
                {"field": _field_label(node), "reason": "data-source-bound (choicesByUrl)"}
            )

        choices = node.get("choices")
        if isinstance(choices, list):
            matched_keys: set[str] = set()
            for choice in choices:
                if isinstance(choice, dict):
                    matched_keys |= TENANT_SCOPED_CHOICE_KEYS & choice.keys()
            if matched_keys:
                node["choices"] = []
                report.append(
                    {
                        "field": _field_label(node),
                        "reason": f"static tenant-scoped options ({', '.join(sorted(matched_keys))})",
                    }
                )

        for value in node.values():
            _walk(value, report)

    elif isinstance(node, list):
        for item in node:
            _walk(item, report)
