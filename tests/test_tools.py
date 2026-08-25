"""tools/list snapshot + error-envelope mapping tests.

No network calls: tool enumeration goes through FastMCP's in-process
list_tools(), and the error-code mapping is tested directly against
FormsAPIError, independent of any real HTTP request.
"""

import json

import pytest

from mspbots_forms_mcp.api_client import FormsAPIError
from mspbots_forms_mcp.config import Settings
from mspbots_forms_mcp.server import create_mcp_server

# required params + annotation hints expected for each of the 14 tools.
# Tool names carry the mspbots_forms_ prefix added in a prior rename pass —
# any signature change here is a breaking contract change (SOP §13).
EXPECTED_TOOLS = {
    "mspbots_forms_form_list": (set(), {"readOnlyHint": True}),
    "mspbots_forms_form_get": ({"form_id"}, {"readOnlyHint": True}),
    "mspbots_forms_form_create": ({"title"}, {}),
    "mspbots_forms_form_update": ({"form_id"}, {"idempotentHint": True}),
    "mspbots_forms_form_publish": ({"form_id"}, {}),
    "mspbots_forms_form_delete": ({"form_id", "confirm"}, {"destructiveHint": True}),
    "mspbots_forms_form_quick_publish": ({"title"}, {}),
    "mspbots_forms_share_list": ({"form_id"}, {"readOnlyHint": True}),
    "mspbots_forms_share_get": ({"share_id"}, {"readOnlyHint": True}),
    "mspbots_forms_share_create": ({"form_id"}, {}),
    "mspbots_forms_share_update": ({"share_id"}, {"idempotentHint": True}),
    "mspbots_forms_share_delete": ({"share_id", "confirm"}, {"destructiveHint": True}),
    "mspbots_forms_response_summary": ({"form_id"}, {"readOnlyHint": True}),
    "mspbots_forms_response_list": ({"form_id"}, {"readOnlyHint": True}),
}

# mspbots_forms_form_create/_update genuinely need their long DSL
# explanation (question `kind` values, showIf semantics) to let an agent
# construct valid nested arguments — an earlier blind usability test found
# that explanation was the most valuable part of these docstrings. They are
# intentionally exempt from the <=500 char budget (SOP §2.2 is "应当", not
# "必须") rather than gutted to fit.
_DESCRIPTION_LENGTH_EXEMPT = {"mspbots_forms_form_create", "mspbots_forms_form_update"}


@pytest.mark.asyncio
async def test_tools_list_snapshot():
    mcp = create_mcp_server(Settings())
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert names == set(EXPECTED_TOOLS), f"unexpected tool set: {names}"
    assert len(tools) == 14

    by_name = {t.name: t for t in tools}
    for name, (expected_required, expected_annotations) in EXPECTED_TOOLS.items():
        tool = by_name[name]
        required = set(tool.inputSchema.get("required", []))
        assert required == expected_required, f"{name}: required={required}"

        ann = tool.annotations
        for hint, value in expected_annotations.items():
            actual = getattr(ann, hint, None) if ann is not None else None
            assert actual == value, f"{name}: {hint}={actual}, expected {value}"
        if not expected_annotations:
            # No semantic hint expected (pure create/publish action) — but
            # still confirm none of the hints were set by accident.
            if ann is not None:
                assert not ann.readOnlyHint
                assert not ann.destructiveHint
                assert not ann.idempotentHint

        first_line = (tool.description or "").strip().splitlines()[0]
        assert len(first_line) <= 100, f"{name}: first line too long: {first_line!r}"

        if name not in _DESCRIPTION_LENGTH_EXEMPT:
            assert len(tool.description or "") <= 500, f"{name}: description too long"


@pytest.mark.asyncio
async def test_service_instructions_present_and_bounded():
    mcp = create_mcp_server(Settings())
    assert mcp.instructions
    assert len(mcp.instructions) <= 1500


@pytest.mark.parametrize(
    "status_code,expected_code,expected_retryable",
    [
        (0, "upstream_error", True),
        (400, "invalid_argument", False),
        (401, "unauthorized", False),
        (403, "unauthorized", False),
        (404, "not_found", False),
        (422, "invalid_argument", False),
        (429, "rate_limited", True),
        (500, "upstream_error", True),
        (503, "upstream_error", True),
    ],
)
def test_error_envelope_mapping(status_code, expected_code, expected_retryable):
    err = FormsAPIError(status_code, "some_domain_code", "boom")
    envelope = json.loads(err.to_envelope())
    assert envelope["error"]["code"] == expected_code
    assert envelope["error"]["retryable"] is expected_retryable
    assert "boom" in envelope["error"]["message"]


def test_error_envelope_without_domain_code():
    err = FormsAPIError(404, None, "not there")
    envelope = json.loads(err.to_envelope())
    assert envelope["error"]["code"] == "not_found"
    assert envelope["error"]["message"] == "not there"
