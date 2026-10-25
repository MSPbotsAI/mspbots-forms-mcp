# 模块文档索引

`mspbots-forms-mcp` 的累积事实，按工具组/代码区域划分。设计或实现涉及本仓的工单前，
先读与工单 `Code Project` 和工单原话匹配的模块文档 —— 用法与维护方式见流水线的
`references/docs-tree.md`。

| 代码区域/工具组 | 文件 | 覆盖范围 |
|---|---|---|
| Form 工具（`mspbots_forms_form_*`） | [forms-tools.md](forms-tools.zh.md) | `src/mspbots_forms_mcp/tools/forms.py`、`src/mspbots_forms_mcp/tools/_survey_walk.py`、`src/mspbots_forms_mcp/_json.py`（所有工具共用的响应大小截断） |

尚未覆盖（还没有模块文档 —— 只在某张单的累积事实会因此丢失或与后续结论矛盾时才写一份，
不要为了「每个文件都有文档」而写）：

- Share 工具（`mspbots_forms_share_*`，`src/mspbots_forms_mcp/tools/shares.py`）
- Response 工具（`mspbots_forms_response_*`，`src/mspbots_forms_mcp/tools/responses.py`）
- 网关凭据中间件 / 租户隔离（`src/mspbots_forms_mcp/server.py`、`src/mspbots_forms_mcp/api_client.py`）
