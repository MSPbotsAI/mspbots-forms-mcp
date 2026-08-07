from typing import Any

import httpx

# Per the API contract (PRD-15818 comment): private endpoints live at
# "https://<host>/api/<resource>" and public endpoints at
# "https://<host>/api/public/<resource>". No additional "/apps/<name>" prefix
# is documented for this service (unlike ticketqa-mcp's App API routing) —
# if that turns out to be wrong once tested against a real deployment, only
# this constant needs to change.
_API_PREFIX = "/api"


class FormsAPIError(Exception):
    def __init__(self, status_code: int, code: str | None, message: str, details: Any = None):
        self.status_code = status_code
        self.code = code
        self.details = details
        super().__init__(f"Forms API error {status_code} ({code}): {message}")


class FormsAPIClient:
    """Async httpx client wrapping the MSPbots Forms/Survey API.

    Auth: a single platform JWT, forwarded verbatim as
    "Authorization: Bearer <token>". Per the API contract, tenant isolation
    is derived server-side from this token ("tenantId 从 token 取，永不从请求
    参数取") — no separate tenant header is needed or sent, unlike
    ticketqa-mcp's undocumented X_Tenant_ID requirement for a different App.
    """

    def __init__(self, access_token: str, host: str):
        self._token = access_token
        self._base_url = host.rstrip("/") + _API_PREFIX

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

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
                    json=json_body,
                )
            except httpx.RequestError as e:
                raise FormsAPIError(0, None, f"{e or type(e).__name__} (url={self._base_url}{path})") from e
            return self._handle(resp)

    async def delete(self, path: str) -> Any:
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                resp = await client.delete(f"{self._base_url}{path}", headers=self._headers())
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
