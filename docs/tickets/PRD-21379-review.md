# PRD-21379 · Code review

Status: frozen @ f116e2a

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

## Round 2 · 2026-10-29 · reviewed dev/PRD-21379 @ f116e2a (base main @ 35c6ccf)

Verdict: approved

### Context: why this is a new round, not a Round-1 fix-up

Round 1 approved `fbf001d` with 0 must-fix. The ticket was then bounced out-of-band (Tom Lan
manually created an `int` branch for this repo, merged the approved work in, and tested it
against live PROD data for the real form `f7528a78`; the fix returned 0 of 185 `client_org`
options). A dev-leg tick found no recognized resume path for that bounce shape and asked for a
formal design-leg rework via `5b`; the design leg produced `PRD-21379-r2.md` (implementation-error
triage, AC5 wording correction, new AC7/TC7 regression case); the dev leg then implemented the fix
and migrated the ticket's commits onto a fresh `dev/PRD-21379` cut from the current default branch
(`main@35c6ccf`, one commit ahead of round 1's `main@4066e70`), per the 2026-10-29 default-branch-only
MCP convention. There is therefore no "Fixes" list to verify against Round 1's findings (Round 1 had
none) — this round reviews the r2 rework on its own merits.

### Scope reviewed

Full branch diff `35c6ccf...f116e2a` touches the same files as Round 1 (`forms.py`,
`_survey_walk.py`, `tests/test_tools.py`, `docs/`) plus the new `docs/tickets/PRD-21379-r2.md`.
Round 1's original fix (the `field_id` filter itself, `find_question_by_name`) is unchanged code
on this branch and was already reviewed; this round's actual new content is the r2-specific commits
`2507a57..f116e2a`:

- `src/mspbots_forms_mcp/tools/_survey_walk.py` — new `normalize_choice_source()` function (AC7).
- `src/mspbots_forms_mcp/tools/forms.py:122-126` — one call site: `question = normalize_choice_source(question)` inserted before the existing `dump_json_capped` call.
- `tests/test_tools.py` — two new tests (`test_form_get_field_id_handles_choices_source_shape`, `test_form_get_field_id_choices_source_small_form_is_not_truncated`) plus the `_client_org_choices_source_definition` mock helper (TC7).
- `docs/tickets/PRD-21379-r2.md` (new), `PRD-21379.ac.json` (AC5 wording amended, AC7/TC7 added), `PRD-21379.md` (frozen, untouched by this round), `PRD-21379-review.md` (this file).
- `125952d` — removal of 8 non-English-only doc artifacts left by round 1 (`.zh.md` files, `docs/modules/`, `docs/tickets-index.*`), which `mcp-track.md` 2.4 disallows for this repo. Confirmed by listing `docs/tickets/` on this branch: only `PRD-21379.{md,ac.json}`, `PRD-21379-r2.md`, `PRD-21379-review.md` remain — no `.zh.md`, no `docs/modules/`, no `docs/tickets-index.md`.

No files outside this list were touched. Scope matches the r2 doc's own "What this rework changes" section (narrow: AC5 wording, AC7/TC7, the one normalization function and its call site).

### Verification performed

- Ran `uv run pytest -q` on the work branch HEAD (`f116e2a`, via `~/.local/bin/uv` — `uv` is not on `PATH` on this machine but is installed under `~/.local`): `27 passed, 1 failed`. The 1 failure is the same pre-existing `test_tools_list_snapshot` (`mspbots_forms_form_delete` description 521 > 500 chars) as Round 1, confirmed by matching assertion text and traceback line.
- Independently re-ran the same command on a separate, freshly-opened pristine worktree at `origin/main@35c6ccf` (detached, no work-branch commits): `20 passed, 1 failed`, same single failing test, same assertion. 0 regressions; the branch adds exactly 7 new passing tests (5 that didn't exist against the old base plus TC7's 2 new tests), matching the self-test's own baseline/final claim.
- Read the full r2 diff (`git diff f349c13..7f2f83e -- src/ tests/`) line by line. `normalize_choice_source()`: returns `question` unchanged if a top-level `choices` list is already present (round-1 shape, AC1/AC2/AC4 untouched) or if `choicesSource` is absent/not a dict/has no list `items`; otherwise promotes `choicesSource.items` to a top-level `choices` key, drops `choicesSource`, and carries `choicesSource.passAttributes` through as `choicesSourcePassAttributes` when present. This is a pure, side-effect-free transform (confirmed no module-level or mutable shared state, matching AC6/TC6's own assertion, which still passes with the new function present).
- Confirmed `_json.py`'s `dump_json_capped` (unchanged by this round, already read in full in Round 1) picks `max(list_keys, key=lambda k: len(_compact(data[k])))` — after normalization the dict carries both `choices` (large) and `choicesSourcePassAttributes` (a 2-3-element list of short attribute names). In every realistic shape the real options list is far larger than the attribute-name list, so `choices` is always the key selected for truncation; TC7's own two tests (185-item oversized case and 3-item untruncated case) exercise exactly this and both pass. See Findings for a theoretical edge case.
- Confirmed the TC7 mock (`_client_org_choices_source_definition`, options nested under `choicesSource.items[*].attrs`) matches the real shape Tom Lan's live test reported (`choicesSource.items[*].attrs`, 185 items, 37/185 missing `tenantId`) — not the flat top-level-`choices` shape Round 1's original mock used, which is exactly the gap this rework closes.
- Re-ran the Chinese-text scan (`grep -rnP '[\x{4e00}-\x{9fff}]' --exclude-dir=.git --exclude-dir=.venv --exclude=uv.lock .`) on the work branch: 2 hits, both confined to `docs/tickets/PRD-21379.md:31` and `PRD-21379-r2.md` (quoted rule names / the pipeline's own `wiki 未覆盖 X` template fragment) — matches the self-test's "Known gate miss" WARN exactly; none in `src/`, `tests/`, or `README.md`.
- Diffed `README.md`'s connector section (lines 7-77) against `~/.claude/skills/vendor-mcp-development/reference/readme-connector-section.md`: byte-for-byte identical (`diff` exit 0).
- Spot-checked `docs/tickets/PRD-21379.ac.json`: TC7's `result: pass` evidence string matches the actual test names and the two tests that exist in `tests/test_tools.py`; TC5 is `untested` with a reason (no live PROD/INT access from this sandbox) — not a silent gap, consistent with `REVIEW.md` section 3's WARN discipline.
- Confirmed via `git log --parents` that `dev/PRD-21379`'s r2 commits are a proper cherry-pick onto the new base: `a795b75` (the new branch's "product + tech design" commit) has parent `35c6ccf`, while the old `dev01.mbagent/PRD-21379` branch's equivalent commit (`2d5f312`, same message) has parent `4066e70` — different hashes, as expected for a real replay onto a new base, not an accidental branch alias.
- `git ls-remote --heads` confirms `dev/PRD-21379` and the old `dev01.mbagent/PRD-21379` both still exist on the remote; per the Handoff section and `mcp-track.md` 4.4 step 3, deleting the old branch is this leg's job after merge, not a review finding.

### Findings

1. [suggestion] `src/mspbots_forms_mcp/tools/_survey_walk.py` (`normalize_choice_source`) — the normalized dict carries both `choices` and, when present, `choicesSourcePassAttributes` as top-level list values. `dump_json_capped` truncates whichever top-level list key has the larger compacted length, so in a pathological case (very few `choices` entries with very long serialized content per entry vs. a `passAttributes` list that happens to compact larger — not reachable with today's 3-attribute lists, but not structurally prevented either) the function could truncate the wrong field. Not a must-fix: not reachable with current data (`passAttributes` is a short, fixed-size list of attribute names; `choices` is always the larger field in every case this ticket's data and tests cover), and AC7 only requires "gracefully truncated per AC2 if still oversized", which is satisfied either way (the response stays well-formed JSON under budget). Worth a one-line comment or an explicit exclusion if a future form ever pairs a tiny choice list with many `passAttributes` keys.

No must-fix findings. The r2 fix is narrowly scoped to exactly what `PRD-21379-r2.md`'s "What this rework changes" commits to; `dump_json_capped`'s truncation and the AC1/AC2/AC4/AC6 code paths are provably untouched (same behavior on the already-passing tests); the new regression test (TC7) is modeled on the real reported data shape, not a shape invented by this round; and the self-test's gate numbers, README diff, and Chinese-text scan all reproduced exactly as claimed.
