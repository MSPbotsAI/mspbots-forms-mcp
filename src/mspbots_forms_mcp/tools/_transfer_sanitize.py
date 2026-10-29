"""Pure-function helpers for cross-tenant form export/import (PRD-21397).

Isolated from transfer.py (the tool-registration module) so these can be
unit-tested without any FormsAPIClient/network dependency — same split as
_common.py's NO_TOKEN constant, just for logic instead of a literal.
"""

import copy
import re
from typing import Any

from .._json import error_envelope
from ._survey_walk import normalize_choice_source

# Export envelope format version. Bump this and add a new validate/transform
# path when the envelope shape changes (e.g. a future version carrying
# share/theme settings) — see Tech design SS5 "Backward compatibility".
EXPORT_SCHEMA_VERSION = 1

# Keys that mark a static choice option as tenant-scoped (PRD-21397 ticket:
# tenantId, haloClientId, rewstOrgId — e.g. Ginko's client_org options).
# Extend this set here for future integrations (Open questions, design doc).
TENANT_SCOPED_CHOICE_KEYS = {"tenantId", "haloClientId", "rewstOrgId"}

# Form-record keys that must never reach the import PATCH body even under
# the "copy the whole record" strategy (review round 2, must-fix #2):
#   - "status": the base record's draft/published/archived field (confirmed
#     to exist by forms.py's own status-filtered form_list and shares.py's
#     parallel status state machine) -- copying it from a published source
#     form would auto-publish the freshly created (currently-draft) form,
#     contradicting the ticket's "unpublished" requirement.
# Beyond that literal, the real field names for owner/sharing/publish-state
# metadata are unverified (forms.py:1-6's own disclaimer: built from a
# pasted API contract, never called against a real deployment) -- so rather
# than guess more literals and risk missing a variant, anything whose name
# looks owner/sharing/publish-shaped is excluded by substring match. Revisit
# once TC2 against a real form shows the actual key names.
_NON_TRANSFERABLE_SETTING_KEYS = frozenset({"id", "definition", "questions", "versions", "status"})
_NON_TRANSFERABLE_SETTING_PATTERN = re.compile(r"owner|shar|publish", re.IGNORECASE)


def is_transferable_setting(key: str) -> bool:
    """True if `key` is safe to carry from the source form record onto the
    import PATCH body (transfer.py's mspbots_forms_form_import)."""
    return key not in _NON_TRANSFERABLE_SETTING_KEYS and not _NON_TRANSFERABLE_SETTING_PATTERN.search(
        key
    )


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
      - a dict with static choice options (either a top-level "choices"
        list, or a "choicesSource": {"items": [...]} dict — the shape
        live-tested and confirmed for the real client_org question on
        sibling ticket PRD-21379, see _choice_keys below) whose items carry
        any key in TENANT_SCOPED_CHOICE_KEYS (checked both on the item
        itself and inside a nested "attrs" dict, the real client_org
        shape) -> the options are cleared (and "choicesSource" dropped
        entirely, same wholesale-clear treatment as choicesByUrl); reported
        as "static tenant-scoped options (<matched keys>)".

    Returns a deep copy — the caller's original definition is never mutated.
    """
    working = copy.deepcopy(definition)
    report: list[dict] = []
    _walk(working, report)
    return working, report


def _choice_keys(choice: dict) -> set[str]:
    """Keys that could mark `choice` as tenant-scoped: the choice's own
    top-level keys (the shape this module originally assumed, still used by
    this ticket's own TC5/TC6 fixtures), plus a nested "attrs" dict's keys
    — the real shape of Ginko's client_org question (choicesSource.items[*]
    .attrs), live-tested and confirmed on sibling ticket PRD-21379
    (test_form_get_field_id_handles_choices_source_shape)."""
    keys = set(choice.keys())
    attrs = choice.get("attrs")
    if isinstance(attrs, dict):
        keys |= attrs.keys()
    return keys


def _walk(node: Any, report: list[dict]) -> None:
    if isinstance(node, dict):
        if "choicesByUrl" in node:
            node.pop("choicesByUrl", None)
            node["choices"] = []
            report.append(
                {"field": _field_label(node), "reason": "data-source-bound (choicesByUrl)"}
            )

        # A static-choice question's options can live under a top-level
        # "choices" list, or under "choicesSource": {"items": [...]} (the
        # real shape confirmed for client_org — see docstring above).
        # normalize_choice_source (_survey_walk.py, already live-tested on
        # PRD-21379) is read-only here: it returns `node` itself unchanged
        # when there's nothing to normalize, or a *new* dict otherwise, so
        # peeking at it never mutates the tree unless a tenant-scoped match
        # is actually found below.
        candidate = normalize_choice_source(node) if "choicesSource" in node else node
        choices = candidate.get("choices")
        if isinstance(choices, list):
            matched_keys: set[str] = set()
            for choice in choices:
                if isinstance(choice, dict):
                    matched_keys |= TENANT_SCOPED_CHOICE_KEYS & _choice_keys(choice)
            if matched_keys:
                if candidate is not node:
                    # The match lived inside choicesSource.items -- drop the
                    # whole source rather than leaving a flattened "choices"
                    # list standing in for it (same wholesale-clear
                    # treatment as choicesByUrl above).
                    node.pop("choicesSource", None)
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
