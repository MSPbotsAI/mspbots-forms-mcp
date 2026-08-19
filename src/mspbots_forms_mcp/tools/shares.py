"""Share link (distribution policy) tools.

⚠️ UNVERIFIED — built entirely from the API contract pasted into ClickUp
PRD-15818 (per Leo Yang's comment), not by reading the actual backend repo.
See README Known Gaps.
"""

from collections.abc import Callable
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .._json import dump_json_capped, error_envelope
from ..api_client import FormsAPIClient, FormsAPIError
from ._common import NO_TOKEN

_ACTION_TO_STATUS = {"pause": "paused", "resume": "active", "close": "closed"}


def register(mcp: FastMCP, client_factory: Callable[[], FormsAPIClient | None]) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def mspbots_forms_share_list(
        survey_id: Annotated[str, Field(description="Required survey ID.")],
    ) -> str:
        """List share links for a survey.
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        try:
            result = await client.get(f"/surveys/{survey_id}/shares")
            return dump_json_capped(result)
        except FormsAPIError as e:
            return e.to_envelope()

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def mspbots_forms_share_get(
        share_id: Annotated[str, Field(description="Required share ID.")],
    ) -> str:
        """Get a share link's details.
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        try:
            result = await client.get(f"/shares/{share_id}")
            return dump_json_capped(result)
        except FormsAPIError as e:
            return e.to_envelope()

    @mcp.tool()
    async def mspbots_forms_share_create(
        survey_id: Annotated[str, Field(description="Required survey ID to create a share for.")],
        survey_version_id: Annotated[
            str | None,
            Field(
                description=(
                    "Optional specific version to bind to; defaults "
                    "to the latest published version if omitted."
                )
            ),
        ] = None,
        audience: Annotated[
            str,
            Field(
                description=(
                    'Who can fill it in — "public" (anyone with the link, '
                    'default), "workspace" (must be logged in), "passcode" '
                    '(requires the passcode field), "personal" (one link per '
                    "recipient — requires the recipient field)."
                )
            ),
        ] = "public",
        passcode: Annotated[
            str | None,
            Field(
                description=(
                    'Required if audience="passcode". A string sets it; the '
                    "response never echoes it back (only a hasPasscode boolean)."
                )
            ),
        ] = None,
        recipient: Annotated[
            str | None,
            Field(
                description=(
                    'Required if audience="personal" — identifies who this link is for.'
                )
            ),
        ] = None,
        duplicate_check: Annotated[
            str | None,
            Field(
                description=(
                    'Optional dedup strength — "off", "browser" '
                    "(cookie-based, weakest, no false positives), \"network\" "
                    "(IP-based, can falsely block coworkers behind the same NAT), "
                    '"once" (one submission per link, most reliable).'
                )
            ),
        ] = None,
        allow_resume: Annotated[
            bool | None,
            Field(
                description=(
                    "Optional, whether respondents can save progress and "
                    "resume later. Note: single-page surveys have no page-turn "
                    "event, so progress can't be saved regardless of this setting."
                )
            ),
        ] = None,
        response_limit: Annotated[
            int | None,
            Field(
                description=(
                    "Optional cap on the number of responses; once "
                    "reached, further submissions get limit_reached."
                )
            ),
        ] = None,
        opens_at: Annotated[
            str | None,
            Field(
                description="Optional ISO 8601 timestamp — collection doesn't start before this."
            ),
        ] = None,
        closes_at: Annotated[
            str | None,
            Field(description="Optional ISO 8601 timestamp — collection stops after this."),
        ] = None,
        prefill: Annotated[
            dict | None,
            Field(description="Optional dict of answers to pre-fill for respondents."),
        ] = None,
    ) -> str:
        """Create a share link for a survey. The survey must have been
        published at least once (mspbots_forms_survey_publish) — otherwise this returns
        409 conflict.
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
            return dump_json_capped(result)
        except FormsAPIError as e:
            return e.to_envelope()

    @mcp.tool(annotations=ToolAnnotations(idempotentHint=True))
    async def mspbots_forms_share_update(
        share_id: Annotated[str, Field(description="Required share ID.")],
        action: Annotated[
            str | None,
            Field(
                description=(
                    'Optional convenience action — "pause" (status=paused), '
                    '"resume" (status=active), "close" (status=closed, a soft '
                    'close), or "rotate" (issues a new token; the old link '
                    "immediately stops working, but already-collected responses "
                    "stay attached to this same share). Mutually exclusive with "
                    "the policy fields below — if action is given, the other "
                    "fields are ignored."
                )
            ),
        ] = None,
        audience: Annotated[
            str | None,
            Field(
                description=(
                    'Optional new audience — "public"/"workspace"/'
                    '"passcode"/"personal". Only used when action is not given.'
                )
            ),
        ] = None,
        passcode: Annotated[
            str | None,
            Field(
                description=(
                    "Optional — a string sets a new passcode, null/empty "
                    "clears it, omit to leave unchanged. Only used when action is "
                    "not given."
                )
            ),
        ] = None,
        recipient: Annotated[
            str | None,
            Field(
                description=(
                    'Optional new recipient (for audience="personal"). Only '
                    "used when action is not given."
                )
            ),
        ] = None,
        duplicate_check: Annotated[
            str | None,
            Field(
                description=(
                    'Optional new dedup strength — "off"/"browser"/'
                    '"network"/"once". Only used when action is not given.'
                )
            ),
        ] = None,
        allow_resume: Annotated[
            bool | None,
            Field(description="Optional new resume setting. Only used when action is not given."),
        ] = None,
        response_limit: Annotated[
            int | None,
            Field(description="Optional new response cap. Only used when action is not given."),
        ] = None,
        opens_at: Annotated[
            str | None,
            Field(
                description="Optional new ISO 8601 open time. Only used when action is not given."
            ),
        ] = None,
        closes_at: Annotated[
            str | None,
            Field(
                description=(
                    "Optional new ISO 8601 close time. Only used when "
                    "action is not given."
                )
            ),
        ] = None,
        prefill: Annotated[
            dict | None,
            Field(
                description="Optional new prefill answers. Only used when action is not given."
            ),
        ] = None,
    ) -> str:
        """Update a share link's policy, or perform a lifecycle action
        (pause/resume/close/rotate) via the `action` parameter.
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        try:
            if action == "rotate":
                result = await client.post(f"/shares/{share_id}/token")
                return dump_json_capped(result)
            body: dict = {}
            if action in _ACTION_TO_STATUS:
                body["status"] = _ACTION_TO_STATUS[action]
            elif action is not None:
                return error_envelope(
                    "invalid_argument",
                    f"Unknown action '{action}' — expected pause, resume, close, or rotate",
                    False,
                )
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
            return dump_json_capped(result)
        except FormsAPIError as e:
            return e.to_envelope()

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
    async def mspbots_forms_share_delete(
        share_id: Annotated[str, Field(description="Required share ID to delete.")],
        confirm: Annotated[
            bool, Field(description="Required — must be set to true to proceed.")
        ],
    ) -> str:
        """Delete a share link. Collected responses are preserved — they
        still have analytical value even after the link is gone.

        ⚠️ DESTRUCTIVE. Requires confirm=true.
        """
        if not confirm:
            return error_envelope(
                "invalid_argument", "Destructive operation requires confirm=true", False
            )
        client = client_factory()
        if client is None:
            return NO_TOKEN
        try:
            result = await client.delete(f"/shares/{share_id}")
            return dump_json_capped(result)
        except FormsAPIError as e:
            return e.to_envelope()
