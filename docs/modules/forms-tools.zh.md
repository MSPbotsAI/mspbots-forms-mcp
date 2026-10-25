# Form 工具（`mspbots_forms_form_*`）

覆盖 `src/mspbots_forms_mcp/tools/forms.py`、`src/mspbots_forms_mcp/tools/_survey_walk.py`，
以及 `src/mspbots_forms_mcp/_json.py` 里的响应大小截断逻辑（本仓所有工具共用，不止 Form 工具）。

## PRD-21379 · 2026-10-24

**未发布** —— 以下事实锚定在工作分支 `dev01.mbagent/PRD-21379` @ `69ad26f`，尚未进入 `main`
或任何 `int` 分支（本仓截至目前没有 `int`/`INT` 分支 —— 只有 `main`、`fix/x-api-key-passthrough`
以及各单的 `dev01.mbagent/*` 分支）。合入 `main` 后请对照重新核实下列 `path:line`。

- `mspbots_forms_form_get`（`src/mspbots_forms_mcp/tools/forms.py:60-126`）新增可选参数
  `field_id`。给定时会强制发起内部 `include=definition` 请求（与调用方传入的 `include` 合并去重，
  `forms.py:94-96`），通过 `find_question_by_name`
  （`src/mspbots_forms_mcp/tools/_survey_walk.py:14-28`）定位 SurveyJS `name` 匹配的那个问题，
  并把该问题自己的字段展开到返回结果的顶层（不嵌套在 wrapper key 下 —— 原因见下一条）。不传
  `field_id` 时行为与本单之前完全一致，逐字节不变。
- **为什么要把问题字段展开到顶层而不是嵌套**：`dump_json_capped`（`src/mspbots_forms_mcp/_json.py:30-33`）
  只扫描**顶层** dict 的 key 来判断哪个是可截断的 `list`。如果 `choices` 数组被嵌套在深一层（比如
  包在一个 `"question"` wrapper key 下面），一个超大的 `choices` 列表就会对这个扫描不可见，整个响应
  会落进「太大、不是 list 形状」分支（`_json.py:54-61`）而被整体丢弃 —— 正好复现 PRD-21379 要修的
  那个 bug。以后任何工具如果要在这个截断上限下返回某一个嵌套 list 的完整内容，都要遵循同样的展平规则。
- `find_question_by_name` 的树遍历形状（`pages[*].elements[*]`，并递归进 `panel` 元素自己嵌套的
  `elements`）是标准的公开 SurveyJS JSON schema，选它是因为它是本仓最接近的既有先例（`forms.py`
  原有的 `include=["definition"]` 返回的就是同一种形状）。**这个形状尚未针对这么大的表单在真实后端
  上独立验证过** —— `forms.py` 模块头部原有的免责声明（第 1-12 行，本单之前就有，与本单无关）本来就
  标注整个 `definition` 形状是照着 PRD-15818 的 API 契约文档写的，只有 `include=["questions"]` 在
  一个小表单上做过一次真实验证（2026-08-07）。如果之后的真机验证（本单 AC5，手工用例，本沙箱未执行，
  见 `docs/tickets/PRD-21379.ac.json`）发现真实形状不同（比如没有 `pages` 包装的扁平 `elements`
  列表），只需要改 `_survey_walk.py` 一处 —— 它被特意单独拆出来就是为了应对这个风险。
- `dump_json_capped` 的截断逻辑（`_json.py:30-52`）本单未改动，也不是本单新写的 —— 它早就会挑
  体积最大的顶层 list 字段，二分查找出能塞进 `MAX_CHARS`（20,000 字符）预算的最大前缀，丢弃尾部的
  完整条目，并标记 `truncated`/`truncated_field`/`original_count`。本单新增的测试
  `tests/test_tools.py::test_form_get_field_id_truncates_oversized_choices_gracefully`
  是本仓第一条真正端到端跑通这条截断路径的测试。
