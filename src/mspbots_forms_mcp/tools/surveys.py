"""Survey (form definition) tools.

⚠️ UNVERIFIED — built entirely from the API contract pasted into ClickUp
PRD-15818 (per Leo Yang's comment), not by reading the actual backend repo.
Endpoint paths/params/response shapes below match that doc; none have been
called against a real deployment. See README Known Gaps.
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
    async def survey_list(
        status: Annotated[
            str | None, Field(description='Optional filter — "draft", "published", or "archived".')
        ] = None,
        q: Annotated[str | None, Field(description="Optional fuzzy title match.")] = None,
        cursor: Annotated[
            str | None,
            Field(description="Optional pagination cursor from a previous response's nextCursor."),
        ] = None,
        limit: Annotated[
            int | None, Field(description="Optional page size (default 20, max 100 — server clamps).")
        ] = None,
    ) -> str:
        """List surveys (form summaries) for the current tenant.

        API: GET /api/surveys
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        params = {"status": status, "q": q, "cursor": cursor, "limit": limit}
        try:
            result = await client.get("/surveys", params=params)
            return json.dumps(result, indent=2)
        except FormsAPIError as e:
            return f"Error: {e}"

    @mcp.tool()
    async def survey_get(
        survey_id: Annotated[str, Field(description="Required survey ID.")],
        include: Annotated[
            list[str] | None,
            Field(
                description=(
                    'Optional list of extra sections to include: "definition" '
                    '(full SurveyJS JSON), "questions" (compact question list — '
                    "name/kind/title/required/showIf, much smaller than the full "
                    'definition), "versions" (published version list).'
                )
            ),
        ] = None,
    ) -> str:
        """Get a survey's details.

        By default only the base record is returned — no definition,
        questions, or versions — since the full definition can be several KB.

        API: GET /api/surveys/:surveyId
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        params = {"include": ",".join(include) if include else None}
        try:
            result = await client.get(f"/surveys/{survey_id}", params=params)
            return json.dumps(result, indent=2)
        except FormsAPIError as e:
            return f"Error: {e}"

    @mcp.tool()
    async def survey_create(
        title: Annotated[str, Field(description="Required survey title.")],
        questions: Annotated[
            list[dict] | None,
            Field(
                description=(
                    "Optional flat list of question dicts (see above). Use "
                    "this OR pages, not both — pages takes precedence if both given."
                )
            ),
        ] = None,
        pages: Annotated[
            list[dict] | None,
            Field(
                description=(
                    'Optional list of {"title": str?, "questions": [...]} for a '
                    "multi-page survey. Takes precedence over questions if both given."
                )
            ),
        ] = None,
        show_progress_bar: Annotated[
            bool | None, Field(description="Optional, whether to show a progress bar.")
        ] = None,
    ) -> str:
        """Create a new survey (draft, unpublished).

        Uses the friendly question DSL, not raw SurveyJS JSON — the server
        translates via a kind-mapping table. Supported `kind` values: "text",
        "textarea", "radio", "checkbox", "dropdown", "rating", "boolean",
        "date". Each question dict: kind (required), title (required),
        required (bool), plus kind-specific fields — "radio"/"checkbox"/
        "dropdown" need choices (list[str]); "rating" takes steps/style
        ("numbers"/"stars"/"smileys")/lowLabel/highLabel; "boolean" takes
        yesLabel/noLabel; "date" takes earliest/latest; "text"/"textarea"
        take placeholder (and "textarea" also rows). Optional showIf:
        {"question": "<earlier question's generated name>", "operator":
        "is"/"isNot"/"greaterThan"/"atLeast"/"lessThan"/"atMost"/"contains"/
        "answered"/"empty", "value": ...} — showIf.question can only
        reference an earlier question (server rejects forward/circular refs
        with 422). Question names (q1, q2, ...) are auto-assigned in order.

        API: POST /api/surveys
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        body: dict = {"title": title}
        if show_progress_bar is not None:
            body["showProgressBar"] = show_progress_bar
        if pages is not None:
            body["pages"] = pages
        elif questions is not None:
            body["questions"] = questions
        try:
            result = await client.post("/surveys", json_body=body)
            return json.dumps(result, indent=2)
        except FormsAPIError as e:
            return f"Error: {e}"

    @mcp.tool()
    async def survey_update(
        survey_id: Annotated[str, Field(description="Required survey ID.")],
        title: Annotated[str | None, Field(description="Optional new title.")] = None,
        show_progress_bar: Annotated[
            bool | None, Field(description="Optional new progress-bar setting.")
        ] = None,
        questions: Annotated[
            list[dict] | None,
            Field(
                description="Optional flat question list (DSL) — replaces the current question set."
            ),
        ] = None,
        pages: Annotated[
            list[dict] | None,
            Field(
                description=(
                    "Optional multi-page question list (DSL) — replaces the "
                    "current question set. Takes precedence over questions if both given."
                )
            ),
        ] = None,
        definition: Annotated[
            dict | None,
            Field(
                description=(
                    "Optional raw SurveyJS JSON, for edits not expressible "
                    "via the DSL. Mutually exclusive with questions/pages in "
                    "practice — the API contract doesn't specify what happens if "
                    "given together, so avoid combining them."
                )
            ),
        ] = None,
    ) -> str:
        """Update a survey's draft. Only affects the working draft — published
        versions are immutable snapshots unaffected by this call.

        Use this to edit a survey that already exists (e.g. one created via
        survey_create); for spinning up a brand-new survey and getting it
        live in one step, use survey_quick_publish instead.

        API: PATCH /api/surveys/:surveyId (idempotent)

        Give either questions/pages (friendly DSL, full replace of the
        question set — same rules as survey_create) OR definition (raw
        SurveyJS JSON, for advanced edits the DSL can't express — e.g.
        custom validators or choicesByUrl). If definition is given, it's a
        shallow merge — properties the DSL/Builder don't recognize are left
        untouched, never dropped.
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        body: dict = {}
        if title is not None:
            body["title"] = title
        if show_progress_bar is not None:
            body["showProgressBar"] = show_progress_bar
        if pages is not None:
            body["pages"] = pages
        elif questions is not None:
            body["questions"] = questions
        if definition is not None:
            body["definition"] = definition
        try:
            result = await client.patch(f"/surveys/{survey_id}", json_body=body)
            return json.dumps(result, indent=2)
        except FormsAPIError as e:
            return f"Error: {e}"

    @mcp.tool()
    async def survey_publish(
        survey_id: Annotated[str, Field(description="Required survey ID to publish.")],
    ) -> str:
        """Publish a survey — creates an immutable version snapshot of its
        current draft. Share links bind to this version, so answers stay
        paired with the question set that was live when they were collected,
        even if the draft changes afterward.

        API: POST /api/surveys/:surveyId/versions
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        try:
            result = await client.post(f"/surveys/{survey_id}/versions")
            return json.dumps(result, indent=2)
        except FormsAPIError as e:
            return f"Error: {e}"

    @mcp.tool()
    async def survey_delete(
        survey_id: Annotated[str, Field(description="Required survey ID to delete.")],
        confirm: Annotated[
            bool,
            Field(
                description=(
                    "Required — must be set to true to proceed. This tool "
                    "refuses to call the API if confirm is not explicitly true."
                )
            ),
        ],
    ) -> str:
        """Delete a survey — permanently removes it along with all its
        published versions, share links, AND collected responses.

        ⚠️ DESTRUCTIVE. Requires confirm=true.

        API: DELETE /api/surveys/:surveyId
        """
        if not confirm:
            return "Error: destructive operation requires confirm=true"
        client = client_factory()
        if client is None:
            return NO_TOKEN
        try:
            result = await client.delete(f"/surveys/{survey_id}")
            return json.dumps(result, indent=2)
        except FormsAPIError as e:
            return f"Error: {e}"

    @mcp.tool()
    async def survey_quick_publish(
        title: Annotated[str, Field(description="Required survey title.")],
        questions: Annotated[
            list[dict] | None,
            Field(description="Optional flat question list (DSL) — see survey_create."),
        ] = None,
        pages: Annotated[
            list[dict] | None,
            Field(description="Optional multi-page question list (DSL) — see survey_create."),
        ] = None,
        show_progress_bar: Annotated[
            bool | None, Field(description="Optional progress-bar setting.")
        ] = None,
        audience: Annotated[
            str,
            Field(
                description=(
                    'Share audience — "public", "workspace", "passcode", or '
                    '"personal" (default "public"). For "passcode" or "personal", '
                    "use share_create afterward instead to set the required "
                    "passcode/recipient field — this tool doesn't accept those."
                )
            ),
        ] = "public",
    ) -> str:
        """Convenience tool: create a survey, publish it, and create a share
        link, in one call. Composite tool implemented by chaining
        survey_create + survey_publish + a share-create call — there is no
        single backing REST endpoint for this; if any step fails partway,
        earlier steps are NOT rolled back (the survey/version may already
        exist even if share creation fails).

        Only for brand-new surveys — to edit questions/title on a survey
        that already exists, use survey_update instead.
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        create_body: dict = {"title": title}
        if show_progress_bar is not None:
            create_body["showProgressBar"] = show_progress_bar
        if pages is not None:
            create_body["pages"] = pages
        elif questions is not None:
            create_body["questions"] = questions
        try:
            survey = await client.post("/surveys", json_body=create_body)
            survey_id = survey.get("id") if isinstance(survey, dict) else None
            if not survey_id:
                return f"Error: survey created but no id in response: {json.dumps(survey)}"
            version = await client.post(f"/surveys/{survey_id}/versions")
            share = await client.post(
                f"/surveys/{survey_id}/shares", json_body={"audience": audience}
            )
            return json.dumps({"survey": survey, "version": version, "share": share}, indent=2)
        except FormsAPIError as e:
            return f"Error: {e}"
