# PRD-21379 · Code review

Status: frozen @ fbf001d

## Round 1 · 2026-10-24 · reviewed dev01.mbagent/PRD-21379 @ fbf001d (base main @ 4066e70)

Verdict: approved

### Scope reviewed

Diff `4066e70...fbf001d`: `src/mspbots_forms_mcp/tools/forms.py`, `src/mspbots_forms_mcp/tools/_survey_walk.py` (new), `tests/test_tools.py`, plus `docs/` (tickets doc, ac.json, module doc, index). No files outside the tech design's Change list were touched.

### Verification performed

- Ran `uv run pytest -q` on the work branch HEAD (`fbf001d`): `25 passed, 1 failed` — matches the self-test's claimed numbers exactly. The 1 failure is `tests/test_tools.py::test_tools_list_snapshot` (`mspbots_forms_form_delete` description too long), unrelated to this ticket's `form_get`/`_survey_walk` changes.
- Independently re-ran the same command on a separate pristine worktree at base `main@4066e70`: `20 passed, 1 failed`, same failing test, same assertion. Confirms the failure is pre-existing baseline-red, not a regression introduced by this diff — 0 regressions, matching the doc's own baseline/final diff claim.
- Read `src/mspbots_forms_mcp/_json.py`'s `dump_json_capped` in full and confirmed its top-level-list truncation mechanism (largest list-valued key, binary-search prefix, `truncated`/`truncated_field`/`original_count` keys) matches exactly what AC2's test and the tech design's "spread at top level" rationale depend on.
- Confirmed via `git ls-remote --heads` that this repo has no `int`/`INT` branch (only `main`, `fix/x-api-key-passthrough`, and per-ticket `dev01.mbagent/*` branches) — matches the Handoff section's note.
- Spot-checked `docs/modules/forms-tools.md`'s `path:line` citations against the actual file (`forms.py:61` for the function def vs. the doc's `forms.py:60-126`, `_survey_walk.py:13` vs. the doc's `:14-28`) — off by one line in both cases (likely counted from a decorator/docstring line), immaterial to the claims made.
- Confirmed EN/ZH docs (`PRD-21379.md`/`.zh.md`, `forms-tools.md`/`.zh.md`) have matching section structure 1:1.
- Confirmed all 4 work-branch commits (`2d5f312`, `14db748`, `69ad26f`, `fbf001d`) are authored and committed as `Dev01.MBAgent <dev01.mbagent@mspbots.ai>`.

### Findings

1. [suggestion] `src/mspbots_forms_mcp/tools/forms.py:126` — the response is built as `{"form_id": form_id, "field_id": field_id, **question}`. If a SurveyJS element ever carried a literal `"form_id"` or `"field_id"` key (not part of the standard schema today, so no known live trigger), the spread would silently override the intended identifiers with the question's own values. Flipping the order to `{**question, "form_id": form_id, "field_id": field_id}` would make the identifiers always win, at no cost. Not a must-fix: implemented exactly per the tech design's specified shape, and no real-world element is known to define those keys.

No must-fix findings. Scope, correctness, security/multi-tenancy (AC6), and test evidence all check out against the tech design and `REVIEW.md`.
