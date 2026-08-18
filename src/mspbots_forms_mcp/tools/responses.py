"""Response (submitted answers) read/analysis tools.

⚠️ UNVERIFIED — built entirely from the API contract pasted into ClickUp
PRD-15818 (per Leo Yang's comment), not by reading the actual backend repo.
See README Known Gaps.
"""

import json
from collections.abc import Callable
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import FormsAPIClient, FormsAPIError
from ._common import NO_TOKEN


def register(mcp: FastMCP, client_factory: Callable[[], FormsAPIClient | None]) -> None:
    @mcp.tool()
    async def mspbots_forms_response_summary(
        survey_id: Annotated[str, Field(description="Required survey ID.")],
    ) -> str:
        """Get per-question aggregated statistics for a survey's responses.

        Call this FIRST for any analysis question — it's a compact summary,
        not hundreds of raw response rows. Includes top-level totalStarted,
        totalCompleted, completionRate, and averageDurationSeconds fields, in
        addition to per-question stats — no separate call is needed for
        completion rate. Only counts completed responses in per-question
        stats (partial ones would skew distributions). Open-text questions
        ("textarea") only include up to 5 sample answers, not the full set.
        "checkbox" questions count each selected option separately, so
        option counts can sum to more than the response count.

        API: GET /api/surveys/:surveyId/responses/summary
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        try:
            result = await client.get(f"/surveys/{survey_id}/responses/summary")
            return json.dumps(result, indent=2)
        except FormsAPIError as e:
            return f"Error: {e}"

    @mcp.tool()
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
        """List individual survey responses, in a compact columnar format
        (columns + rows, not one repeated-key object per row) to save
        tokens. Only use this when you need to see actual individual
        answers — for aggregate analysis, use mspbots_forms_response_summary instead.

        Column names/order come from the survey's latest PUBLISHED version's
        definition — each response's answers pair with the definition that
        was live when it was collected, so column headers track the version
        that produced each batch of rows, not necessarily the current draft.

        API: GET /api/surveys/:surveyId/responses
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        params = {"status": status, "shareId": share_id, "cursor": cursor, "limit": limit}
        try:
            result = await client.get(f"/surveys/{survey_id}/responses", params=params)
            return json.dumps(result, indent=2)
        except FormsAPIError as e:
            return f"Error: {e}"
