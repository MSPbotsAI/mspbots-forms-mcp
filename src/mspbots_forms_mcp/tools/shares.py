"""Share link (distribution policy) tools.

⚠️ UNVERIFIED — built entirely from the API contract pasted into ClickUp
PRD-15818 (per Leo Yang's comment), not by reading the actual backend repo.
See README Known Gaps.
"""

import json
from collections.abc import Callable

from mcp.server.fastmcp import FastMCP

from ..api_client import FormsAPIClient, FormsAPIError
from ._common import NO_TOKEN

_ACTION_TO_STATUS = {"pause": "paused", "resume": "active", "close": "closed"}


def register(mcp: FastMCP, client_factory: Callable[[], FormsAPIClient | None]) -> None:
    @mcp.tool()
    async def share_list(survey_id: str) -> str:
        """List share links for a survey.

        API: GET /api/surveys/:surveyId/shares

        Args:
            survey_id: Required survey ID.
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        try:
            result = await client.get(f"/surveys/{survey_id}/shares")
            return json.dumps(result, indent=2)
        except FormsAPIError as e:
            return f"Error: {e}"

    @mcp.tool()
    async def share_get(share_id: str) -> str:
        """Get a share link's details.

        API: GET /api/shares/:shareId

        Args:
            share_id: Required share ID.
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        try:
            result = await client.get(f"/shares/{share_id}")
            return json.dumps(result, indent=2)
        except FormsAPIError as e:
            return f"Error: {e}"

    @mcp.tool()
    async def share_create(
        survey_id: str,
        survey_version_id: str | None = None,
        audience: str = "public",
        passcode: str | None = None,
        recipient: str | None = None,
        duplicate_check: str | None = None,
        allow_resume: bool | None = None,
        response_limit: int | None = None,
        opens_at: str | None = None,
        closes_at: str | None = None,
        prefill: dict | None = None,
    ) -> str:
        """Create a share link for a survey. The survey must have been
        published at least once (survey_publish) — otherwise this returns
        409 conflict.

        API: POST /api/surveys/:surveyId/shares

        Args:
            survey_id: Required survey ID to create a share for.
            survey_version_id: Optional specific version to bind to; defaults
                to the latest published version if omitted.
            audience: Who can fill it in — "public" (anyone with the link,
                default), "workspace" (must be logged in), "passcode"
                (requires the passcode field), "personal" (one link per
                recipient — requires the recipient field).
            passcode: Required if audience="passcode". A string sets it; the
                response never echoes it back (only a hasPasscode boolean).
            recipient: Required if audience="personal" — identifies who this
                link is for.
            duplicate_check: Optional dedup strength — "off", "browser"
                (cookie-based, weakest, no false positives), "network"
                (IP-based, can falsely block coworkers behind the same NAT),
                "once" (one submission per link, most reliable).
            allow_resume: Optional, whether respondents can save progress and
                resume later. Note: single-page surveys have no page-turn
                event, so progress can't be saved regardless of this setting.
            response_limit: Optional cap on the number of responses; once
                reached, further submissions get limit_reached.
            opens_at: Optional ISO 8601 timestamp — collection doesn't start
                before this.
            closes_at: Optional ISO 8601 timestamp — collection stops after this.
            prefill: Optional dict of answers to pre-fill for respondents.
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        body: dict = {"audience": audience}
        if survey_version_id is not None:
            body["surveyVersionId"] = survey_version_id
        if passcode is not None:
            body["passcode"] = passcode
        if recipient is not None:
            body["recipient"] = recipient
        if duplicate_check is not None:
            body["duplicateCheck"] = duplicate_check
        if allow_resume is not None:
            body["allowResume"] = allow_resume
        if response_limit is not None:
            body["responseLimit"] = response_limit
        if opens_at is not None:
            body["opensAt"] = opens_at
        if closes_at is not None:
            body["closesAt"] = closes_at
        if prefill is not None:
            body["prefill"] = prefill
        try:
            result = await client.post(f"/surveys/{survey_id}/shares", json_body=body)
            return json.dumps(result, indent=2)
        except FormsAPIError as e:
            return f"Error: {e}"

    @mcp.tool()
    async def share_update(
        share_id: str,
        action: str | None = None,
        audience: str | None = None,
        passcode: str | None = None,
        recipient: str | None = None,
        duplicate_check: str | None = None,
        allow_resume: bool | None = None,
        response_limit: int | None = None,
        opens_at: str | None = None,
        closes_at: str | None = None,
        prefill: dict | None = None,
    ) -> str:
        """Update a share link's policy, or perform a lifecycle action.

        API: PATCH /api/shares/:shareId (idempotent) for policy field
        changes, OR POST /api/shares/:shareId/token for action="rotate".

        Args:
            share_id: Required share ID.
            action: Optional convenience action — "pause" (status=paused),
                "resume" (status=active), "close" (status=closed, a soft
                close), or "rotate" (issues a new token; the old link
                immediately stops working, but already-collected responses
                stay attached to this same share). Mutually exclusive with
                the policy fields below — if action is given, the other
                fields are ignored.
            audience: Optional new audience — "public"/"workspace"/
                "passcode"/"personal". Only used when action is not given.
            passcode: Optional — a string sets a new passcode, null/empty
                clears it, omit to leave unchanged. Only used when action is
                not given.
            recipient: Optional new recipient (for audience="personal"). Only
                used when action is not given.
            duplicate_check: Optional new dedup strength — "off"/"browser"/
                "network"/"once". Only used when action is not given.
            allow_resume: Optional new resume setting. Only used when action
                is not given.
            response_limit: Optional new response cap. Only used when action
                is not given.
            opens_at: Optional new ISO 8601 open time. Only used when action
                is not given.
            closes_at: Optional new ISO 8601 close time. Only used when
                action is not given.
            prefill: Optional new prefill answers. Only used when action is
                not given.
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        try:
            if action == "rotate":
                result = await client.post(f"/shares/{share_id}/token")
                return json.dumps(result, indent=2)
            body: dict = {}
            if action in _ACTION_TO_STATUS:
                body["status"] = _ACTION_TO_STATUS[action]
            elif action is not None:
                return f"Error: unknown action '{action}' — expected pause, resume, close, or rotate"
            else:
                if audience is not None:
                    body["audience"] = audience
                if passcode is not None:
                    body["passcode"] = passcode
                if recipient is not None:
                    body["recipient"] = recipient
                if duplicate_check is not None:
                    body["duplicateCheck"] = duplicate_check
                if allow_resume is not None:
                    body["allowResume"] = allow_resume
                if response_limit is not None:
                    body["responseLimit"] = response_limit
                if opens_at is not None:
                    body["opensAt"] = opens_at
                if closes_at is not None:
                    body["closesAt"] = closes_at
                if prefill is not None:
                    body["prefill"] = prefill
            result = await client.patch(f"/shares/{share_id}", json_body=body)
            return json.dumps(result, indent=2)
        except FormsAPIError as e:
            return f"Error: {e}"

    @mcp.tool()
    async def share_delete(share_id: str, confirm: bool) -> str:
        """Delete a share link. Collected responses are preserved — they
        still have analytical value even after the link is gone.

        ⚠️ DESTRUCTIVE. Requires confirm=true.

        API: DELETE /api/shares/:shareId

        Args:
            share_id: Required share ID to delete.
            confirm: Required — must be set to true to proceed.
        """
        if not confirm:
            return "Error: destructive operation requires confirm=true"
        client = client_factory()
        if client is None:
            return NO_TOKEN
        try:
            result = await client.delete(f"/shares/{share_id}")
            return json.dumps(result, indent=2)
        except FormsAPIError as e:
            return f"Error: {e}"
