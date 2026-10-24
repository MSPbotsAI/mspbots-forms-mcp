# 工单索引

每张通过 mb-ticket-pipeline 交付的工单一行。`状态` 反映的是该工单自己文档的冻结状态
（`frozen @ <sha>`），不是 ClickUp 上的状态。

| 工单 | 标题 | 文档 | 状态 | 涉及代码区域 |
|---|---|---|---|---|
| PRD-21379 | Forms MCP truncates option properties | [docs/tickets/PRD-21379.zh.md](tickets/PRD-21379.zh.md) | frozen @ 69ad26f | `tools/forms.py`、`tools/_survey_walk.py`（新增） |
