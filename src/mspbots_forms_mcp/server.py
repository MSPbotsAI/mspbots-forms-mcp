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
# Value is (access_token, host).
_gateway_creds_var: contextvars.ContextVar[tuple[str, str] | None] = contextvars.ContextVar(
    "forms_gateway_creds", default=None
)


def get_client_from_context(settings: Settings) -> FormsAPIClient | None:
    """Resolve the active FormsAPIClient for the current request context."""
    creds = _gateway_creds_var.get()
    if not creds:
        return None
    token, host = creds
    return FormsAPIClient(token, host)


class GatewayTokenMiddleware:
    """ASGI middleware.

    Reads X-MSP-Token and X-MSP-Host (both required) from request headers
    and stores them in the contextvar. Returns 401 if either is missing on
    /mcp requests.
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
        if not token or not host:
            response = JSONResponse(
                {
                    "error": "Missing credentials",
                    "message": (
                        "This server requires the X-MSP-Token header (Agent Platform "
                        "bearer access credential) and the X-MSP-Host header "
                        "(Forms/Survey API host)"
                    ),
                    "required_headers": ["X-MSP-Token", "X-MSP-Host"],
                    "optional_headers": [],
                },
                status_code=401,
            )
            await response(scope, receive, send)
            return

        ctx_token = _gateway_creds_var.set((token, host))
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
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    client_factory: Callable[[], FormsAPIClient | None] = lambda: get_client_from_context(settings)

    from .tools import responses, shares, surveys

    surveys.register(mcp, client_factory)
    shares.register(mcp, client_factory)
    responses.register(mcp, client_factory)

    return mcp
