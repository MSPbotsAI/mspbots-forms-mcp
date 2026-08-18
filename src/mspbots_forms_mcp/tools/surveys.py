"""Survey (form definition) tools.

⚠️ UNVERIFIED — built entirely from the API contract pasted into ClickUp
PRD-15818 (per Leo Yang's comment), not by reading the actual backend repo.
Endpoint paths/params/response shapes below match that doc; none have been
called against a real deployment. See README Known Gaps.
"""

from collections.abc import Callable
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .._json import dump_json_capped, error_envelope
from ..api_client import FormsAPIClient, FormsAPIError
from ._common import NO_TOKEN

# Hard safety ceiling on top of the underlying API's own documented cap
# (default 20, max 100) — we clamp to the tighter of the two (100).
_MAX_LIMIT = 100


def register(mcp: FastMCP, client_factory: Callable[[], FormsAPIClient | None]) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def mspbots_forms_survey_list(
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
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        if limit is not None:
            limit = min(limit, _MAX_LIMIT)
        params = {"status": status, "q": q, "cursor": cursor, "limit": limit}
        try:
            result = await client.get("/surveys", params=params)
            return dump_json_capped(result)
        except FormsAPIError as e:
            return e.to_envelope()

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def mspbots_forms_survey_get(
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
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        params = {"include": ",".join(include) if include else None}
        try:
            result = await client.get(f"/surveys/{survey_id}", params=params)
            return dump_json_capped(result)
        except FormsAPIError as e:
            return e.to_envelope()

    @mcp.tool()
    async def mspbots_forms_survey_create(
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
            return dump_json_capped(result)
        except FormsAPIError as e:
            return e.to_envelope()

    @mcp.tool(annotations=ToolAnnotations(idempotentHint=True))
    async def mspbots_forms_survey_update(
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
        mspbots_forms_survey_create); for spinning up a brand-new survey and getting it
        live in one step, use mspbots_forms_survey_quick_publish instead.

        Give either questions/pages (friendly DSL, full replace of the
        question set — same rules as mspbots_forms_survey_create) OR definition (raw
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
            return dump_json_capped(result)
        except FormsAPIError as e:
            return e.to_envelope()

    @mcp.tool()
    async def mspbots_forms_survey_publish(
        survey_id: Annotated[str, Field(description="Required survey ID to publish.")],
    ) -> str:
        """Publish a survey — creates an immutable version snapshot of its
        current draft. Share links bind to this version, so answers stay
        paired with the question set that was live when they were collected,
        even if the draft changes afterward.
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        try:
            result = await client.post(f"/surveys/{survey_id}/versions")
            return dump_json_capped(result)
        except FormsAPIError as e:
            return e.to_envelope()

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
    async def mspbots_forms_survey_delete(
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
        """
        if not confirm:
            return error_envelope(
                "invalid_argument", "Destructive operation requires confirm=true", False
            )
        client = client_factory()
        if client is None:
            return NO_TOKEN
        try:
            result = await client.delete(f"/surveys/{survey_id}")
            return dump_json_capped(result)
        except FormsAPIError as e:
            return e.to_envelope()

    @mcp.tool()
    async def mspbots_forms_survey_quick_publish(
        title: Annotated[str, Field(description="Required survey title.")],
        questions: Annotated[
            list[dict] | None,
            Field(description="Optional flat question list (DSL) — see mspbots_forms_survey_create."),
        ] = None,
        pages: Annotated[
            list[dict] | None,
            Field(description="Optional multi-page question list (DSL) — see mspbots_forms_survey_create."),
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
                    "use mspbots_forms_share_create afterward instead to set the required "
                    "passcode/recipient field — this tool doesn't accept those."
                )
            ),
        ] = "public",
    ) -> str:
        """Create a survey, publish it, and create a share link, in one call.

        Chains create + publish + share-create — no single backing
        endpoint, so a partial failure is NOT rolled back (survey/version
        may already exist even if share creation fails).

        Only for brand-new surveys — to edit an existing one, use
        mspbots_forms_survey_update instead.
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
                return error_envelope(
                    "upstream_error",
                    f"Survey created but no id in response: {dump_json_capped(survey)}",
                    False,
                )
            version = await client.post(f"/surveys/{survey_id}/versions")
            share = await client.post(
                f"/surveys/{survey_id}/shares", json_body={"audience": audience}
            )
            return dump_json_capped({"survey": survey, "version": version, "share": share})
        except FormsAPIError as e:
            return e.to_envelope()
