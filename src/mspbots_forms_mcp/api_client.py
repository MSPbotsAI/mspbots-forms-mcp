from typing import Any

import httpx

# The API contract (PRD-15818 comment) documents paths as bare "/api/<resource>",
# but live testing against agent.mspbots.ai showed the real gateway route is
# "/apps/app-forms/api/<resource>" (confirmed 2026-08-07 with a real PROD
# token) — same "/apps/<name>/api/..." convention as ticketqa-mcp, just not
# mentioned in the contract doc.
_API_PREFIX = "/apps/app-forms/api"


class FormsAPIError(Exception):
    def __init__(self, status_code: int, code: str | None, message: str, details: Any = None):
        self.status_code = status_code
        self.code = code
        self.details = details
        super().__init__(f"Forms API error {status_code} ({code}): {message}")


class FormsAPIClient:
    """Async httpx client wrapping the MSPbots Forms/Survey API.

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
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                resp = await client.get(
                    f"{self._base_url}{path}",
                    headers=self._headers(),
                    cookies=self._cookies(),
                    params=self._clean_params(params),
                )
            except httpx.RequestError as e:
                raise FormsAPIError(0, None, f"{e or type(e).__name__} (url={self._base_url}{path})") from e
            return self._handle(resp)

    async def post(self, path: str, json_body: Any = None) -> Any:
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                resp = await client.post(
                    f"{self._base_url}{path}",
                    headers=self._headers(),
                    cookies=self._cookies(),
                    json=json_body,
                )
            except httpx.RequestError as e:
                raise FormsAPIError(0, None, f"{e or type(e).__name__} (url={self._base_url}{path})") from e
            return self._handle(resp)

    async def patch(self, path: str, json_body: Any) -> Any:
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                resp = await client.patch(
                    f"{self._base_url}{path}",
                    headers=self._headers(),
                    cookies=self._cookies(),
                    json=json_body,
                )
            except httpx.RequestError as e:
                raise FormsAPIError(0, None, f"{e or type(e).__name__} (url={self._base_url}{path})") from e
            return self._handle(resp)

    async def delete(self, path: str) -> Any:
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                resp = await client.delete(
                    f"{self._base_url}{path}", headers=self._headers(), cookies=self._cookies()
                )
            except httpx.RequestError as e:
                raise FormsAPIError(0, None, f"{e or type(e).__name__} (url={self._base_url}{path})") from e
            return self._handle(resp)

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
