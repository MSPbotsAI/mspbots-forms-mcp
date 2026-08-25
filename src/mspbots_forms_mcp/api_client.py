import asyncio
from typing import Any

import httpx

from ._json import error_envelope

_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_MAX_BACKOFF_SECONDS = 20.0

# The API contract (PRD-15818 comment) documents paths as bare "/api/<resource>",
# but live testing against agent.mspbots.ai showed the real gateway route is
# "/apps/app-forms/api/<resource>" (confirmed 2026-08-07 with a real PROD
# token) — same "/apps/<name>/api/..." convention as ticketqa-mcp, just not
# mentioned in the contract doc.
_API_PREFIX = "/apps/app-forms/api"

# One shared connection pool for the process lifetime. No credentials are
# ever stored on it — the token/tenant are passed per-request via headers/
# cookies, so this is safe to share across tenants/requests (see server.py's
# contextvar-based credential isolation, which is what actually keeps
# tenants apart).
_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True)
    return _http_client


# status_code -> (error code, retryable). status_code 0 means a network/
# connection-level failure (no response at all).
_STATUS_TO_CODE: dict[int, tuple[str, bool]] = {
    0: ("upstream_error", True),
    400: ("invalid_argument", False),
    401: ("unauthorized", False),
    403: ("unauthorized", False),
    404: ("not_found", False),
    422: ("invalid_argument", False),
    429: ("rate_limited", True),
}


def _classify(status_code: int) -> tuple[str, bool]:
    if status_code in _STATUS_TO_CODE:
        return _STATUS_TO_CODE[status_code]
    if status_code >= 500:
        return "upstream_error", True
    return "invalid_argument", False


class FormsAPIError(Exception):
    def __init__(self, status_code: int, code: str | None, message: str, details: Any = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(f"Forms API error {status_code} ({code}): {message}")

    def to_envelope(self) -> str:
        envelope_code, retryable = _classify(self.status_code)
        # self.code is the Forms API's own domain error code (e.g. a
        # validation-specific string), distinct from the SOP's fixed
        # vocabulary in envelope_code — surface both when available.
        message = f"[{self.code}] {self.message}" if self.code else self.message
        return error_envelope(envelope_code, message, retryable)


class FormsAPIClient:
    """Async httpx client wrapping the MSPbots Forms API.

    Auth: a platform JWT forwarded as "Authorization: Bearer <token>", PLUS
    a tenant ID sent as the "X_Tenant_ID" cookie. The API contract claimed
    tenant isolation is derived server-side from the JWT alone ("tenantId 从
    token 取，永不从请求参数取"), but live testing against agent.mspbots.ai
    (2026-08-07) proved that's only true once the request reaches the
    business logic — the APISIX app-routing gateway in front of it 404s
    ("App not found") without the X_Tenant_ID cookie, regardless of what's
    in the token. Isolated via curl: same token, only difference is this
    cookie, 404 -> 200. Same class of gap as ticketqa-mcp's undocumented
    X_Tenant_ID requirement, except there it's an HTTP header and here it's
    a cookie.

    Reuses the module-level connection pool (see _get_http_client) across
    every call made through this instance, rather than opening a new
    connection per request.
    """

    def __init__(self, access_token: str, host: str, tenant_id: str):
        self._token = access_token
        self._tenant_id = tenant_id
        self._base_url = host.rstrip("/") + _API_PREFIX

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _cookies(self) -> dict[str, str]:
        return {"X_Tenant_ID": self._tenant_id}

    def _clean_params(self, params: dict | None) -> dict:
        if not params:
            return {}
        return {k: v for k, v in params.items() if v is not None}

    async def get(self, path: str, params: dict | None = None) -> Any:
        return await self._request("GET", path, params=self._clean_params(params))

    async def post(self, path: str, json_body: Any = None) -> Any:
        return await self._request("POST", path, json_body=json_body)

    async def patch(self, path: str, json_body: Any) -> Any:
        return await self._request("PATCH", path, json_body=json_body)

    async def delete(self, path: str) -> Any:
        return await self._request("DELETE", path)

    async def _request(
        self, method: str, path: str, params: dict | None = None, json_body: Any = None
    ) -> Any:
        client = _get_http_client()
        url = f"{self._base_url}{path}"
        headers = self._headers()
        cookies = self._cookies()

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = await client.request(
                    method,
                    url,
                    headers=headers,
                    cookies=cookies,
                    params=params,
                    json=json_body,
                )
            except httpx.RequestError as e:
                last_exc = e
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(min(2**attempt, _MAX_BACKOFF_SECONDS))
                    continue
                raise FormsAPIError(0, None, f"{e or type(e).__name__} (url={url})") from e

            if resp.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES:
                delay = self._retry_delay(resp, attempt)
                await asyncio.sleep(delay)
                continue

            return self._handle(resp)

        # Unreachable in practice (loop always returns or raises above), but
        # keeps type checkers happy and guards against future edits.
        if last_exc:
            raise FormsAPIError(0, None, f"{last_exc}") from last_exc
        raise FormsAPIError(0, None, "request failed with no response")

    def _retry_delay(self, resp: httpx.Response, attempt: int) -> float:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), _MAX_BACKOFF_SECONDS)
            except ValueError:
                pass
        return min(2**attempt, _MAX_BACKOFF_SECONDS)

    def _handle(self, resp: httpx.Response) -> Any:
        if resp.status_code == 204:
            return {"ok": True, "status": 204}
        try:
            body = resp.json()
        except ValueError:
            body = {"raw_response": resp.text}
        if resp.status_code >= 400:
            err = body.get("error") if isinstance(body, dict) else None
            code = err.get("code") if isinstance(err, dict) else None
            message = err.get("message") if isinstance(err, dict) else str(body)
            details = err.get("details") if isinstance(err, dict) else None
            raise FormsAPIError(resp.status_code, code, message or "unknown error", details)
        return body
