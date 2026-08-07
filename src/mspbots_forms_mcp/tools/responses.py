"""Response (submitted answers) read/analysis tools.

⚠️ UNVERIFIED — built entirely from the API contract pasted into ClickUp
PRD-15818 (per Leo Yang's comment), not by reading the actual backend repo.
See README Known Gaps.
"""

import json
from collections.abc import Callable

from mcp.server.fastmcp import FastMCP

from ..api_client import FormsAPIClient, FormsAPIError
from ._common import NO_TOKEN


def register(mcp: FastMCP, client_factory: Callable[[], FormsAPIClient | None]) -> None:
    @mcp.tool()
    async def response_summary(survey_id: str) -> str:
        """Get per-question aggregated statistics for a survey's responses.

        Call this FIRST for any analysis question — it's a compact summary,
        not hundreds of raw response rows. Only counts completed responses
        (partial ones would skew distributions). Open-text questions
        ("textarea") only include up to 5 sample answers, not the full set.
        "checkbox" questions count each selected option separately, so
        option counts can sum to more than the response count.

        API: GET /api/surveys/:surveyId/responses/summary

        Args:
            survey_id: Required survey ID.
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
    async def response_list(
        survey_id: str,
        status: str | None = None,
        share_id: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> str:
        """List individual survey responses, in a compact columnar format
        (columns + rows, not one repeated-key object per row) to save
        tokens. Only use this when you need to see actual individual
        answers — for aggregate analysis, use response_summary instead.

        Column names/order come from the survey's latest PUBLISHED version's
        definition — each response's answers pair with the definition that
        was live when it was collected, so column headers track the version
        that produced each batch of rows, not necessarily the current draft.

        API: GET /api/surveys/:surveyId/responses

        Args:
            survey_id: Required survey ID.
            status: Optional filter — "partial" or "completed".
            share_id: Optional filter — only responses collected via this
                specific share link.
            cursor: Optional pagination cursor from a previous response's nextCursor.
            limit: Optional page size, max 100.
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
