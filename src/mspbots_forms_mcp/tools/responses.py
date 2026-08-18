"""Response (submitted answers) read/analysis tools.

⚠️ UNVERIFIED — built entirely from the API contract pasted into ClickUp
PRD-15818 (per Leo Yang's comment), not by reading the actual backend repo.
See README Known Gaps.
"""

from collections.abc import Callable
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .._json import dump_json_capped
from ..api_client import FormsAPIClient, FormsAPIError
from ._common import NO_TOKEN

# Hard safety ceiling on top of the underlying API's own documented cap
# (default 20, max 100) — we clamp to the tighter of the two (100).
_MAX_LIMIT = 100


def register(mcp: FastMCP, client_factory: Callable[[], FormsAPIClient | None]) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def mspbots_forms_response_summary(
        survey_id: Annotated[str, Field(description="Required survey ID.")],
    ) -> str:
        """Get per-question aggregated statistics for a survey's responses.

        Call this FIRST for analysis — a compact summary, not raw rows.
        Includes totalStarted, totalCompleted, completionRate, and
        averageDurationSeconds, plus per-question stats (completed
        responses only). "textarea" caps sample answers at 5; "checkbox"
        counts can exceed the response count (multi-select).

        API: GET /api/surveys/:surveyId/responses/summary
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        try:
            result = await client.get(f"/surveys/{survey_id}/responses/summary")
            return dump_json_capped(result)
        except FormsAPIError as e:
            return e.to_envelope()

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def mspbots_forms_response_list(
        survey_id: Annotated[str, Field(description="Required survey ID.")],
        status: Annotated[
            str | None, Field(description='Optional filter — "partial" or "completed".')
        ] = None,
        share_id: Annotated[
            str | None,
            Field(
                description="Optional filter — only responses collected via this specific share link."
            ),
        ] = None,
        cursor: Annotated[
            str | None,
            Field(description="Optional pagination cursor from a previous response's nextCursor."),
        ] = None,
        limit: Annotated[
            int | None, Field(description="Optional page size (default 20, max 100).")
        ] = None,
    ) -> str:
        """List individual survey responses in a compact columnar format
        (columns + rows, not one object per row). Only for actual
        individual answers — for aggregates use mspbots_forms_response_summary.

        Columns come from the survey's latest PUBLISHED version's
        definition, so headers track the version live when each batch of
        rows was collected, not necessarily the current draft.

        API: GET /api/surveys/:surveyId/responses
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        if limit is not None:
            limit = min(limit, _MAX_LIMIT)
        params = {"status": status, "shareId": share_id, "cursor": cursor, "limit": limit}
        try:
            result = await client.get(f"/surveys/{survey_id}/responses", params=params)
            return dump_json_capped(result)
        except FormsAPIError as e:
            return e.to_envelope()
