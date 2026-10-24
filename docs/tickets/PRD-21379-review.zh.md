# PRD-21379 · 代码评审

状态: 冻结 @ fbf001d

## 第 1 轮 · 2026-10-24 · 评审 dev01.mbagent/PRD-21379 @ fbf001d（基线 main @ 4066e70）

结论: 通过

### 评审范围

diff `4066e70...fbf001d`：`src/mspbots_forms_mcp/tools/forms.py`、`src/mspbots_forms_mcp/tools/_survey_walk.py`（新增）、`tests/test_tools.py`，以及 `docs/`（工单文档、ac.json、模块文档、索引）。没有改动超出技术设计「改动清单」列出的文件。

### 执行过的核实

- 在工作分支 HEAD（`fbf001d`）上跑了 `uv run pytest -q`：`25 passed, 1 failed`——与自测记录声称的数字完全一致。唯一失败项是 `tests/test_tools.py::test_tools_list_snapshot`（`mspbots_forms_form_delete` 描述过长），与本单改动的 `form_get`/`_survey_walk` 无关。
- 另开一个独立 worktree，在基线 `main@4066e70` 上跑同一条命令：`20 passed, 1 failed`，同一条失败用例、同一条断言。确认该失败是基线即红、与本次改动无关，不是本次合入引入的回归——与文档自己给出的 baseline/final diff 结论一致，0 回归。
- 完整读了 `src/mspbots_forms_mcp/_json.py` 的 `dump_json_capped`，确认它的顶层列表截断机制（挑最大的列表值字段、二分查找最大前缀、`truncated`/`truncated_field`/`original_count` 三个字段）与 AC2 用例、以及技术设计「字段铺平到顶层」的依据完全吻合。
- 用 `git ls-remote --heads` 确认该仓库没有 `int`/`INT` 分支（只有 `main`、`fix/x-api-key-passthrough`、以及各单的 `dev01.mbagent/*` 分支）——与「交接」一节的记录一致。
- 抽查了 `docs/modules/forms-tools.md` 的 `path:line` 引用与实际文件的对照（函数定义实际在 `forms.py:61`，文档写的是 `forms.py:60-126`；`_survey_walk.py` 实际在 `:13`，文档写的是 `:14-28`）——两处都差一行（大概率是从装饰器/文档字符串行数起算的），不影响结论的成立。
- 确认中英文档（`PRD-21379.md`/`.zh.md`、`forms-tools.md`/`.zh.md`）小节结构逐节一一对应。
- 确认工作分支上全部 4 个提交（`2d5f312`、`14db748`、`69ad26f`、`fbf001d`）的 author 和 committer 都是 `Dev01.MBAgent <dev01.mbagent@mspbots.ai>`。

### 发现

1. [suggestion] `src/mspbots_forms_mcp/tools/forms.py:126` —— 响应是这样拼的：`{"form_id": form_id, "field_id": field_id, **question}`。如果某个 SurveyJS 元素本身带了字面意义上的 `"form_id"` 或 `"field_id"` 键（标准 schema 里目前没有这两个键，没有已知的真实触发场景），`**question` 展开会把这两个标识字段悄悄覆盖成问题对象自己的值。把顺序换成 `{**question, "form_id": form_id, "field_id": field_id}` 能让标识字段永远赢，且没有代价。不算 must-fix：当前实现完全照技术设计规定的形状写的，也没有已知的真实元素会定义这两个键。

没有 must-fix 发现。范围、正确性、安全/多租户隔离（AC6）、以及测试证据，对照技术设计和 `REVIEW.md` 均核实通过。
