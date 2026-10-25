# Form tools (`mspbots_forms_form_*`)

Covers `src/mspbots_forms_mcp/tools/forms.py`, `src/mspbots_forms_mcp/tools/_survey_walk.py`,
and the response-size capping in `src/mspbots_forms_mcp/_json.py` that every tool in this
repo (not just Form tools) shares.

## PRD-21379 · 2026-10-24

**Unreleased** — these facts are anchored to work branch `dev01.mbagent/PRD-21379` @ `69ad26f`,
not yet on `main` or any `int` branch (this repo has no `int`/`INT` branch as of this writing —
only `main`, `fix/x-api-key-passthrough`, and per-ticket `dev01.mbagent/*` branches exist).
Re-verify these `path:line` references against `main` once this merges.

- `mspbots_forms_form_get` (`src/mspbots_forms_mcp/tools/forms.py:60-126`) gained an optional
  `field_id` parameter. When given, it forces an internal `include=definition` fetch (merged
  into any caller-supplied `include`, de-duplicated — `forms.py:94-96`), locates the one
  question whose SurveyJS `name` matches via `find_question_by_name`
  (`src/mspbots_forms_mcp/tools/_survey_walk.py:14-28`), and returns that question's own
  fields spread at the top level of the result (not nested under a wrapper key — see next
  bullet for why). Omitting `field_id` is byte-for-byte unchanged from before this ticket.
- **Why the question's fields are spread at the top level, not nested**: `dump_json_capped`
  (`src/mspbots_forms_mcp/_json.py:30-33`) only scans **top-level** dict keys for a `list`
  value when deciding what to truncate. If a question's `choices` array were nested one level
  deeper (e.g. under a `"question"` wrapper key), an oversized `choices` list would be
  invisible to that scan and the whole response would instead fall into the "too large,
  not list-shaped" branch (`_json.py:54-61`) and be discarded entirely — reproducing the
  exact bug PRD-21379 fixes. Any future tool that needs to return one question's (or any
  single nested list's) full contents under this cap must follow the same flattening rule.
- `find_question_by_name`'s tree-walk shape (`pages[*].elements[*]`, recursing into `panel`
  elements' own nested `elements`) is the standard public SurveyJS JSON schema, chosen
  because it is the closest existing precedent in this repo (`forms.py`'s pre-existing
  `include=["definition"]` returns the same shape). **It has not been independently verified
  against a real backend response for a form this large** — `forms.py`'s own module-level
  disclaimer (lines 1-12, pre-existing, unrelated to this ticket) already flags the entire
  `definition` shape as built from the PRD-15818 API contract doc, confirmed by live testing
  only for `include=["questions"]` on one small form (2026-08-07). If a live check (this
  ticket's AC5, manual, not run from this sandbox — see `docs/tickets/PRD-21379.ac.json`)
  later shows a different real shape (e.g. a flat `elements` list with no `pages` wrapper),
  only `_survey_walk.py` needs to change — it is intentionally isolated for exactly this risk.
- `dump_json_capped`'s truncation (`_json.py:30-52`) is unchanged by this ticket and was
  already exercised by this new code path, not newly written: it already picks the largest
  top-level list field and binary-searches the largest prefix that fits under `MAX_CHARS`
  (20,000 chars), dropping whole trailing items and flagging `truncated`/`truncated_field`/
  `original_count`. This ticket's test
  `tests/test_tools.py::test_form_get_field_id_truncates_oversized_choices_gracefully`
  is the first test in this repo to actually exercise that code path end-to-end.
