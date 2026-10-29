"""Transfer tool tests (PRD-21397): strip_tenant_specific, version
validation (pure functions, no network), and the export/import tool pair
driven end-to-end against a fake FormsAPIClient (no real HTTP).

Maps to docs/tickets/PRD-21397.ac.json:
  TC1 -> test_export_then_import_roundtrip_is_field_for_field_identical
  TC4 -> test_choices_by_url_field_is_stripped_and_reported
  TC5 -> test_tenant_scoped_static_choices_are_stripped_and_reported
  TC6 -> test_ordinary_static_choices_are_not_over_stripped
  TC7 -> test_import_refuses_unsupported_export_version,
         test_import_refuses_missing_export_version
  TC8 -> test_import_returns_form_id_and_report
  TC9 -> test_tenant_a_identifiers_do_not_survive_unflagged
(TC2/TC3 are manual-only, see the ac.json "untested" entries and the
 Self-test section of docs/tickets/PRD-21397.md.)
"""

import copy
import json

import pytest

from mspbots_forms_mcp.tools._transfer_sanitize import (
    EXPORT_SCHEMA_VERSION,
    TransferError,
    strip_tenant_specific,
    validate_export_version,
)
from mspbots_forms_mcp.tools.transfer import register as register_transfer


# ---------------------------------------------------------------------------
# strip_tenant_specific / validate_export_version — pure functions, no network
# ---------------------------------------------------------------------------


def test_choices_by_url_field_is_stripped_and_reported():
    definition = {
        "pages": [
            {
                "elements": [
                    {
                        "type": "dropdown",
                        "name": "q1",
                        "title": "Client org",
                        "choicesByUrl": {"url": "https://example/api/orgs"},
                        "choices": ["placeholder-will-be-cleared"],
                    }
                ]
            }
        ]
    }
    stripped, report = strip_tenant_specific(definition)
    field = stripped["pages"][0]["elements"][0]
    assert "choicesByUrl" not in field
    assert field["choices"] == []
    assert report == [{"field": "q1", "reason": "data-source-bound (choicesByUrl)"}]


def test_tenant_scoped_static_choices_are_stripped_and_reported():
    definition = {
        "pages": [
            {
                "elements": [
                    {
                        "type": "dropdown",
                        "name": "client_org",
                        "title": "Client org",
                        "choices": [
                            {"value": "a", "text": "Acme", "tenantId": "t-123"},
                            {"value": "b", "text": "Beta", "tenantId": "t-456"},
                        ],
                    }
                ]
            }
        ]
    }
    stripped, report = strip_tenant_specific(definition)
    field = stripped["pages"][0]["elements"][0]
    assert field["choices"] == []
    assert len(report) == 1
    assert report[0]["field"] == "client_org"
    assert "tenantId" in report[0]["reason"]


def test_ordinary_static_choices_are_not_over_stripped():
    definition = {
        "pages": [
            {
                "elements": [
                    {
                        "type": "radio",
                        "name": "q2",
                        "title": "Favorite color",
                        "choices": ["Red", "Green", "Blue"],
                    }
                ]
            }
        ]
    }
    stripped, report = strip_tenant_specific(definition)
    field = stripped["pages"][0]["elements"][0]
    assert field["choices"] == ["Red", "Green", "Blue"]
    assert report == []


def test_strip_does_not_mutate_the_input():
    definition = {
        "pages": [{"elements": [{"name": "q1", "choicesByUrl": {"url": "x"}, "choices": ["a"]}]}]
    }
    original = copy.deepcopy(definition)
    strip_tenant_specific(definition)
    assert definition == original


def test_import_refuses_unsupported_export_version():
    with pytest.raises(TransferError) as exc_info:
        validate_export_version({"export_version": 2, "form": {}})
    assert "2" in exc_info.value.message
    assert exc_info.value.code == "invalid_argument"


def test_import_refuses_missing_export_version():
    with pytest.raises(TransferError) as exc_info:
        validate_export_version({"form": {}})
    assert "None" in exc_info.value.message or "none" in exc_info.value.message.lower()


def test_tenant_a_identifiers_do_not_survive_unflagged():
    tenant_a_ids = {"tenantId": "A-ONLY-111", "haloClientId": "A-ONLY-222", "rewstOrgId": "A-ONLY-333"}
    definition = {
        "pages": [
            {
                "elements": [
                    {
                        "name": "client_org",
                        "choices": [
                            {"value": "x", "text": "X", **tenant_a_ids},
                        ],
                    },
                    {
                        "name": "plain",
                        "choices": ["unrelated-string-choice"],
                    },
                ]
            }
        ]
    }
    stripped, report = strip_tenant_specific(definition)
    rendered = json.dumps(stripped)
    for value in tenant_a_ids.values():
        assert value not in rendered
    assert any(r["field"] == "client_org" for r in report)


# ---------------------------------------------------------------------------
# Tool-level: mspbots_forms_form_export / mspbots_forms_form_import driven
# through FastMCP's in-process call_tool, against a fake client (no network)
# — same no-network style as test_tools.py/test_middleware.py.
# ---------------------------------------------------------------------------


class _FakeClient:
    """Records calls and plays back canned responses — stands in for
    FormsAPIClient so these tests never touch the network."""

    def __init__(self, get_response=None, create_response=None, patch_response=None):
        self._get_response = get_response
        self._create_response = create_response
        self._patch_response = patch_response
        self.calls: list[tuple] = []

    async def get(self, path, params=None):
        self.calls.append(("get", path, params))
        return self._get_response

    async def post(self, path, json_body=None):
        self.calls.append(("post", path, json_body))
        return self._create_response

    async def patch(self, path, json_body):
        self.calls.append(("patch", path, json_body))
        return self._patch_response


def _make_mcp(client):
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(name="test-transfer")
    register_transfer(mcp, lambda: client)
    return mcp


SOURCE_FORM = {
    "id": "src-form-1",
    "title": "PRECICOM offboarding",
    "showProgressBar": True,
    "definition": {
        "pages": [
            {
                "name": "page1",
                "elements": [
                    {"type": "text", "name": "q1", "title": "Employee name"},
                    {"type": "radio", "name": "q2", "title": "Department", "choices": ["IT", "Sales"]},
                ],
            }
        ]
    },
}


@pytest.mark.asyncio
async def test_export_then_import_roundtrip_is_field_for_field_identical():
    # Export side: fake client returns the canned source form record.
    export_client = _FakeClient(get_response=SOURCE_FORM)
    export_mcp = _make_mcp(export_client)
    export_result = await export_mcp.call_tool("mspbots_forms_form_export", {"form_id": "src-form-1"})
    export_payload = json.loads(export_result[0][0].text)

    assert export_payload["export_version"] == EXPORT_SCHEMA_VERSION
    assert export_payload["form"] == SOURCE_FORM
    assert export_client.calls == [
        ("get", "/surveys/src-form-1", {"include": "definition,questions,versions"})
    ]

    # Import side: a fresh fake client (new tenant), fed the export payload.
    import_client = _FakeClient(
        create_response={"id": "new-form-9"}, patch_response={"id": "new-form-9"}
    )
    import_mcp = _make_mcp(import_client)
    import_result = await import_mcp.call_tool(
        "mspbots_forms_form_import", {"export_payload": export_payload}
    )
    import_payload = json.loads(import_result[0][0].text)

    assert import_payload["form_id"] == "new-form-9"
    assert import_payload["title"] == "PRECICOM offboarding (imported)"
    assert import_payload["report"] == []  # no data-source/tenant-scoped fields in this fixture

    # The definition handed to PATCH is field-for-field identical to the
    # source definition (no data-source/tenant-scoped choices to strip).
    patch_call = next(c for c in import_client.calls if c[0] == "patch")
    assert patch_call[2]["definition"] == SOURCE_FORM["definition"]


@pytest.mark.asyncio
async def test_import_returns_form_id_and_report():
    source_with_data_source_field = copy.deepcopy(SOURCE_FORM)
    source_with_data_source_field["definition"]["pages"][0]["elements"].append(
        {"type": "dropdown", "name": "q3", "title": "Org", "choicesByUrl": {"url": "x"}}
    )
    export_payload = {"export_version": EXPORT_SCHEMA_VERSION, "form": source_with_data_source_field}

    import_client = _FakeClient(create_response={"id": "new-form-9"}, patch_response={"id": "new-form-9"})
    import_mcp = _make_mcp(import_client)
    import_result = await import_mcp.call_tool(
        "mspbots_forms_form_import", {"export_payload": export_payload}
    )
    import_payload = json.loads(import_result[0][0].text)

    assert import_payload["form_id"] == "new-form-9"
    assert len(import_payload["report"]) == 1
    assert import_payload["report"][0]["field"] == "q3"


@pytest.mark.asyncio
async def test_import_refuses_unsupported_version_without_any_write_call():
    import_client = _FakeClient()
    import_mcp = _make_mcp(import_client)
    result = await import_mcp.call_tool(
        "mspbots_forms_form_import",
        {"export_payload": {"export_version": 2, "form": SOURCE_FORM}},
    )
    payload = json.loads(result[0][0].text)
    assert payload["error"]["code"] == "invalid_argument"
    assert "2" in payload["error"]["message"]
    assert import_client.calls == []  # no post/patch ever invoked
