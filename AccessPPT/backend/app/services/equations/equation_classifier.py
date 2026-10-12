"""
Equation classification: decides, per candidate, whether it can be converted
automatically, is already a MathType object, or must be reviewed manually.
"""
from __future__ import annotations

from collections import defaultdict

from app.services.equations.equation_detector import (
    CATEGORY_EQUATION_EDITOR_OLE,
    CATEGORY_IMAGE,
    CATEGORY_MATH_TEXT,
    CATEGORY_MATHTYPE_OLE,
    CATEGORY_OMML,
    CATEGORY_OTHER_EQUATION_OLE,
    PLACEMENT_INLINE,
    PLACEMENT_STANDALONE,
    PLACEMENT_TABLE,
    EquationCandidate,
)

ELIGIBLE = "eligible"
ALREADY_MATHTYPE = "already_mathtype"
NEEDS_REVIEW = "needs_review"

CATEGORY_LABELS = {
    CATEGORY_OMML: "Native Office Math (OMML)",
    CATEGORY_MATHTYPE_OLE: "Existing MathType object",
    CATEGORY_EQUATION_EDITOR_OLE: "Legacy Equation Editor 3.0 object",
    CATEGORY_OTHER_EQUATION_OLE: "Other embedded equation object",
    CATEGORY_MATH_TEXT: "Equation-like plain text",
    CATEGORY_IMAGE: "Possible equation image",
}


def classify(candidates: list[EquationCandidate], text_animated: dict[int, set[int]]) -> list[EquationCandidate]:
    """Set ``eligibility``, ``reason`` and ``unit_id`` on every candidate (in place)."""
    for c in candidates:
        c.eligibility, c.reason = _classify_one(c, text_animated.get(c.slide_number, set()))

    # A text box is replaced as a whole, so every equation in it must be eligible.
    units: dict[tuple[int, int], list[EquationCandidate]] = defaultdict(list)
    for c in candidates:
        if c.category == CATEGORY_OMML and c.placement == PLACEMENT_STANDALONE:
            units[(c.slide_number, c.shape_id)].append(c)
    for (slide_no, shape_id), group in units.items():
        if all(c.eligibility == ELIGIBLE for c in group):
            for c in group:
                c.unit_id = f"s{slide_no}-sp{shape_id}"
        else:
            for c in group:
                if c.eligibility == ELIGIBLE:
                    c.eligibility = NEEDS_REVIEW
                    c.reason = "Another equation in the same text box needs review, so the text box is left unchanged."
    return candidates


def _classify_one(c: EquationCandidate, animated_ids: set[int]) -> tuple[str, str]:
    if c.category == CATEGORY_MATHTYPE_OLE:
        return ALREADY_MATHTYPE, f"Already a MathType object ({c.prog_id}); left unchanged."
    if c.category == CATEGORY_EQUATION_EDITOR_OLE:
        return NEEDS_REVIEW, (
            "Legacy Equation Editor 3.0 object. Automatic conversion of this object type is not "
            "implemented; open it in PowerPoint with MathType installed to convert it."
        )
    if c.category == CATEGORY_OTHER_EQUATION_OLE:
        return NEEDS_REVIEW, f"Unrecognised equation object type ({c.prog_id}); manual review required."
    if c.category == CATEGORY_MATH_TEXT:
        return NEEDS_REVIEW, (
            f"Plain text that looks mathematical ({c.confidence} confidence). Its structure cannot be "
            "recovered reliably from text, so it is not converted automatically."
        )
    if c.category == CATEGORY_IMAGE:
        return NEEDS_REVIEW, (
            "Picture that may contain an equation. Image recognition is not verified, so the "
            "original image is kept; recreate it in MathType manually if needed."
        )
    # Native OMML
    if c.placement == PLACEMENT_INLINE:
        return NEEDS_REVIEW, (
            "Inline equation mixed with other text. MathType objects are separate shapes in PowerPoint, "
            "so replacing it would change the text layout. Move the equation to its own text box first."
        )
    if c.placement == PLACEMENT_TABLE:
        return NEEDS_REVIEW, "Equation inside a table cell; PowerPoint cannot place an OLE object inside a cell."
    if c.unsupported:
        return NEEDS_REVIEW, f"Contains OMML elements that are not handled yet: {', '.join(c.unsupported)}."
    if c.shape_id in animated_ids:
        return NEEDS_REVIEW, "The text box has paragraph-level animations that would not apply to a MathType object."
    if c.geometry.cx <= 0 or c.geometry.cy <= 0:
        return NEEDS_REVIEW, "The equation's text box has no resolvable position/size."
    return ELIGIBLE, "Standalone native equation; can be replaced by a MathType object at the same position."
