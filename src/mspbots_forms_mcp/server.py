import contextvars
from collections.abc import Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .api_client import FormsAPIClient
from .config import Settings

# Per-request credential isolation via contextvars.
# GatewayTokenMiddleware sets this before the MCP handler runs.
# Python asyncio copies context per task, so concurrent SSE connections are isolated.
# Value is (access_token, host, tenant_id).
_gateway_creds_var: contextvars.ContextVar[tuple[str, str, str] | None] = contextvars.ContextVar(
    "forms_gateway_creds", default=None
)


def get_client_from_context(settings: Settings) -> FormsAPIClient | None:
    """Resolve the active FormsAPIClient for the current request context."""
    creds = _gateway_creds_var.get()
    if not creds:
        return None
    token, host, tenant_id = creds
    return FormsAPIClient(token, host, tenant_id)


class GatewayTokenMiddleware:
    """ASGI middleware.

    Reads X-MSP-Token, X-MSP-Host, and X-MSP-Tenant-Id (all required) from
    request headers and stores them in the contextvar. Returns 401 if any
    is missing on /mcp requests.

    X-MSP-Tenant-Id exists because live testing (2026-08-07, against
    agent.mspbots.ai) proved the APISIX app-routing gateway in front of the
    Forms API 404s ("App not found") unless the request carries an
    X_Tenant_ID *cookie* — the API contract's claim that tenant is derived
    purely from the JWT is only true past that gateway layer. This mirrors
    ticketqa-mcp's undocumented X-MSP-Tenant-Id header, except downstream
    this one gets sent as a cookie, not a header (see api_client.py).
    """

    def __init__(self, app: ASGIApp, settings: Settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not path.startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        token = request.headers.get("x-msp-token")
        host = request.headers.get("x-msp-host")
        tenant_id = request.headers.get("x-msp-tenant-id")
        if not token or not host or not tenant_id:
            response = JSONResponse(
                {
                    "error": "Missing credentials",
                    "message": (
                        "This server requires the X-MSP-Token header (Agent Platform "
                        "bearer access credential), the X-MSP-Host header (Forms/Survey "
                        "API host), and the X-MSP-Tenant-Id header (tenant ID, forwarded "
                        "downstream as the X_Tenant_ID cookie the app-routing gateway "
                        "requires)"
                    ),
                    "required_headers": ["X-MSP-Token", "X-MSP-Host", "X-MSP-Tenant-Id"],
                    "optional_headers": [],
                },
                status_code=401,
            )
            await response(scope, receive, send)
            return

        ctx_token = _gateway_creds_var.set((token, host, tenant_id))
        try:
            await self.app(scope, receive, send)
        finally:
            _gateway_creds_var.reset(ctx_token)


def create_mcp_server(settings: Settings) -> FastMCP:
    """Build the FastMCP server instance and register all Forms tools."""
    # DNS-rebinding protection is a browser-oriented safeguard that rejects
    # non-localhost Host headers with 421. Disable it so the server works
    # correctly behind a reverse proxy or docker network.
    mcp = FastMCP(
        name="mspbots-forms-mcp",
        instructions=(
            "MSPbots Forms/Survey is a survey builder and response-collection "
            "feature of the MSPbots platform: build surveys, publish them, "
            "manage share links, and read back/analyze what respondents "
            "submitted. Three tool groups: Survey (build/edit — "
            "mspbots_forms_survey_list/get/create/update/publish/delete, plus "
            "the composite mspbots_forms_survey_quick_publish which creates + "
            "publishes + shares a new survey in one call), Share (distribution "
            "policy for a published survey — mspbots_forms_share_list/get/"
            "create/update/delete; audience can be public/workspace/passcode/"
            "personal), and Response (mspbots_forms_response_summary for "
            "aggregated per-question stats — call this FIRST for analysis "
            "questions — and mspbots_forms_response_list for raw individual "
            "answers in a compact columnar format). Typical flow: "
            "survey_create -> survey_publish -> share_create to launch a "
            "survey, or survey_quick_publish to do all three at once; later, "
            "response_summary to see results, response_list only when "
            "individual answers are needed. Delete tools are destructive and "
            "require confirm=true. Public respondent-facing endpoints (submit/"
            "unlock) are intentionally not exposed as tools."
        ),
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    client_factory: Callable[[], FormsAPIClient | None] = lambda: get_client_from_context(settings)

    from .tools import responses, shares, surveys

    surveys.register(mcp, client_factory)
    shares.register(mcp, client_factory)
    responses.register(mcp, client_factory)

    return mcp
