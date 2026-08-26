# mspbots-forms-mcp

MCP server for the **MSPbots Forms API** — lets an Agent build forms, publish them, manage share links, and read back/analyze responses.

> **Naming note:** this is not a third-party vendor integration. It wraps an **internal MSPbots App API** (form builder + response collection feature — the underlying API's own paths/fields still say "survey", e.g. `/surveys`, `surveyVersionId`; the tools here present it to agents as "form" instead) described in the API contract attached to [PRD-15818](https://app.clickup.com/t/2280862/PRD-15818). "MSP" in the header names below refers to the MSPbots Agent Platform itself, not an external MSP tool vendor. This follows the same pattern as `ticketqa-mcp` (PRD-14991) — an internal-App wrapper, not a `vendor-mcp-template` SOP project.

## ✅ Build status: read tools verified against real PROD data (2026-08-07)

This server was built from the API contract Leo Yang pasted into the PRD-15818 comment — **the actual backend repository was not read**. It's since been tested end-to-end (real MCP handshake + tool call, not just curl) against the real production deployment:

- **Real host found by trial**: the contract didn't say where this API is deployed. A working browser request (captured from the actual `app-forms` UI) revealed it: `https://agent.mspbots.ai/apps/app-forms/api/...` — a `/apps/<name>/api/...` prefix the contract never mentioned.
- **UPDATE 2026-08-26**: `app-forms` now also has a real INT deployment. A direct request to `agentint.mspbots.ai/apps/app-forms/api/surveys` returns real 200 data (previously 404'd — see git history for the original "PROD-only" finding, which was accurate as of 2026-08-07/08-24 but is no longer current). A real `mspbots_forms_form_list` call through the gateway with an INT tenant now returns that same INT-only data, not PROD data — confirmed the gateway's `X-MSP-Host` routing for `mspbots-forms` now correctly follows environment rather than being hardcoded to PROD. **Practical effect**: write-tool testing against INT is now safe (touches real INT data, not PROD) — re-verify this isn't stale again before assuming it, the same way this note itself corrected a stale assumption.
- **Undocumented tenant requirement, confirmed by isolation test**: the contract claims tenant is derived purely from the JWT ("tenantId 从 token 取，永不从请求参数取"). Live testing proved that's only true past the app-routing gateway — without an `X_Tenant_ID` **cookie** (not a header!), the same token/path 404s ("App not found"); adding just that cookie (nothing else changed) turns it into 200. Same class of gap `ticketqa-mcp` hit (there it was an undocumented header; here it's a cookie).
- **Verified working with real data**: `mspbots_forms_form_list`, `mspbots_forms_form_get` (with `include=questions`), `mspbots_forms_response_summary`, `mspbots_forms_share_list` — all returned real, correctly-shaped data for an actual PROD form (`Untitled survey`, id `9030b62e-4000-4e61-ae98-2b7285c86ea6` — that's the real record's own title, from before this repo's tool-facing terminology was changed to "form").
- **Not yet tested**: any write tool (`mspbots_forms_form_create/update/publish/delete/quick_publish`, `mspbots_forms_share_create/update/delete`) — deliberately not exercised against PROD without explicit sign-off, since they'd create/mutate/delete real data. `mspbots_forms_response_list` also untested (the one test form has 0 responses).
- The 3 referenced design docs (`survey-share-design.md`, `route-a-design.md`, `mcp-design.md`) and the real `service/lib/question-kinds.ts` source were still not read — the question-kind table below remains transcribed from the comment, not source-verified. The `text`/`textarea` kinds that were tested match, though.

## Overview

Implements the [Model Context Protocol](https://modelcontextprotocol.io/) (Streamable HTTP transport) and exposes the **14 tools** specified in the API contract, covering three areas — **building/editing forms**, **managing how they're shared**, and **reading back what respondents submitted**. An agent should reach for this MCP for requests like:

- "Build me a quick customer-satisfaction form and get me a link to send out" → `mspbots_forms_form_quick_publish`
- "I need to tweak the wording on question 3 of the NPS form" → `mspbots_forms_form_update`
- "How many people finished the NPS form, what's the average score?" → `mspbots_forms_response_summary`
- "Pause this share link for a bit, we're getting too many responses right now" → `mspbots_forms_share_update` with `action="pause"`
- "Show me the actual open-text comments people left, not just the stats" → `mspbots_forms_response_list`
- "This form's done — delete it and everything tied to it" → `mspbots_forms_form_delete`

| Category | Tool | Annotations |
|---|---|---|
| Form | `mspbots_forms_form_list`, `mspbots_forms_form_get` | readOnly |
| | `mspbots_forms_form_create`, `mspbots_forms_form_publish` | — |
| | `mspbots_forms_form_update` | idempotent |
| | `mspbots_forms_form_delete` | **destructive**, requires `confirm=true` |
| | `mspbots_forms_form_quick_publish` | composite: create + publish + share in one call |
| Share | `mspbots_forms_share_list`, `mspbots_forms_share_get` | readOnly |
| | `mspbots_forms_share_create` | — |
| | `mspbots_forms_share_update` | idempotent; `action` param (`pause`/`resume`/`close`/`rotate`) consolidates 4 lifecycle operations |
| | `mspbots_forms_share_delete` | **destructive**, requires `confirm=true` (responses preserved) |
| Response | `mspbots_forms_response_summary` | readOnly — call this first for analysis |
| | `mspbots_forms_response_list` | readOnly — columnar format, only when individual answers are needed |

Per the contract, the public respondent-facing endpoints (`/api/public/*` — unlock, save draft, submit) are **deliberately not exposed as tools**: an agent shouldn't be able to submit a form on an anonymous respondent's behalf.

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
# {"status": "ok"}
```

No credentials are required for the health endpoint.

## 授权参数说明 (Authentication)

Every request to `/mcp` must include the following HTTP headers:

| Header | 类型 | 是否必填 | 默认值 | 枚举值 | 字段描述 | Example |
|---|---|---|---|---|---|---|
| `X-MSP-Token` | string | 必填 | 无 | 无(自由文本,JWT) | Agent Platform 已签发的访问凭证(平台 JWT)。本服务原样转发为下游请求的 `Authorization: Bearer <token>`。 | `X-MSP-Token: eyJhbGciOiJFZERTQSJ9...` |
| `X-MSP-Host` | string | 必填 | 无 | 无(自由文本,base URL) | Forms API 所在的 host。本服务会拼接 `/apps/app-forms/api/<endpoint>` 得到完整请求地址(**实测确认**的真实路径,契约文档只写了裸的 `/api/<endpoint>`,没提这个 `/apps/app-forms` 前缀)。**2026-08-26更新**：此前记录"App 只部署在 PROD、网关固定转发到 PROD"已过时——实测 `app-forms` 现在也有真实 INT 部署，走网关的请求会正确按环境路由（INT 租户拿到的是 INT 数据），不再固定转发 PROD。 | `X-MSP-Host: https://agent.mspbots.ai` |
| `X-MSP-Tenant-Id` | string | 必填 | 无 | 无(自由文本,UUID) | 租户 ID。契约文档说租户完全从 token 解析、不需要额外传——**实测证明这只对业务层成立**:APISIX 的 app 路由网关在拿到租户信息之前就会 404("App not found"),必须靠这个值。本服务把它转发为下游请求的 **`X_Tenant_ID` cookie**(不是 header——这是实测才发现的,契约完全没提)。 | `X-MSP-Tenant-Id: e9f794fe-a6b4-4f35-bd2f-fcd19c5cc308` |

Missing any of the three headers returns `401 Unauthorized`.

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
- Headers: `X-MSP-Token`, `X-MSP-Host`, `X-MSP-Tenant-Id` (all required)

## Question DSL (for `mspbots_forms_form_create` / `mspbots_forms_form_update`)

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

Multi-page forms use `pages: [{title?, questions: [...]}]` instead of a flat `questions` list.

## Test Example

```bash
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "X-MSP-Token: <token>" \
  -H "X-MSP-Host: https://agent.mspbots.ai" \
  -H "X-MSP-Tenant-Id: <tenant-id>" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "mspbots_forms_form_create",
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

- **Verified 2026-08-07 against real PROD data**: `mspbots_forms_form_list`, `mspbots_forms_form_get` (incl. `include=questions`), `mspbots_forms_response_summary`, `mspbots_forms_share_list` all returned correctly-shaped real data for a live PROD form. The real host (`https://agent.mspbots.ai/apps/app-forms/api/...`) and the undocumented `X-MSP-Tenant-Id` → `X_Tenant_ID` cookie requirement (see Auth table above) were both discovered this way, not from the contract doc.
- **Write tools are still untested**: `mspbots_forms_form_create/update/publish/delete/quick_publish` and `mspbots_forms_share_create/update/delete` have not been called — deliberately avoided mutating real PROD data without explicit sign-off. `mspbots_forms_response_list` is also untested (the one available test form has 0 responses to list). Test these against a disposable form before trusting them.
- `mspbots_forms_form_quick_publish` is a composite tool (3 chained API calls: create → publish → share-create) with **no rollback** — if the second or third call fails, the form and/or its published version will already exist. This is a client-side convenience, not an atomic server-side operation.
- `mspbots_forms_share_update`'s `action="rotate"` calls a genuinely different endpoint (`POST /api/shares/:shareId/token`) than the other three actions (`PATCH /api/shares/:shareId` with a `status` field) — this was inferred from the contract's description ("把四个生命周期动作收敛进一个 tool") rather than the contract giving an explicit combined-tool spec; the underlying two endpoints themselves are separately documented and that part is solid.
- The `question-kinds` mapping table above was transcribed from the ClickUp comment's rendered markdown table, not read from the actual `service/lib/question-kinds.ts` source file the comment says is authoritative. The `text`/`textarea` kinds were confirmed correct against a real form; the other 6 kinds (`radio`/`checkbox`/`dropdown`/`rating`/`boolean`/`date`) are still unverified.
- `mspbots_forms_form_update`'s interaction between `definition` and `questions`/`pages` when both are given is unspecified in the contract — this implementation includes both in the request body if both are passed, which may or may not be what the real server expects. Avoid combining them until confirmed.
- **`app-forms` App deployment (UPDATED 2026-08-26)**: this used to be PROD-only (a direct request to `agentint.mspbots.ai/apps/app-forms/api/...` 404'd, and the gateway hardcoded `X-MSP-Host` to PROD's `agent.mspbots.ai` regardless of environment — confirmed live 2026-08-24). That's no longer the case: `app-forms` now has a real INT deployment, and a real `mspbots_forms_form_list` call through the gateway with an INT tenant returns real INT data, not PROD data (confirmed live 2026-08-26). Don't assume either state without re-checking — this exact assumption already went stale once.
- **Terminology note**: tool names/descriptions/params say "form" (e.g. `form_id`, `mspbots_forms_form_create`), matching the "MSPbots Forms" product name — but the underlying REST API's own paths and JSON fields still say "survey" (`/surveys`, `surveyVersionId`) and are left as-is, since those are the real backend's wire contract, not something this MCP controls.
