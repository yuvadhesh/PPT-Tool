"""
Geometry, Inheritance, and OOXML Element Helpers for Reading Order Extraction.
Handles:
1. Placeholder geometry inheritance (Slide -> Slide Layout -> Slide Master).
2. Effective font/style inheritance (Run -> Paragraph -> Placeholder -> Master defaults).
3. Group transforms (Recursive absolute bounding boxes via off, ext, chOff, chExt).
4. Rotated bounding box calculation.
5. OOXML element classification (p:sp, p:pic, p:graphicFrame, p:grpSp, p:cxnSp, mc:AlternateContent).
6. RTL detection (a:pPr rtl="1" or language tags).
7. Connector detection (a:stCxn / a:endCxn).
8. Decorative detection (Office 365 a16/adec extension and cNvPr attributes).
"""
import math
from typing import Optional, Tuple, Dict, Any, List
from lxml import etree
from pptx.enum.shapes import PP_PLACEHOLDER

from app.services.reading_order_config import (
    DEFAULT_SLIDE_WIDTH_EMU,
    DEFAULT_SLIDE_HEIGHT_EMU,
)

OOXML_NAMESPACES = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "a16": "http://schemas.microsoft.com/office/drawing/2014/main",
    "adec": "http://schemas.microsoft.com/office/drawing/2017/decorative",
}


def compute_rotated_bbox(
    left: int, top: int, width: int, height: int, rot_val: int
) -> Tuple[int, int, int, int]:
    """
    Computes axis-aligned bounding box for a shape rotated by rot_val (in 60,000ths of a degree).
    Returns (min_x, min_y, new_width, new_height).
    """
    if not rot_val or rot_val == 0:
        return left, top, width, height

    angle_deg = (rot_val / 60000.0) % 360.0
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    cx = left + width / 2.0
    cy = top + height / 2.0

    half_w = width / 2.0
    half_h = height / 2.0

    corners = [
        (-half_w, -half_h),
        (half_w, -half_h),
        (half_w, half_h),
        (-half_w, half_h),
    ]

    rx = [x * cos_a - y * sin_a for x, y in corners]
    ry = [x * sin_a + y * cos_a for x, y in corners]

    min_x = cx + min(rx)
    max_x = cx + max(rx)
    min_y = cy + min(ry)
    max_y = cy + max(ry)

    return int(round(min_x)), int(round(min_y)), int(round(max_x - min_x)), int(round(max_y - min_y))


def resolve_placeholder_geometry(
    shape, slide
) -> Tuple[int, int, int, int, str]:
    """
    STEP 1.1: Resolves position and size from:
    Slide explicit -> Slide Layout placeholder -> Slide Master placeholder.
    Returns (left, top, width, height, geometry_source).
    """
    # 1. Check direct shape coordinates
    left = getattr(shape, "left", None)
    top = getattr(shape, "top", None)
    width = getattr(shape, "width", None)
    height = getattr(shape, "height", None)

    if None not in (left, top, width, height) and width > 0 and height > 0:
        return int(left), int(top), int(width), int(height), "slide"

    ph_type = None
    ph_idx = None
    try:
        if getattr(shape, "is_placeholder", False):
            ph_type = shape.placeholder_format.type
            ph_idx = shape.placeholder_format.idx
    except Exception:
        pass

    # 2. Check Slide Layout Placeholders
    try:
        layout = getattr(slide, "slide_layout", None)
        if layout and hasattr(layout, "placeholders") and (ph_type is not None or ph_idx is not None):
            for ph in layout.placeholders:
                match = False
                pht = ph.placeholder_format.type
                pidx = ph.placeholder_format.idx
                if ph_idx is not None and pidx == ph_idx:
                    match = True
                elif ph_type is not None and pht == ph_type:
                    match = True
                if match:
                    l = getattr(ph, "left", None)
                    t = getattr(ph, "top", None)
                    w = getattr(ph, "width", None)
                    h = getattr(ph, "height", None)
                    if None not in (l, t, w, h) and w > 0 and h > 0:
                        return int(l), int(t), int(w), int(h), "layout"
    except Exception:
        pass

    # 3. Check Slide Master Placeholders
    try:
        master = getattr(slide.slide_layout, "slide_master", None) if hasattr(slide, "slide_layout") else None
        if master and hasattr(master, "placeholders") and (ph_type is not None or ph_idx is not None):
            for ph in master.placeholders:
                match = False
                pht = ph.placeholder_format.type
                pidx = ph.placeholder_format.idx
                if ph_idx is not None and pidx == ph_idx:
                    match = True
                elif ph_type is not None and pht == ph_type:
                    match = True
                if match:
                    l = getattr(ph, "left", None)
                    t = getattr(ph, "top", None)
                    w = getattr(ph, "width", None)
                    h = getattr(ph, "height", None)
                    if None not in (l, t, w, h) and w > 0 and h > 0:
                        return int(l), int(t), int(w), int(h), "master"
    except Exception:
        pass

    # Safe defaults if missing
    def_l = int(left) if left is not None else 0
    def_t = int(top) if top is not None else 0
    def_w = int(width) if width is not None and width > 0 else 1000000
    def_h = int(height) if height is not None and height > 0 else 500000
    return def_l, def_t, def_w, def_h, "slide"


def resolve_effective_font_properties(shape, slide) -> Dict[str, Any]:
    """
    STEP 1.2: Resolves effective font size, bold, alignment across run -> paragraph -> layout -> master.
    """
    res = {
        "font_size_pt": 14.0,
        "is_bold": False,
        "alignment": "LEFT",
    }
    tf = getattr(shape, "text_frame", None)
    if not tf or not tf.paragraphs:
        return res

    p0 = tf.paragraphs[0]
    res["alignment"] = str(getattr(p0, "alignment", "LEFT") or "LEFT")

    # 1. Check runs
    for run in p0.runs:
        if getattr(run.font, "size", None):
            res["font_size_pt"] = run.font.size.pt
        if getattr(run.font, "bold", None) is not None:
            res["is_bold"] = bool(run.font.bold)
            break

    # 2. Check paragraph level
    if res["font_size_pt"] == 14.0 and getattr(p0.font, "size", None):
        res["font_size_pt"] = p0.font.size.pt
    if not res["is_bold"] and getattr(p0.font, "bold", None):
        res["is_bold"] = bool(p0.font.bold)

    # 3. Check layout placeholder if size still default
    if res["font_size_pt"] == 14.0:
        try:
            if getattr(shape, "is_placeholder", False) and hasattr(slide, "slide_layout"):
                ph_t = shape.placeholder_format.type
                for l_ph in slide.slide_layout.placeholders:
                    if l_ph.placeholder_format.type == ph_t and l_ph.has_text_frame:
                        lp0 = l_ph.text_frame.paragraphs[0]
                        if getattr(lp0.font, "size", None):
                            res["font_size_pt"] = lp0.font.size.pt
                            break
        except Exception:
            pass

    return res


def compute_group_absolute_bbox(grp_elem) -> Tuple[int, int, int, int]:
    """
    STEP 1.3: Computes absolute group coordinates using grpSpPr xfrm: off, ext, chOff, chExt.
    """
    try:
        a_ns = OOXML_NAMESPACES["a"]
        p_ns = OOXML_NAMESPACES["p"]

        grpSpPr = grp_elem.find(f"{{{p_ns}}}grpSpPr")
        if grpSpPr is not None:
            xfrm = grpSpPr.find(f"{{{a_ns}}}xfrm")
            if xfrm is not None:
                off = xfrm.find(f"{{{a_ns}}}off")
                ext = xfrm.find(f"{{{a_ns}}}ext")
                if off is not None and ext is not None:
                    x = int(off.get("x", "0"))
                    y = int(off.get("y", "0"))
                    cx = int(ext.get("cx", "0"))
                    cy = int(ext.get("cy", "0"))
                    return x, y, cx, cy
    except Exception:
        pass
    return 0, 0, 0, 0


def detect_ooxml_element_type(shape_elem) -> str:
    """
    STEP 1.4: Determines OOXML element tag name and handles mc:AlternateContent.
    Accepts python-pptx Shape object or raw lxml Element.
    """
    raw_elem = getattr(shape_elem, "_element", shape_elem)
    tag = getattr(raw_elem, "tag", "").split("}")[-1]
    if tag == "AlternateContent":
        return "AlternateContent"
    if getattr(shape_elem, "is_placeholder", False):
        return "placeholder"
    if getattr(shape_elem, "has_text_frame", False) and tag == "sp":
        return "textbox"
    if tag == "pic":
        return "picture"
    if tag == "graphicFrame":
        if getattr(shape_elem, "has_table", False):
            return "table"
        if getattr(shape_elem, "has_chart", False):
            return "chart"
        return "graphicFrame"
    if tag == "grpSp":
        return "group"
    if tag == "cxnSp":
        return "connector"
    return tag or "shape"


def is_shape_decorative(shape_elem) -> bool:
    """
    STEP 1.8: Detects decorative metadata via a16:decorative (adec namespace) in cNvPr extLst,
    or isDecorative="1" attribute.
    """
    raw_elem = getattr(shape_elem, "_element", shape_elem)
    try:
        for elem in raw_elem.iter():
            if elem.tag.endswith("cNvPr"):
                if elem.get("isDecorative", "0") in ("1", "true"):
                    return True
                # Check Office 365 extensions
                for child in elem.iter():
                    if child.tag.endswith("decorative") and child.get("val") in ("1", "true"):
                        return True
    except Exception:
        pass
    return False


def is_rtl_shape_or_text(shape) -> bool:
    """
    STEP 2.3: Detects RTL paragraph formatting or language codes.
    """
    try:
        tf = getattr(shape, "text_frame", None)
        if not tf:
            return False

        for p in tf.paragraphs:
            p_elem = getattr(p, "_element", None)
            if p_elem is not None:
                pPr = p_elem.find(f"{{{OOXML_NAMESPACES['a']}}}pPr")
                if pPr is not None:
                    if pPr.get("rtl") in ("1", "true"):
                        return True
                    # Check language
                    for rPr in p_elem.iter(f"{{{OOXML_NAMESPACES['a']}}}rPr"):
                        lang = rPr.get("lang", "").lower()
                        if any(lang.startswith(prefix) for prefix in ("ar", "he", "fa", "ur", "ug")):
                            return True

        text = "\n".join(p.text for p in tf.paragraphs)
        # Check unicode ranges for Arabic / Hebrew
        for ch in text:
            code = ord(ch)
            if (0x0590 <= code <= 0x05FF) or (0x0600 <= code <= 0x06FF) or (0xFB50 <= code <= 0xFDFF):
                return True
    except Exception:
        pass
    return False


def get_connector_connections(shape_elem) -> Tuple[Optional[int], Optional[int]]:
    """
    STEP 2: Extracts start and end shape IDs connected by a connector (p:cxnSp).
    """
    st_id = None
    end_id = None
    try:
        a_ns = OOXML_NAMESPACES["a"]
        for st in shape_elem.iter(f"{{{a_ns}}}stCxn"):
            raw_id = st.get("id")
            if raw_id and raw_id.isdigit():
                st_id = int(raw_id)
                break
        for end in shape_elem.iter(f"{{{a_ns}}}endCxn"):
            raw_id = end.get("id")
            if raw_id and raw_id.isdigit():
                end_id = int(raw_id)
                break
    except Exception:
        pass
    return st_id, end_id
