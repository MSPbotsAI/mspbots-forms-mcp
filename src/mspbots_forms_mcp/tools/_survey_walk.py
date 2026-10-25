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
