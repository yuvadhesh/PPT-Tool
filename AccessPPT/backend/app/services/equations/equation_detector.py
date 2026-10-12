"""
Equation detection: walks every slide (including groups, tables and
``mc:AlternateContent`` branches) and returns equation candidates with their
geometry, text and MathML. Classification into eligible / review buckets is done
by :mod:`equation_classifier`.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from lxml import etree
from pptx.shapes.shapetree import SlideShapeFactory

from app.services.equations.omml_processor import M_NS, convert_omath, find_top_level_equations

NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "m": M_NS,
}
OLE_URI = "http://schemas.openxmlformats.org/presentationml/2006/ole"

CATEGORY_OMML = "omml"
CATEGORY_MATHTYPE_OLE = "mathtype_ole"
CATEGORY_EQUATION_EDITOR_OLE = "equation_editor_ole"
CATEGORY_OTHER_EQUATION_OLE = "other_equation_ole"
CATEGORY_MATH_TEXT = "math_text"
CATEGORY_IMAGE = "image"

PLACEMENT_STANDALONE = "standalone_shape"
PLACEMENT_INLINE = "inline_text"
PLACEMENT_TABLE = "table_cell"

_STRONG_MATH_CHARS = set("√∛∫∬∮∑∏∞∂∇≤≥≠≈±∓×÷∈∉⊂⊆∪∩→⇒⇔")
_RELATION_RE = re.compile(r"[A-Za-z0-9)\]]\s*(=|<|>|≤|≥|≠|≈)\s*[-−A-Za-z0-9(√π]")
_SCRIPT_RE = re.compile(r"[A-Za-z0-9)]\s*[\^_]\s*[A-Za-z0-9({]")
_LONG_WORD_RE = re.compile(r"[A-Za-z]{4,}")
_IMAGE_HINT_RE = re.compile(r"\b(equation|formula|eqn|math)\b", re.IGNORECASE)


def _local(el) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _ns(el) -> str:
    return etree.QName(el).namespace if isinstance(el.tag, str) else ""


@dataclass
class Geometry:
    x: int = 0
    y: int = 0
    cx: int = 0
    cy: int = 0
    rot: int = 0
    flip_h: bool = False
    flip_v: bool = False


@dataclass
class EquationCandidate:
    id: str
    slide_number: int
    shape_id: int
    shape_name: str
    category: str
    placement: str
    geometry: Geometry
    group_path: list[str] = field(default_factory=list)
    text: str = ""
    mathml: Optional[str] = None
    constructs: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    prog_id: Optional[str] = None
    font_size_pt: Optional[float] = None
    confidence: str = "high"
    in_alternate_content: bool = False
    eligibility: str = "pending"
    reason: str = ""
    unit_id: Optional[str] = None
    shape_element: Any = field(default=None, repr=False, compare=False)
    replace_element: Any = field(default=None, repr=False, compare=False)
    equation_element: Any = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        for key in ("shape_element", "replace_element", "equation_element"):
            d.pop(key, None)
        return d


def _geometry(el, slide) -> Geometry:
    xfrm = el.find("p:spPr/a:xfrm", NS)
    if xfrm is None:
        xfrm = el.find("p:xfrm", NS)
    if xfrm is None:
        xfrm = el.find("p:grpSpPr/a:xfrm", NS)
    g = Geometry()
    if xfrm is not None:
        off, ext = xfrm.find("a:off", NS), xfrm.find("a:ext", NS)
        if off is not None:
            g.x, g.y = int(off.get("x", 0)), int(off.get("y", 0))
        if ext is not None:
            g.cx, g.cy = int(ext.get("cx", 0)), int(ext.get("cy", 0))
        g.rot = int(xfrm.get("rot", 0))
        g.flip_h = xfrm.get("flipH") in ("1", "true")
        g.flip_v = xfrm.get("flipV") in ("1", "true")
        return g
    # Placeholder without its own xfrm: inherit from layout via python-pptx.
    try:
        shape = SlideShapeFactory(el, slide.shapes)
        g.x, g.y = int(shape.left or 0), int(shape.top or 0)
        g.cx, g.cy = int(shape.width or 0), int(shape.height or 0)
    except Exception:
        pass
    return g


def _cnvpr(el):
    return el.find(".//p:cNvPr", NS)


def _non_math_text(txbody) -> str:
    parts = []
    for t in txbody.iter(f"{{{NS['a']}}}t"):
        if not any(_ns(anc) == M_NS for anc in t.iterancestors()):
            parts.append(t.text or "")
    return "".join(parts)


def _first_font_size(eq_el) -> Optional[float]:
    for rpr in eq_el.iter(f"{{{NS['a']}}}rPr"):
        sz = rpr.get("sz")
        if sz:
            return int(sz) / 100.0
    return None


def _uses_math_font(el) -> bool:
    for latin in el.iter(f"{{{NS['a']}}}latin"):
        if "math" in (latin.get("typeface") or "").lower():
            return True
    return False


def looks_like_math_text(text: str, math_font: bool = False) -> Optional[str]:
    """Return a confidence label if plain text looks like an equation, else None."""
    t = text.strip()
    if not t or len(t) > 120 or len(_LONG_WORD_RE.findall(t)) > 2:
        return None
    strong = math_font or any(c in _STRONG_MATH_CHARS for c in t) or any(0x1D400 <= ord(c) <= 0x1D7FF for c in t)
    structural = bool(_RELATION_RE.search(t) or _SCRIPT_RE.search(t))
    if strong and structural:
        return "medium"
    if strong or structural:
        return "low"
    return None


class EquationDetector:
    def detect(self, prs) -> list[EquationCandidate]:
        candidates: list[EquationCandidate] = []
        for idx, slide in enumerate(prs.slides, start=1):
            sp_tree = slide._element.find("p:cSld/p:spTree", NS)
            if sp_tree is not None:
                self._walk(sp_tree, slide, idx, [], None, candidates)
        return candidates

    def _walk(self, container, slide, slide_no, group_path, alt_content, out):
        for child in container:
            name = _local(child)
            if name == "AlternateContent" and _ns(child) == NS["mc"]:
                choice = child.find("mc:Choice", NS)
                if choice is not None:
                    self._walk(choice, slide, slide_no, group_path, child, out)
                continue
            if name == "grpSp":
                c = _cnvpr(child)
                self._walk(child, slide, slide_no, group_path + [c.get("name", "") if c is not None else ""], None, out)
            elif name == "sp":
                self._sp(child, slide, slide_no, group_path, alt_content, out)
            elif name == "graphicFrame":
                self._graphic_frame(child, slide, slide_no, group_path, alt_content, out)
            elif name == "pic":
                self._pic(child, slide, slide_no, group_path, alt_content, out)

    def _base(self, el, slide, slide_no, group_path, alt_content, category, placement, suffix):
        c = _cnvpr(el)
        shape_id = int(c.get("id", 0)) if c is not None else 0
        return EquationCandidate(
            id=f"s{slide_no}-sp{shape_id}-{suffix}",
            slide_number=slide_no,
            shape_id=shape_id,
            shape_name=c.get("name", "") if c is not None else "",
            category=category,
            placement=placement,
            geometry=_geometry(el, slide),
            group_path=list(group_path),
            in_alternate_content=alt_content is not None,
            shape_element=el,
            replace_element=alt_content if alt_content is not None else el,
        )

    def _omml_candidates(self, el, container, slide, slide_no, group_path, alt_content, placement, out):
        for n, eq in enumerate(find_top_level_equations(container)):
            conv = convert_omath(eq)
            cand = self._base(el, slide, slide_no, group_path, alt_content, CATEGORY_OMML, placement, f"e{n}")
            cand.text = conv.linear
            cand.mathml = conv.mathml
            cand.constructs = conv.constructs
            cand.unsupported = conv.unsupported
            cand.font_size_pt = _first_font_size(eq)
            cand.equation_element = eq
            out.append(cand)

    def _sp(self, el, slide, slide_no, group_path, alt_content, out):
        txbody = el.find("p:txBody", NS)
        if txbody is None:
            return
        if find_top_level_equations(txbody):
            placement = PLACEMENT_INLINE if _non_math_text(txbody).strip() else PLACEMENT_STANDALONE
            self._omml_candidates(el, txbody, slide, slide_no, group_path, alt_content, placement, out)
            return
        text = "\n".join(
            "".join(t.text or "" for t in p.iter(f"{{{NS['a']}}}t")) for p in txbody.findall("a:p", NS)
        ).strip()
        confidence = looks_like_math_text(text, _uses_math_font(txbody))
        if confidence:
            cand = self._base(el, slide, slide_no, group_path, alt_content, CATEGORY_MATH_TEXT, PLACEMENT_STANDALONE, "t0")
            cand.text = text
            cand.confidence = confidence
            out.append(cand)

    def _graphic_frame(self, el, slide, slide_no, group_path, alt_content, out):
        gdata = el.find("a:graphic/a:graphicData", NS)
        if gdata is None:
            return
        if gdata.get("uri") == OLE_URI:
            ole = gdata.find(".//p:oleObj", NS)
            prog_id = (ole.get("progId") or "") if ole is not None else ""
            if prog_id.startswith("Equation.DSMT"):
                category = CATEGORY_MATHTYPE_OLE
            elif prog_id == "Equation.3":
                category = CATEGORY_EQUATION_EDITOR_OLE
            elif prog_id.startswith("Equation."):
                category = CATEGORY_OTHER_EQUATION_OLE
            else:
                return
            cand = self._base(el, slide, slide_no, group_path, alt_content, category, PLACEMENT_STANDALONE, "ole")
            cand.prog_id = prog_id
            c = _cnvpr(el)
            cand.text = (c.get("descr") or "") if c is not None else ""
            out.append(cand)
            return
        tbl = gdata.find("a:tbl", NS)
        if tbl is not None and find_top_level_equations(tbl):
            self._omml_candidates(el, tbl, slide, slide_no, group_path, alt_content, PLACEMENT_TABLE, out)

    def _pic(self, el, slide, slide_no, group_path, alt_content, out):
        c = _cnvpr(el)
        if c is None:
            return
        hint = " ".join(filter(None, [c.get("descr"), c.get("title"), c.get("name")]))
        if _IMAGE_HINT_RE.search(hint):
            cand = self._base(el, slide, slide_no, group_path, alt_content, CATEGORY_IMAGE, PLACEMENT_STANDALONE, "img")
            cand.text = c.get("descr") or ""
            cand.confidence = "low"
            out.append(cand)


def text_animated_shape_ids(slide) -> set[int]:
    """Shape ids targeted by paragraph-level (text build) animations."""
    ids = set()
    for tgt in slide._element.iterfind(".//p:timing//p:spTgt", NS):
        if tgt.find("p:txEl", NS) is not None:
            try:
                ids.add(int(tgt.get("spid")))
            except (TypeError, ValueError):
                pass
    return ids


equation_detector = EquationDetector()
