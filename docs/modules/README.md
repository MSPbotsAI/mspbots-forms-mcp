# Module docs index

Accumulated facts for `mspbots-forms-mcp`, keyed by tool group / code area. Read the
module doc(s) that match your ticket's `Code Project` and ticket text before designing
or implementing against this repo — see the pipeline's `references/docs-tree.md` for
how this index is used and kept in sync with the codebase.

| Code area / tool group | File | Covers |
|---|---|---|
| Form tools (`mspbots_forms_form_*`) | [forms-tools.md](forms-tools.md) | `src/mspbots_forms_mcp/tools/forms.py`, `src/mspbots_forms_mcp/tools/_survey_walk.py`, `src/mspbots_forms_mcp/_json.py` (response-size capping shared by every tool) |

Not yet covered (no module doc exists — write one only when a ticket's accumulated
fact would otherwise be lost or contradicted by a later one, not just to have one for
every file):

- Share tools (`mspbots_forms_share_*`, `src/mspbots_forms_mcp/tools/shares.py`)
- Response tools (`mspbots_forms_response_*`, `src/mspbots_forms_mcp/tools/responses.py`)
- Gateway credential middleware / tenant isolation (`src/mspbots_forms_mcp/server.py`, `src/mspbots_forms_mcp/api_client.py`)
