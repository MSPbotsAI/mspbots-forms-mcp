# mspbots-forms-mcp

MCP server for the **MSPbots Forms/Survey API** — lets an Agent build surveys, publish them, manage share links, and read back/analyze responses.

> **Naming note:** this is not a third-party vendor integration. It wraps an **internal MSPbots App API** (survey builder + response collection feature) described in the API contract attached to [PRD-15818](https://app.clickup.com/t/2280862/PRD-15818). "MSP" in the header names below refers to the MSPbots Agent Platform itself, not an external MSP tool vendor. This follows the same pattern as `ticketqa-mcp` (PRD-14991) — an internal-App wrapper, not a `vendor-mcp-template` SOP project.

## ⚠️ Build status: unverified, built from a design doc only

This entire server was built from the API contract Leo Yang pasted into the PRD-15818 comment — **the actual backend repository was not read**. That comment is thorough (full endpoint list, request/response shapes, error codes, the exact 14 tool names/categories/annotations, a question-kind mapping table), so the implementation below should be functionally close, but:

- **No endpoint has been called against a real deployment.** The host/base URL for this API was never provided.
- The comment references three design docs that live in the actual repo (`survey-share-design.md`, `route-a-design.md`, `mcp-design.md`) and a real source file (`service/lib/question-kinds.ts`) — none of these were read. The question-kind mapping table below is transcribed from the comment's rendered table, not the source file.
- Leo's own suggestion was "让 AI 读仓库，MCP 和 API 就出来了" (have the AI read the repo and the MCP/API will fall out) — implying the intended workflow was to read the actual codebase, not build from the doc alone. This build takes the other path (treat the documented HTTP contract like any external API and wrap it with an HTTP client), which sidesteps needing repo access but means nothing here is verified against real code.
- **Do not treat this as production-ready** until it's been checked against either the real repo or a live test call.

## Overview

Implements the [Model Context Protocol](https://modelcontextprotocol.io/) (Streamable HTTP transport) and exposes the **14 tools** specified in the API contract:

| Category | Tool | Annotations |
|---|---|---|
| Survey | `survey_list`, `survey_get` | readOnly |
| | `survey_create`, `survey_publish` | — |
| | `survey_update` | idempotent |
| | `survey_delete` | **destructive**, requires `confirm=true` |
| | `survey_quick_publish` | composite: create + publish + share in one call |
| Share | `share_list`, `share_get` | readOnly |
| | `share_create` | — |
| | `share_update` | idempotent; `action` param (`pause`/`resume`/`close`/`rotate`) consolidates 4 lifecycle operations |
| | `share_delete` | **destructive**, requires `confirm=true` (responses preserved) |
| Response | `response_summary` | readOnly — call this first for analysis |
| | `response_list` | readOnly — columnar format, only when individual answers are needed |

Per the contract, the public respondent-facing endpoints (`/api/public/*` — unlock, save draft, submit) are **deliberately not exposed as tools**: an agent shouldn't be able to submit a survey on an anonymous respondent's behalf.

## Quick Start

### Docker (recommended)

```bash
docker compose up --build
```

The server starts on `http://localhost:8080`.

### Local (uv)

```bash
uv sync
python -m mspbots_forms_mcp
```

## Health Check

```bash
curl http://localhost:8080/health
# {"status": "ok", "service": "mspbots-forms-mcp", "transport": "http"}
```

No credentials are required for the health endpoint.

## 授权参数说明 (Authentication)

Every request to `/mcp` must include the following HTTP headers:

| Header | 类型 | 是否必填 | 默认值 | 枚举值 | 字段描述 | Example |
|---|---|---|---|---|---|---|
| `X-MSP-Token` | string | 必填 | 无 | 无(自由文本,JWT) | Agent Platform 已签发的访问凭证(平台 JWT)。本服务原样转发为下游请求的 `Authorization: Bearer <token>`。租户隔离按契约文档说明由下游服务端从 token 里解析,本服务不单独传租户 header(这点跟 `ticketqa-mcp` 不同,那边下游需要额外的 `X_Tenant_ID`——这次未经实测验证是否也需要,见下方 Known Gaps)。 | `X-MSP-Token: eyJhbGciOiJFZERTQSJ9...` |
| `X-MSP-Host` | string | 必填 | 无 | 无(自由文本,base URL) | Forms/Survey API 所在的 host。本服务会拼接 `/api/<endpoint>` 得到完整请求地址(与契约文档给出的路径一致)。契约文档未给出这个服务实际部署在哪,所以做成每请求传入,而不是写死。 | `X-MSP-Host: https://forms.mspbots.ai` |

Missing either header returns `401 Unauthorized`.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MCP_HTTP_PORT` | `8080` | Listening port |
| `MCP_HTTP_HOST` | `0.0.0.0` | Listening host |

## MCP Endpoint

```
POST http://localhost:8080/mcp
```

Connect your MCP client with:
- Transport: `http` (Streamable HTTP)
- Headers: `X-MSP-Token`, `X-MSP-Host` (both required)

## Question DSL (for `survey_create` / `survey_update`)

Each question is a dict: `kind` (required), `title` (required), `required` (bool), plus kind-specific fields. Question `name`s (`q1`, `q2`, ...) are auto-assigned by the server in definition order.

| `kind` | SurveyJS type | Extra fields |
|---|---|---|
| `text` | `text` | `placeholder` |
| `textarea` | `comment` | `placeholder`, `rows` |
| `radio` | `radiogroup` | `choices` (required) |
| `checkbox` | `checkbox` | `choices` (required) |
| `dropdown` | `dropdown` | `choices` (required), `placeholder` |
| `rating` | `rating` | `steps`, `style` (`numbers`/`stars`/`smileys`), `lowLabel`, `highLabel` |
| `boolean` | `boolean` | `yesLabel`, `noLabel` |
| `date` | `text` + `inputType:date` | `earliest`, `latest` |

`showIf`: `{"question": "<earlier question name>", "operator": "is"/"isNot"/"greaterThan"/"atLeast"/"lessThan"/"atMost"/"contains"/"answered"/"empty", "value": ...}` — `question` can only reference an **earlier** question (server rejects forward/circular refs with `422`).

Multi-page surveys use `pages: [{title?, questions: [...]}]` instead of a flat `questions` list.

## Test Example

```bash
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "X-MSP-Token: <token>" \
  -H "X-MSP-Host: https://forms.mspbots.ai" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "survey_create",
      "arguments": {
        "title": "Customer satisfaction",
        "questions": [
          {"kind": "rating", "title": "Overall satisfaction", "required": true, "steps": 5, "lowLabel": "Poor", "highLabel": "Great"},
          {"kind": "radio", "title": "How did you hear about us?", "choices": ["Website", "Friend", "Ad"]}
        ]
      }
    }
  }'
```

## API Reference

- Source spec: API contract pasted into a comment on [PRD-15818](https://app.clickup.com/t/2280862/PRD-15818) by Leo Yang
- Parent program: [PRD-14513 — MSPbots MCP gateway](https://app.clickup.com/t/2280862/PRD-14513)

## Known Gaps / Implementation Notes

- **Nothing in this server has been tested against a real deployment.** No base URL/host was provided for the Forms/Survey API, and no test JWT was available. Every tool is a direct, literal translation of the documented contract — treat this as a first draft, not a verified implementation.
- **Auth model assumption carried over unverified from `ticketqa-mcp`'s precedent, then explicitly NOT applied here**: `ticketqa-mcp` needed an extra `X_Tenant_ID` header that its source spec never mentioned (only discovered by live testing). This contract explicitly states tenant ID is derived server-side from the JWT itself ("tenantId 从 token 取，永不从请求参数取"), so this server does **not** send a separate tenant header — but this has not been confirmed with a real call. If a live test 404s or 401s unexpectedly, check whether an undocumented tenant header is needed here too, the same way it was for TicketQA.
- `survey_quick_publish` is a composite tool (3 chained API calls: create → publish → share-create) with **no rollback** — if the second or third call fails, the survey and/or its published version will already exist. This is a client-side convenience, not an atomic server-side operation.
- `share_update`'s `action="rotate"` calls a genuinely different endpoint (`POST /api/shares/:shareId/token`) than the other three actions (`PATCH /api/shares/:shareId` with a `status` field) — this was inferred from the contract's description ("把四个生命周期动作收敛进一个 tool") rather than the contract giving an explicit combined-tool spec; the underlying two endpoints themselves are separately documented and that part is solid.
- The `question-kinds` mapping table above was transcribed from the ClickUp comment's rendered markdown table, not read from the actual `service/lib/question-kinds.ts` source file the comment says is authoritative — if the real file has since diverged from what was pasted into the comment, this table would be stale.
- `survey_update`'s interaction between `definition` and `questions`/`pages` when both are given is unspecified in the contract — this implementation includes both in the request body if both are passed, which may or may not be what the real server expects. Avoid combining them until confirmed.
