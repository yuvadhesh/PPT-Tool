"""
Targeted OOXML edits that replace one equation shape with a MathType OLE object
while leaving every other element, relationship and the z-order untouched.
"""
from __future__ import annotations

import io
from copy import deepcopy

from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.shapes.graphfrm import CT_GraphicalObjectFrame
from pptx.parts.image import ImagePart

from app.services.equations.equation_detector import NS, EquationCandidate
from app.services.equations.mathtype_adapter import MathTypeObject

_R = NS["r"]
_METAFILE_EXT = {"image/x-emf": "emf", "image/x-wmf": "wmf"}


def _add_preview_image(slide_part, data: bytes, content_type: str) -> str:
    if content_type in _METAFILE_EXT:
        package = slide_part.package
        partname = package.next_image_partname(_METAFILE_EXT[content_type])
        part = ImagePart(partname, content_type, package, data)
        return slide_part.relate_to(part, RT.IMAGE)
    _, rid = slide_part.get_or_add_image_part(io.BytesIO(data))
    return rid


def _rel_ids(el) -> set[str]:
    ids = set()
    for node in el.iter():
        for attr in ("embed", "id", "link"):
            v = node.get(f"{{{_R}}}{attr}")
            if v:
                ids.add(v)
    return ids


def _fit(obj: MathTypeObject, cand: EquationCandidate) -> tuple[int, int]:
    w, h = obj.width_emu, obj.height_emu
    box_w, box_h = cand.geometry.cx, cand.geometry.cy
    scale = min(1.0, box_w / w if box_w else 1.0, box_h / h if box_h else 1.0)
    return max(1, int(w * scale)), max(1, int(h * scale))


def replace_with_mathtype_object(slide, cand: EquationCandidate, obj: MathTypeObject, alt_text: str) -> None:
    """Swap the candidate's shape (or its mc:AlternateContent wrapper) for an OLE frame."""
    slide_part = slide.part
    target = cand.replace_element
    parent = target.getparent()
    if parent is None:
        raise ValueError("Equation shape is no longer attached to the slide tree")

    ole_rid = slide_part.add_embedded_ole_object_part(obj.prog_id, io.BytesIO(obj.ole_object))
    img_rid = _add_preview_image(slide_part, obj.preview_image, obj.preview_content_type)
    cx, cy = _fit(obj, cand)
    frame = CT_GraphicalObjectFrame.new_ole_object_graphicFrame(
        cand.shape_id, "Equation", ole_rid, obj.prog_id, img_rid,
        cand.geometry.x, cand.geometry.y, cx, cy, obj.width_emu, obj.height_emu,
    )
    ole = frame.find(".//p:oleObj", NS)
    ole.attrib.pop("showAsIcon", None)
    ole.set("name", "Equation")

    # Keep the original identity so animations, links and reading order still resolve.
    new_cnvpr = frame.find("p:nvGraphicFramePr/p:cNvPr", NS)
    old_cnvpr = cand.shape_element.find(".//p:cNvPr", NS)
    new_cnvpr.set("name", cand.shape_name or "Equation")
    new_cnvpr.set("descr", alt_text)
    if old_cnvpr is not None:
        for child in old_cnvpr:
            new_cnvpr.append(deepcopy(child))
    locks = frame.find(".//a:graphicFrameLocks", NS)
    locks.attrib.pop("noGrp", None)
    locks.set("noChangeAspect", "1")
    xfrm = frame.find("p:xfrm", NS)
    g = cand.geometry
    if g.rot:
        xfrm.set("rot", str(g.rot))
    if g.flip_h:
        xfrm.set("flipH", "1")
    if g.flip_v:
        xfrm.set("flipV", "1")

    removed_rids = _rel_ids(target)
    parent.replace(target, frame)
    still_used = _rel_ids(slide._element)
    for rid in removed_rids - still_used:
        if rid in slide_part.rels:
            slide_part.rels.pop(rid)
