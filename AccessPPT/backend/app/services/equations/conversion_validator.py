"""
Validation of MathType objects returned by an adapter and of the final PPTX.
A conversion only counts as successful when the output contains a genuine
MathType OLE object (``Equation.DSMT*`` with an ``Equation Native`` stream).
"""
from __future__ import annotations

import hashlib
import io
from typing import Optional

import olefile
from pptx import Presentation

from app.services.equations.equation_detector import NS, OLE_URI
from app.services.equations.mathtype_adapter import MathTypeObject

ALLOWED_PREVIEW_TYPES = {"image/x-emf", "image/x-wmf", "image/png"}
MATHTYPE_STREAM = "Equation Native"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def inspect_ole(blob: bytes) -> Optional[str]:
    """Return None if ``blob`` is an OLE compound file holding MathType equation data."""
    if not blob or not olefile.isOleFile(io.BytesIO(blob)):
        return "Not an OLE compound file (images, SVG or text are not MathType objects)."
    with olefile.OleFileIO(io.BytesIO(blob)) as ole:
        if not ole.exists(MATHTYPE_STREAM):
            return f"OLE object has no '{MATHTYPE_STREAM}' stream."
    return None


def validate_mathtype_object(obj: MathTypeObject) -> Optional[str]:
    if not obj.prog_id.startswith("Equation.DSMT"):
        return f"Unexpected progId '{obj.prog_id}' (expected a MathType Equation.DSMT* object)."
    problem = inspect_ole(obj.ole_object)
    if problem:
        return problem
    if obj.preview_content_type not in ALLOWED_PREVIEW_TYPES or not obj.preview_image:
        return f"Missing or unsupported preview image ({obj.preview_content_type})."
    if obj.width_emu <= 0 or obj.height_emu <= 0:
        return "MathType object has no size."
    return None


def _shape_ids(slide) -> set[int]:
    return {int(c.get("id")) for c in slide._element.iterfind(".//p:cSld//p:cNvPr", NS) if c.get("id", "").isdigit()}


def _dangling_rels(slide) -> list[str]:
    missing = []
    for node in slide._element.iter():
        for attr in ("embed", "id", "link"):
            rid = node.get(f"{{{NS['r']}}}{attr}")
            if rid and rid not in slide.part.rels:
                missing.append(rid)
    return missing


def _mathtype_frame(slide, shape_id: int):
    for frame in slide._element.iterfind(".//p:graphicFrame", NS):
        c = frame.find("p:nvGraphicFramePr/p:cNvPr", NS)
        if c is None or c.get("id") != str(shape_id):
            continue
        gdata = frame.find("a:graphic/a:graphicData", NS)
        ole = gdata.find(".//p:oleObj", NS) if gdata is not None and gdata.get("uri") == OLE_URI else None
        if ole is not None and (ole.get("progId") or "").startswith("Equation.DSMT"):
            return ole
    return None


def validate_output(
    original_path: str,
    original_sha256: str,
    output_path: str,
    converted: list[tuple[int, int]],
) -> list[dict]:
    """Return a list of named checks; ``converted`` holds (slide_number, shape_id) pairs."""
    checks: list[dict] = []

    def check(name: str, passed: bool, detail: str = ""):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    check("original_unchanged", sha256_file(original_path) == original_sha256, "SHA-256 of the uploaded file")
    try:
        before, after = Presentation(original_path), Presentation(output_path)
    except Exception as e:
        check("output_opens", False, str(e))
        return checks
    check("output_opens", True)
    check("slide_count", len(before.slides) == len(after.slides), f"{len(before.slides)} -> {len(after.slides)}")
    check(
        "slide_size",
        (before.slide_width, before.slide_height) == (after.slide_width, after.slide_height),
    )
    notes_b = sum(1 for s in before.slides if s.has_notes_slide)
    notes_a = sum(1 for s in after.slides if s.has_notes_slide)
    check("notes_preserved", notes_b == notes_a, f"{notes_b} -> {notes_a}")

    lost, dangling, missing_ole = [], [], []
    for idx, (sb, sa) in enumerate(zip(before.slides, after.slides), start=1):
        gone = _shape_ids(sb) - _shape_ids(sa)
        if gone:
            lost.append(f"slide {idx}: {sorted(gone)}")
        d = _dangling_rels(sa)
        if d:
            dangling.append(f"slide {idx}: {d}")
    for slide_no, shape_id in converted:
        ole = _mathtype_frame(after.slides[slide_no - 1], shape_id)
        if ole is None:
            missing_ole.append(f"slide {slide_no} shape {shape_id}: no MathType OLE frame")
            continue
        part = after.slides[slide_no - 1].part.related_part(ole.get(f"{{{NS['r']}}}id"))
        problem = inspect_ole(part.blob)
        if problem:
            missing_ole.append(f"slide {slide_no} shape {shape_id}: {problem}")
    check("no_shapes_lost", not lost, "; ".join(lost))
    check("relationships_resolve", not dangling, "; ".join(dangling))
    check("mathtype_objects_valid", not missing_ole, "; ".join(missing_ole) or f"{len(converted)} object(s) verified")
    return checks
