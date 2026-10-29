"""Helpers for walking a SurveyJS form definition tree.

A SurveyJS definition nests questions under `pages[*].elements[*]`, and an
element of type "panel" nests its own "elements" list recursively (PRD-21379
tech design). This module isolates that walk so callers don't need to know
the tree shape, and so the shape assumption lives in exactly one place if a
live response later shows it differs (see forms.py module docstring).
"""

from typing import Any


def find_question_by_name(definition: dict[str, Any], name: str) -> dict[str, Any] | None:
    """Return the first question/element whose "name" equals `name`.

    Walks `definition["pages"][*]["elements"][*]`, recursing into any
    "panel"-type element's own nested "elements" list. Returns None if no
    page/element matches, or if `definition` isn't shaped as expected
    (missing or non-list "pages").
    """
    pages = definition.get("pages")
    if not isinstance(pages, list):
        return None
    for page in pages:
        if not isinstance(page, dict):
            continue
        found = _search_elements(page.get("elements"), name)
        if found is not None:
            return found
    return None


def _search_elements(elements: Any, name: str) -> dict[str, Any] | None:
    if not isinstance(elements, list):
        return None
    for element in elements:
        if not isinstance(element, dict):
            continue
        if element.get("name") == name:
            return element
        if element.get("type") == "panel":
            found = _search_elements(element.get("elements"), name)
            if found is not None:
                return found
    return None


def normalize_choice_source(question: dict[str, Any]) -> dict[str, Any]:
    """Promote a "choicesSource" static-choice-source dict's nested "items"
    list to a top-level "choices" key (PRD-21379 rework r2, AC7).

    A SurveyJS question carries its options one of two ways: a flat
    top-level "choices" list (what PRD-21379 round 1 assumed, and what the
    round-1 test mocks use), or a "choicesSource" reference --
    {"items": [...], "passAttributes": [...]} -- which is what the real
    client_org question on form f7528a78 actually uses. `_json.dump_json_capped`
    only scans a dict's own top-level keys for a list value to truncate
    (`_json.py:28-30`); a "choicesSource" dict is invisible to that scan, so
    without this normalization an oversized choicesSource-shaped question
    falls into the generic "not list-shaped" branch and the entire payload
    -- every option -- is discarded instead of gracefully truncated.

    Only one of the two shapes is expected on a given question. If a
    top-level "choices" list is already present, `question` is returned
    unchanged (round-1 behavior, AC1/AC2/AC4 untouched). If neither shape is
    present (e.g. a non-choice question type), `question` is also returned
    unchanged.
    """
    if isinstance(question.get("choices"), list):
        return question
    choices_source = question.get("choicesSource")
    if not isinstance(choices_source, dict):
        return question
    items = choices_source.get("items")
    if not isinstance(items, list):
        return question
    normalized = dict(question)
    del normalized["choicesSource"]
    normalized["choices"] = items
    pass_attributes = choices_source.get("passAttributes")
    if pass_attributes is not None:
        normalized["choicesSourcePassAttributes"] = pass_attributes
    return normalized
