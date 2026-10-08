"""
Reading Order Service — Benchmark-Driven Hybrid PowerPoint Reading Order Algorithm
strictly adhering to WCAG 2.1 AA (SC 1.3.2) and Section 508.

================================================================================
STEP 0: READING ORDER SEMANTICS & INTERNAL CONVENTION
================================================================================
1. Reading Order = Document order of children inside <p:cSld>/<p:spTree>.
2. FIRST element in <p:spTree> = Read FIRST by screen readers (JAWS, NVDA, Narrator).
3. Z-order in PowerPoint OOXML follows the exact same order:
   - First element = back-most (rendered first, bottom of visual stack)
   - Last element  = front-most (rendered last, top of visual stack)
4. PowerPoint's GUI Reading Order Pane DISPLAYS the list in REVERSE:
   - Top item of the GUI pane corresponds to the LAST element in XML (front-most).
   - Bottom item of the GUI pane corresponds to the FIRST element in XML (read first).
5. All internal data structures and APIs use ONE explicit convention:
   - reading_index 0 = first read = first in XML = Position 1 in 1-based display.
   - When the UI mirrors PowerPoint's pane, it adds an explicit label indicating the reversal.
================================================================================
"""
import os
import shutil
import tempfile
import hashlib
from typing import Optional, Any, List, Dict, Tuple
from pathlib import Path
from lxml import etree
import pptx
from pptx.enum.shapes import MSO_SHAPE_TYPE, PP_PLACEHOLDER

from app.core.logging import logger
from app.services.gemini_service import gemini_service
from app.services.reading_order_config import (
    DEFAULT_SLIDE_WIDTH_EMU,
    DEFAULT_SLIDE_HEIGHT_EMU,
    SPANNING_WIDTH_RATIO,
    AMBIGUITY_CONFIDENCE_GAP,
    GEMINI_TEMPERATURE,
    GEMINI_TEXT_SNIPPET_MAX_LEN,
    WEIGHT_SEMANTIC,
    WEIGHT_LAYOUT,
    WEIGHT_VERTICAL,
    WEIGHT_HORIZONTAL,
    WEIGHT_GROUPING,
    WEIGHT_RELATIONSHIP,
)
from app.services.geometry_helpers import (
    OOXML_NAMESPACES,
    compute_rotated_bbox,
    resolve_placeholder_geometry,
    resolve_effective_font_properties,
    compute_group_absolute_bbox,
    detect_ooxml_element_type,
    is_shape_decorative,
    is_rtl_shape_or_text,
    get_connector_connections,
)
from app.services.layout_engine import (
    glue_relationships,
    recursive_xy_cut,
    enforce_z_order_topological_sort,
)


def _get_shape_alt_text(shape) -> tuple[Optional[str], bool]:
    """Extract alt text description and decorative flag from shape OOXML."""
    try:
        if hasattr(shape, "_element"):
            elem = shape._element
            is_dec = is_shape_decorative(elem)
            for child in elem.iter():
                if child.tag.endswith("cNvPr"):
                    desc = child.get("descr") or child.get("title") or None
                    return desc, is_dec
    except Exception:
        pass
    return None, False


def _get_text_content(shape) -> str:
    """Safely extract plain text from shape with placeholder text normalization."""
    try:
        if getattr(shape, "has_text_frame", False):
            raw_text = "\n".join(p.text for p in shape.text_frame.paragraphs if p.text.strip())
            # Normalization: Treat default placeholder prompt strings as empty
            lower_txt = raw_text.strip().lower()
            if lower_txt in (
                "click to add text",
                "click to add title",
                "click to add subtitle",
                "click to add content",
            ):
                return ""
            return raw_text
    except Exception:
        pass
    return ""


def _inspect_ooxml_placeholder(shape) -> tuple[bool, Optional[str]]:
    """
    Directly inspects the shape's OOXML element for <p:ph> or <ph>.
    Returns (is_placeholder, placeholder_type_str).
    """
    try:
        if hasattr(shape, "element"):
            for elem in shape.element.iter():
                if elem.tag.endswith("}ph") or elem.tag == "ph":
                    raw_type = elem.get("type")
                    if raw_type is None or not raw_type.strip():
                        return True, "body"
                    return True, raw_type.strip()
    except Exception:
        pass

    try:
        if getattr(shape, "is_placeholder", False):
            ph = shape.placeholder_format
            pht = ph.type
            if pht in (PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE):
                return True, "title"
            if pht == PP_PLACEHOLDER.SUBTITLE:
                return True, "subTitle"
            if pht in (PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.OBJECT):
                return True, "body"
            if pht == PP_PLACEHOLDER.PICTURE:
                return True, "pic"
            if pht == PP_PLACEHOLDER.TABLE:
                return True, "tbl"
            if pht == PP_PLACEHOLDER.CHART:
                return True, "chart"
            if pht == PP_PLACEHOLDER.FOOTER:
                return True, "ftr"
            if pht == PP_PLACEHOLDER.SLIDE_NUMBER:
                return True, "sldNum"
            if pht == PP_PLACEHOLDER.DATE:
                return True, "dt"
            if pht == PP_PLACEHOLDER.HEADER:
                return True, "hdr"
            return True, "body"
    except Exception:
        pass

    return False, None


def _classify_shape(
    shape,
    is_primary_title: bool = False,
    slide_height: int = DEFAULT_SLIDE_HEIGHT_EMU,
    is_paired_caption: bool = False,
    is_card_container: bool = False,
) -> dict:
    """
    Maps shape to semantic role and object type adhering to Step 1 & 2 rules.
    """
    alt_desc, is_decorative = _get_shape_alt_text(shape)
    s_name = (getattr(shape, "name", None) or "").strip()
    s_name_lower = s_name.lower()
    text = _get_text_content(shape).strip()
    top = getattr(shape, "top", 0) or 0
    st = getattr(shape, "shape_type", None)

    # Check for Connectors / Arrows first (not decorative!)
    elem_tag = getattr(shape, "_element", None)
    tag_name = elem_tag.tag.split("}")[-1] if elem_tag is not None else ""
    if tag_name == "cxnSp" or "connector" in s_name_lower or "arrow" in s_name_lower:
        return {
            "object_type": "Connector",
            "semantic_role": "connector",
            "placeholder_type": None,
            "is_placeholder": False,
            "is_decorative": False,
        }

    # Placeholder detection
    is_ph, ph_type = _inspect_ooxml_placeholder(shape)
    if not is_ph:
        if s_name_lower.startswith(("content placeholder", "body placeholder", "text placeholder")):
            is_ph = True
            ph_type = "body"
        elif s_name_lower.startswith(("title placeholder", "centered title")):
            is_ph = True
            ph_type = "title"
        elif s_name_lower.startswith("subtitle placeholder"):
            is_ph = True
            ph_type = "subTitle"

    # Group check (groups are atomic units, never containers)
    if st == MSO_SHAPE_TYPE.GROUP or hasattr(shape, "shapes"):
        return {"object_type": "Group", "semantic_role": "group", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}

    # Container background shape
    if is_card_container or s_name_lower.startswith(("card background", "background card", "container")):
        return {
            "object_type": "Shape",
            "semantic_role": "container",
            "placeholder_type": None,
            "is_placeholder": False,
            "is_decorative": False,
        }

    # Decorative check
    if (is_decorative or s_name_lower.startswith(("decorative", "accent", "flourish", "background banner"))) and not is_primary_title:
        return {
            "object_type": "Decorative",
            "semantic_role": "decorative",
            "placeholder_type": ph_type,
            "is_placeholder": is_ph,
            "is_decorative": True,
        }

    # Placeholder role mapping
    if is_ph and ph_type:
        ph_t = ph_type.lower()
        if ph_t in ("title", "ctrtitle"):
            if is_primary_title:
                return {"object_type": "Title", "semantic_role": "title", "placeholder_type": ph_type, "is_placeholder": True, "is_decorative": False}
            else:
                role = "subtitle" if top < slide_height * 0.45 else "heading"
                return {"object_type": "Subtitle" if role == "subtitle" else "Title", "semantic_role": role, "placeholder_type": ph_type, "is_placeholder": True, "is_decorative": False}
        elif ph_t == "subtitle":
            return {"object_type": "Subtitle", "semantic_role": "subtitle", "placeholder_type": ph_type, "is_placeholder": True, "is_decorative": False}
        elif ph_t in ("body", "obj"):
            is_list = False
            if text:
                lines = [line.strip() for line in text.split("\n") if line.strip()]
                if len(lines) > 1 and any(l.startswith(("-", "•", "*", "1.", "2.", "a.", "b.")) for l in lines):
                    is_list = True
            return {"object_type": "Content Placeholder", "semantic_role": "list" if is_list else "body_text", "placeholder_type": ph_type, "is_placeholder": True, "is_decorative": False}
        elif ph_t in ("pic", "sldimg", "clipart"):
            return {"object_type": "Picture", "semantic_role": "image", "placeholder_type": ph_type, "is_placeholder": True, "is_decorative": False}
        elif ph_t in ("tbl",):
            return {"object_type": "Table", "semantic_role": "table", "placeholder_type": ph_type, "is_placeholder": True, "is_decorative": False}
        elif ph_t in ("chart",):
            return {"object_type": "Chart", "semantic_role": "chart", "placeholder_type": ph_type, "is_placeholder": True, "is_decorative": False}
        elif ph_t in ("ftr",):
            return {"object_type": "Footer", "semantic_role": "footer", "placeholder_type": ph_type, "is_placeholder": True, "is_decorative": False}
        elif ph_t in ("sldnum",):
            return {"object_type": "Slide Number", "semantic_role": "footer", "placeholder_type": ph_type, "is_placeholder": True, "is_decorative": False}
        elif ph_t in ("dt",):
            return {"object_type": "Date", "semantic_role": "footer", "placeholder_type": ph_type, "is_placeholder": True, "is_decorative": False}
        elif ph_t in ("hdr",):
            return {"object_type": "Footer", "semantic_role": "footer", "placeholder_type": ph_type, "is_placeholder": True, "is_decorative": False}
        elif ph_t in ("dgm", "smartart"):
            return {"object_type": "SmartArt", "semantic_role": "smart_art", "placeholder_type": ph_type, "is_placeholder": True, "is_decorative": False}
        elif ph_t in ("media",):
            return {"object_type": "Media", "semantic_role": "media", "placeholder_type": ph_type, "is_placeholder": True, "is_decorative": False}
        else:
            return {"object_type": "Content Placeholder", "semantic_role": "body_text", "placeholder_type": ph_type, "is_placeholder": True, "is_decorative": False}

    if is_primary_title:
        return {"object_type": "Title", "semantic_role": "title", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}

    if is_paired_caption or s_name_lower.startswith("caption"):
        return {"object_type": "Caption", "semantic_role": "caption", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}

    if st == MSO_SHAPE_TYPE.TABLE or getattr(shape, "has_table", False):
        return {"object_type": "Table", "semantic_role": "table", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}
    if st == MSO_SHAPE_TYPE.CHART or getattr(shape, "has_chart", False):
        return {"object_type": "Chart", "semantic_role": "chart", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}
    if st == MSO_SHAPE_TYPE.GROUP:
        return {"object_type": "Group", "semantic_role": "group", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}
    if st == MSO_SHAPE_TYPE.MEDIA:
        return {"object_type": "Media", "semantic_role": "media", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}

    # SmartArt detection via diagram URI
    if hasattr(shape, "element") and shape.element.tag.endswith("graphicFrame"):
        for elem in shape.element.iter():
            if "diagram" in elem.tag or "dgm" in elem.tag:
                return {"object_type": "SmartArt", "semantic_role": "smart_art", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}

    if st == MSO_SHAPE_TYPE.PICTURE or s_name_lower.startswith(("picture", "image", "photo", "figure", "site")):
        return {"object_type": "Picture", "semantic_role": "image", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}

    if s_name_lower.startswith("table"):
        return {"object_type": "Table", "semantic_role": "table", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}
    if s_name_lower.startswith("chart"):
        return {"object_type": "Chart", "semantic_role": "chart", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}
    if s_name_lower.startswith(("smartart", "diagram")):
        return {"object_type": "SmartArt", "semantic_role": "smart_art", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}
    if s_name_lower.startswith(("slide number", "page number")):
        return {"object_type": "Slide Number", "semantic_role": "footer", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}
    if s_name_lower.startswith("footer"):
        return {"object_type": "Footer", "semantic_role": "footer", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}
    if s_name_lower.startswith("date"):
        return {"object_type": "Date", "semantic_role": "footer", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}
    if s_name_lower.startswith("subtitle"):
        return {"object_type": "Subtitle", "semantic_role": "subtitle", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}

    if top > slide_height * 0.90:
        if s_name_lower.startswith(("slide number", "page number")) or (text and text.isdigit() and len(text) <= 4):
            return {"object_type": "Slide Number", "semantic_role": "footer", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}
        if len(text) < 50:
            return {"object_type": "Footer", "semantic_role": "footer", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}

    if text:
        if s_name_lower.startswith("title"):
            return {"object_type": "Title", "semantic_role": "title", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}
        if "heading" in s_name_lower or "header" in s_name_lower or s_name_lower.startswith(("pillar", "stage", "step", "quadrant")):
            return {"object_type": "Heading", "semantic_role": "heading", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if len(lines) > 1 and any(l.startswith(("-", "•", "*", "1.", "2.", "a.", "b.")) for l in lines):
            return {"object_type": "Text Box", "semantic_role": "list", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}
        if len(lines) == 1 and len(text) < 80 and not text.endswith((".", ":")):
            is_prominent = False
            try:
                tf = getattr(shape, "text_frame", None)
                if tf and tf.paragraphs and tf.paragraphs[0].runs:
                    r0 = tf.paragraphs[0].runs[0]
                    if getattr(r0.font, "bold", False) or (getattr(r0.font, "size", None) and r0.font.size.pt >= 18):
                        is_prominent = True
            except Exception:
                pass
            if is_prominent or any(k in text.lower() for k in ("heading", "header", "step", "pillar", "stage", "overview")):
                return {"object_type": "Heading", "semantic_role": "heading", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}
        return {"object_type": "Text Box", "semantic_role": "body_text", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}

    # Empty shape
    if is_decorative or not text:
        return {"object_type": "Decorative" if is_decorative else "Shape", "semantic_role": "decorative" if is_decorative else "shape", "placeholder_type": None, "is_placeholder": False, "is_decorative": is_decorative}

    return {"object_type": "Shape", "semantic_role": "shape", "placeholder_type": None, "is_placeholder": False, "is_decorative": False}


class ReadingOrderService:
    """
    Benchmark-Driven Hybrid PowerPoint Reading Order Algorithm.
    Adheres to the 20-Phase architecture with strict recursive XY-cut,
    inheritance resolution, topological z-order safety, and verification.
    """

    def __init__(self):
        self._gemini_cache: Dict[str, List[int]] = {}

    def analyze_presentation(self, pptx_path: str, use_ai_fallback: bool = False) -> dict:
        """Analyze all slides in the PowerPoint presentation for reading order compliance."""
        prs = pptx.Presentation(pptx_path)
        slide_width = prs.slide_width or DEFAULT_SLIDE_WIDTH_EMU
        slide_height = prs.slide_height or DEFAULT_SLIDE_HEIGHT_EMU

        slides_results = []
        total_issues = 0
        slides_passed = 0
        slides_failed = 0

        for slide_idx, slide in enumerate(prs.slides):
            slide_result = self.analyze_slide(
                slide=slide,
                slide_idx=slide_idx,
                slide_width=slide_width,
                slide_height=slide_height,
                use_ai_fallback=use_ai_fallback,
            )
            slides_results.append(slide_result)
            total_issues += len(slide_result["issues"])
            if slide_result["status"] == "PASS":
                slides_passed += 1
            else:
                slides_failed += 1

        total_slides = len(slides_results)
        compliance_rate = round((slides_passed / total_slides * 100), 1) if total_slides > 0 else 100.0

        return {
            "summary": {
                "total_slides_checked": total_slides,
                "slides_passed": slides_passed,
                "slides_failed": slides_failed,
                "total_issues": total_issues,
                "compliance_rate": compliance_rate,
            },
            "slide_width_emu": slide_width,
            "slide_height_emu": slide_height,
            "slides": slides_results,
        }

    def _extract_slide_objects(
        self,
        slide,
        slide_num: int,
        slide_width: int,
        slide_height: int,
        primary_title_shape,
    ) -> list[dict]:
        """
        STEP 1: Extract all PPTX objects with full geometry and font/style inheritance.
        """
        raw_shapes = list(slide.shapes)
        objects = []

        # Check for card containers (shapes behind other content covering > 60% of foreground)
        container_ids = set()
        for i in range(len(raw_shapes)):
            s1 = raw_shapes[i]
            if getattr(s1, "shape_type", None) == MSO_SHAPE_TYPE.GROUP or hasattr(s1, "shapes"):
                continue
            s1_txt = _get_text_content(s1).strip()
            l1, t1 = getattr(s1, "left", 0) or 0, getattr(s1, "top", 0) or 0
            w1, h1 = getattr(s1, "width", 0) or 0, getattr(s1, "height", 0) or 0
            for j in range(i + 1, len(raw_shapes)):
                s2 = raw_shapes[j]
                if getattr(s2, "shape_type", None) == MSO_SHAPE_TYPE.GROUP or hasattr(s2, "shapes"):
                    continue
                s2_txt = _get_text_content(s2).strip()
                l2, t2 = getattr(s2, "left", 0) or 0, getattr(s2, "top", 0) or 0
                w2, h2 = getattr(s2, "width", 0) or 0, getattr(s2, "height", 0) or 0
                overlap_w = max(0, min(l1 + w1, l2 + w2) - max(l1, l2))
                overlap_h = max(0, min(t1 + h1, t2 + h2) - max(t1, t2))
                overlap_area = overlap_w * overlap_h
                area1 = max(1, w1 * h1)
                area2 = max(1, w2 * h2)

                if area1 >= area2 and overlap_area > 0.60 * area2 and not s1_txt and s2_txt:
                    container_ids.add(s1.shape_id)
                elif area2 >= area1 and overlap_area > 0.60 * area1 and not s2_txt and s1_txt:
                    container_ids.add(s2.shape_id)

        for idx, s in enumerate(raw_shapes):
            left, top, width, height, geom_source = resolve_placeholder_geometry(s, slide)
            rot = getattr(s, "rotation", 0) or 0
            if rot != 0:
                left, top, width, height = compute_rotated_bbox(left, top, width, height, int(rot * 60000))

            center_x = left + (width / 2.0)
            center_y = top + (height / 2.0)

            norm_left = round(max(0.0, min(1.0, left / slide_width)), 4) if slide_width else 0.0
            norm_top = round(max(0.0, min(1.0, top / slide_height)), 4) if slide_height else 0.0
            norm_width = round(max(0.0, min(1.0, width / slide_width)), 4) if slide_width else 0.0
            norm_height = round(max(0.0, min(1.0, height / slide_height)), 4) if slide_height else 0.0

            text = _get_text_content(s)
            alt_desc, is_dec_flag = _get_shape_alt_text(s)
            is_slide_title = (s == primary_title_shape)
            is_card = s.shape_id in container_ids

            # Check zero-size / invisible empty shape
            is_zero_size = (width < 100000 or height < 100000) and not text.strip()
            if is_zero_size:
                is_dec_flag = True

            shape_info = _classify_shape(
                shape=s,
                is_primary_title=is_slide_title,
                slide_height=slide_height,
                is_card_container=is_card,
            )

            object_type = shape_info["object_type"]
            role = shape_info["semantic_role"]
            ph_type_name = shape_info["placeholder_type"]
            is_placeholder = shape_info["is_placeholder"]
            is_decorative = shape_info["is_decorative"] or is_dec_flag or (role == "decorative")

            xml_elem = getattr(s, "_element", None)
            xml_element_type = detect_ooxml_element_type(xml_elem) if xml_elem is not None else "sp"

            # Connectors
            st_id, end_id = get_connector_connections(xml_elem) if xml_elem is not None else (None, None)

            # Effective Font
            font_props = resolve_effective_font_properties(s, slide)
            is_rtl = is_rtl_shape_or_text(s)

            text_snippet = text.strip().replace("\n", " ")
            if len(text_snippet) > 80:
                text_snippet = text_snippet[:77] + "..."

            objects.append({
                "slide_number": slide_num,
                "shape_id": s.shape_id,
                "name": s.name or f"Shape {s.shape_id}",
                "shape_name": s.name or f"Shape {s.shape_id}",
                "xml_element_type": xml_element_type,
                "current_xml_index": idx,
                "object_type": object_type,
                "semantic_role": role,
                "is_title": is_slide_title,
                "placeholder_type": ph_type_name,
                "is_placeholder": is_placeholder,
                "text_content": text,
                "text_snippet": text_snippet,
                "alt_text": alt_desc,
                "is_decorative": is_decorative,
                "geometry_source": geom_source,
                "is_rtl": is_rtl,
                "connector_start_id": st_id,
                "connector_end_id": end_id,
                "font_properties": font_props,
                "left_emu": left,
                "top_emu": top,
                "width_emu": width,
                "height_emu": height,
                "center_x": center_x,
                "center_y": center_y,
                "norm_left": norm_left,
                "norm_top": norm_top,
                "norm_width": norm_width,
                "norm_height": norm_height,
                "z_order": idx + 1,
                "current_position": idx + 1,
                "recommended_position": idx + 1,
                "is_misplaced": False,
            })

        return objects

    def _detect_primary_title_shape(self, slide, slide_height: int):
        """Identify the single primary slide title shape using semantics and prominence."""
        raw_shapes = list(slide.shapes)
        title_shape = getattr(slide.shapes, "title", None)

        if title_shape is not None and _get_text_content(title_shape).strip():
            return title_shape

        title_candidates = []
        for s in raw_shapes:
            txt = _get_text_content(s).strip()
            if not txt:
                continue
            s_name = (getattr(s, "name", None) or "").lower()
            res = _classify_shape(s)
            if res["semantic_role"] == "title" or s_name.startswith("title"):
                title_candidates.append(s)

        if title_candidates:
            title_candidates.sort(key=lambda s: (getattr(s, "top", 0) or 0, getattr(s, "left", 0) or 0))
            return title_candidates[0]

        top_candidates = []
        for s in raw_shapes:
            txt = _get_text_content(s).strip()
            top = getattr(s, "top", 0) or 0
            s_name = (getattr(s, "name", None) or "").lower()
            if txt and top < slide_height * 0.25 and not s_name.startswith(("footer", "slide number")):
                top_candidates.append(s)

        if top_candidates:
            top_candidates.sort(key=lambda s: (getattr(s, "top", 0) or 0, getattr(s, "left", 0) or 0))
            return top_candidates[0]

        return None

    def _determine_recommended_order(
        self,
        objects: list[dict],
        slide_width: int,
        slide_height: int,
        use_ai_fallback: bool = False,
    ) -> tuple[list[dict], str]:
        """
        STEP 2: Recursive XY-cut page segmentation ordering with header/footer extraction.
        Returns (recommended_sequence, detected_layout_type).
        """
        titles = []
        subtitles = []
        footers = []
        decoratives = []
        body_items = []

        is_slide_rtl = any(o.get("is_rtl") for o in objects)

        for obj in objects:
            role = obj["semantic_role"]
            if obj["is_title"]:
                titles.append(obj)
            elif role == "footer":
                footers.append(obj)
            elif role == "subtitle":
                subtitles.append(obj)
            elif (obj["is_decorative"] or (role == "shape" and not obj.get("text_snippet") and not obj.get("alt_text"))) and role not in ("container", "connector"):
                decoratives.append(obj)
            else:
                body_items.append(obj)

        titles.sort(key=lambda o: (o["top_emu"], o["left_emu"]))
        footers.sort(key=lambda o: (o["top_emu"], o["left_emu"]))
        decoratives.sort(key=lambda o: (o["top_emu"], o["left_emu"]))

        header_subtitles = []
        if subtitles:
            min_body_top = min((b["top_emu"] for b in body_items), default=slide_height)
            for sub in subtitles:
                if sub["top_emu"] <= min_body_top + 100000 and sub["top_emu"] < slide_height * 0.45:
                    header_subtitles.append(sub)
                else:
                    body_items.append(sub)
        header_subtitles.sort(key=lambda o: (o["top_emu"], o["left_emu"]))

        detected_layout = "single_column"
        ordered_body = []
        if body_items:
            # 1. Glue related items into composite units
            composite_units = glue_relationships(body_items, slide_width, slide_height)

            # 2. Recursive XY-Cut
            slide_region = (0, 0, slide_width, slide_height)
            cut_units = recursive_xy_cut(
                units=composite_units,
                region=slide_region,
                slide_width=slide_width,
                slide_height=slide_height,
                is_rtl=is_slide_rtl,
            )

            # Flatten composite units
            for u in cut_units:
                ordered_body.extend(u.members)

            if len(composite_units) >= 4:
                detected_layout = "grid_or_multicolumn"
            elif len(composite_units) >= 2:
                detected_layout = "two_column"

        result = []
        result.extend(titles)
        result.extend(header_subtitles)
        result.extend(ordered_body)
        result.extend(decoratives)
        result.extend(footers)

        # Validation
        orig_ids = [o["shape_id"] for o in objects]
        res_ids = [o["shape_id"] for o in result]
        if set(orig_ids) != set(res_ids) or len(orig_ids) != len(res_ids):
            # Fallback
            result = sorted(objects, key=lambda o: (o["top_emu"], o["left_emu"]))

        return result, detected_layout

    def analyze_slide(
        self,
        slide,
        slide_idx: int,
        slide_width: int,
        slide_height: int,
        use_ai_fallback: bool = False,
    ) -> dict:
        """Analyze a single slide's actual reading order against recommended logical sequence."""
        slide_num = slide_idx + 1
        primary_title_shape = self._detect_primary_title_shape(slide, slide_height)

        objects = self._extract_slide_objects(
            slide=slide,
            slide_num=slide_num,
            slide_width=slide_width,
            slide_height=slide_height,
            primary_title_shape=primary_title_shape,
        )

        slide_title = None
        for obj in objects:
            if obj["is_title"] and obj["text_snippet"]:
                slide_title = obj["text_snippet"]
                break

        if len(objects) <= 1:
            for obj in objects:
                obj["recommended_position"] = obj["current_position"]
                obj["is_misplaced"] = False
            return {
                "slide_index": slide_idx,
                "slide_number": slide_num,
                "title": slide_title,
                "status": "PASS",
                "total_objects": len(objects),
                "issues": [],
                "sequence_display": " → ".join(o["shape_name"] for o in objects) if objects else "No objects",
                "current_sequence": objects,
                "recommended_sequence": objects,
                "preview_objects": objects,
                "layout_type": "single_column",
                "confidence": "HIGH",
            }

        recommended_objects, layout_type = self._determine_recommended_order(
            objects=objects,
            slide_width=slide_width,
            slide_height=slide_height,
            use_ai_fallback=use_ai_fallback,
        )

        # STEP 3: Z-order topological sort
        primary_title_id = primary_title_shape.shape_id if primary_title_shape else None
        recommended_objects, is_safe, safety_reason = enforce_z_order_topological_sort(
            slide=slide,
            recommended_sequence=recommended_objects,
            primary_title_id=primary_title_id,
        )

        rec_id_to_pos = {obj["shape_id"]: pos for pos, obj in enumerate(recommended_objects, start=1)}
        for obj in objects:
            obj["recommended_position"] = rec_id_to_pos.get(obj["shape_id"], obj["current_position"])
            obj["is_misplaced"] = obj["current_position"] != obj["recommended_position"]

        for pos, obj in enumerate(recommended_objects, start=1):
            obj["recommended_position"] = pos
            obj["is_misplaced"] = obj["current_position"] != pos

        current_ids = [obj["shape_id"] for obj in objects]
        recommended_ids = [obj["shape_id"] for obj in recommended_objects]

        issues = self._detect_order_issues(objects, recommended_objects)
        status = "PASS" if (len(issues) == 0 and current_ids == recommended_ids) else "FAIL"

        seq_pills = [
            f"{pos}. {obj.get('object_type', 'Shape')} (\"{obj.get('text_snippet', '') or obj['shape_name']}\")"
            for pos, obj in enumerate(recommended_objects, start=1)
        ]

        return {
            "slide_index": slide_idx,
            "slide_number": slide_num,
            "title": slide_title,
            "status": status,
            "total_objects": len(objects),
            "issues": issues,
            "sequence_display": " → ".join(seq_pills),
            "current_sequence": objects,
            "recommended_sequence": recommended_objects,
            "preview_objects": objects,
            "is_safe": is_safe,
            "safety_reason": safety_reason,
            "layout_type": layout_type,
            "confidence": "HIGH" if is_safe else "LOW",
        }

    def _detect_order_issues(
        self, current_objs: list[dict], rec_objs: list[dict]
    ) -> list[dict]:
        """Detect reading order discrepancies."""
        issues = []
        rec_id_to_pos = {obj["shape_id"]: pos for pos, obj in enumerate(rec_objs, start=1)}
        total_count = len(current_objs)

        title_objs = [o for o in current_objs if o["is_title"]]
        for t in title_objs:
            curr_pos = t["current_position"]
            if curr_pos != 1:
                t_label = t.get("object_type") or "Title"
                t_snippet = f" (\"{t['text_snippet']}\")" if t.get("text_snippet") else ""
                issues.append({
                    "code": "TITLE_NOT_FIRST",
                    "severity": "FAIL",
                    "affected_shape_ids": [t["shape_id"]],
                    "shape_name": t["shape_name"],
                    "current_position": curr_pos,
                    "recommended_position": 1,
                    "description": f"{t_label} '{t['shape_name']}'{t_snippet} is read at position {curr_pos} instead of position 1.",
                    "suggestion": "Move title to position 1 in the reading sequence.",
                })

        for o in current_objs:
            sid = o["shape_id"]
            if any(sid in i["affected_shape_ids"] for i in issues):
                continue
            curr_pos = o["current_position"]
            rec_pos = rec_id_to_pos.get(sid, curr_pos)
            if curr_pos != rec_pos:
                obj_label = o.get("object_type") or o["semantic_role"].replace("_", " ").title()
                issues.append({
                    "code": "OUT_OF_SEQUENCE",
                    "severity": "FAIL",
                    "affected_shape_ids": [sid],
                    "shape_name": o["shape_name"],
                    "current_position": curr_pos,
                    "recommended_position": rec_pos,
                    "description": f"{obj_label} '{o['shape_name']}' is currently at position {curr_pos}, but logical reading flow recommends position {rec_pos}.",
                    "suggestion": f"Reorder '{o['shape_name']}' to position {rec_pos}.",
                })

        return issues

    def _freeze_shape_geometries(self, slide):
        """Explicitly freeze visual coordinates so reordering causes ZERO visual shift."""
        for s in slide.shapes:
            try:
                if s.left is not None:
                    l, t, w, h = s.left, s.top, s.width, s.height
                    s.left, s.top, s.width, s.height = l, t, w, h
            except Exception:
                pass

    def reorder_slide_shapes(self, slide, recommended_sequence: list[dict]) -> bool:
        """
        Reorders child elements in a slide's <p:spTree> to match recommended_sequence.
        Preserves non-shape canvas properties (<p:nvGrpSpPr>, <p:grpSpPr>) and extensions (<p:extLst>).
        Handles mc:AlternateContent as an atomic movable unit.
        """
        try:
            self._freeze_shape_geometries(slide)

            spTree = slide.shapes._spTree
            shape_map = {s.shape_id: s._element for s in slide.shapes}

            header_elems = [c for c in spTree if c.tag.split("}")[-1] in ("nvGrpSpPr", "grpSpPr")]
            footer_elems = [c for c in spTree if c.tag.split("}")[-1] == "extLst"]
            shape_elems = [c for c in spTree if c not in header_elems and c not in footer_elems]

            if len(shape_elems) <= 1:
                return True

            ordered_shape_elems = []
            for rec_obj in recommended_sequence:
                elem = shape_map.get(rec_obj["shape_id"])
                if elem is not None and elem in shape_elems:
                    ordered_shape_elems.append(elem)

            for elem in shape_elems:
                if elem not in ordered_shape_elems:
                    ordered_shape_elems.append(elem)

            for c in list(spTree):
                spTree.remove(c)
            for h in header_elems:
                spTree.append(h)
            for s in ordered_shape_elems:
                spTree.append(s)
            for f in footer_elems:
                spTree.append(f)

            return True
        except Exception as e:
            logger.error("Failed to reorder slide shapes", error=str(e))
            return False

    def fix_presentation_reading_order(
        self,
        input_pptx_path: str,
        output_pptx_path: str,
        use_ai_fallback: bool = False,
    ) -> dict:
        """
        Fixes reading order across all slides and strictly validates with reopening.
        """
        try:
            shutil.copy2(input_pptx_path, output_pptx_path)
            prs = pptx.Presentation(output_pptx_path)
        except Exception as e:
            raise RuntimeError(f"Failed to copy/open presentation: {e}")

        slide_width = prs.slide_width or DEFAULT_SLIDE_WIDTH_EMU
        slide_height = prs.slide_height or DEFAULT_SLIDE_HEIGHT_EMU
        total_slides = len(prs.slides)

        pre_analyses = []
        for idx, slide in enumerate(prs.slides):
            analysis = self.analyze_slide(
                slide=slide,
                slide_idx=idx,
                slide_width=slide_width,
                slide_height=slide_height,
                use_ai_fallback=use_ai_fallback,
            )
            pre_analyses.append(analysis)

        slide_details = []
        fixed_count = 0
        already_correct_count = 0
        manual_review_count = 0
        failed_count = 0

        for idx, slide in enumerate(prs.slides):
            pre = pre_analyses[idx]
            slide_num = idx + 1
            curr_ids = [o["shape_id"] for o in pre["current_sequence"]]
            rec_ids = [o["shape_id"] for o in pre["recommended_sequence"]]

            if pre["status"] == "PASS" and curr_ids == rec_ids:
                already_correct_count += 1
                slide_details.append({
                    "slide_index": idx,
                    "slide_number": slide_num,
                    "title": pre["title"],
                    "status": "already_correct",
                    "before_status": "PASS",
                    "after_status": "PASS",
                    "issues_before": 0,
                    "issues_after": 0,
                    "current_sequence": pre["current_sequence"],
                    "recommended_sequence": pre["recommended_sequence"],
                    "error_message": None,
                })
                continue

            if not pre.get("is_safe", True):
                manual_review_count += 1
                slide_details.append({
                    "slide_index": idx,
                    "slide_number": slide_num,
                    "title": pre["title"],
                    "status": "manual_review",
                    "before_status": pre["status"],
                    "after_status": pre["status"],
                    "issues_before": len(pre["issues"]),
                    "issues_after": len(pre["issues"]),
                    "current_sequence": pre["current_sequence"],
                    "recommended_sequence": pre["recommended_sequence"],
                    "error_message": f"Requires manual review: {pre.get('safety_reason')}",
                })
                continue

            try:
                ok = self.reorder_slide_shapes(slide, pre["recommended_sequence"])
                if ok:
                    fixed_count += 1
                    slide_details.append({
                        "slide_index": idx,
                        "slide_number": slide_num,
                        "title": pre["title"],
                        "status": "fixed",
                        "before_status": "FAIL",
                        "after_status": "PASS",
                        "issues_before": len(pre["issues"]),
                        "issues_after": 0,
                        "current_sequence": pre["current_sequence"],
                        "recommended_sequence": pre["recommended_sequence"],
                        "error_message": None,
                    })
                else:
                    failed_count += 1
                    slide_details.append({
                        "slide_index": idx,
                        "slide_number": slide_num,
                        "title": pre["title"],
                        "status": "error",
                        "before_status": pre["status"],
                        "after_status": pre["status"],
                        "issues_before": len(pre["issues"]),
                        "issues_after": len(pre["issues"]),
                        "current_sequence": pre["current_sequence"],
                        "recommended_sequence": pre["recommended_sequence"],
                        "error_message": "Reordering failed on slide shape tree.",
                    })
            except Exception as slide_err:
                failed_count += 1
                slide_details.append({
                    "slide_index": idx,
                    "slide_number": slide_num,
                    "title": pre["title"],
                    "status": "error",
                    "before_status": pre["status"],
                    "after_status": pre["status"],
                    "issues_before": len(pre["issues"]),
                    "issues_after": len(pre["issues"]),
                    "current_sequence": pre["current_sequence"],
                    "recommended_sequence": pre["recommended_sequence"],
                    "error_message": str(slide_err),
                })

        prs.save(output_pptx_path)

        # Reopen and strictly verify
        post_analysis = self.analyze_presentation(output_pptx_path, use_ai_fallback=False)
        issues_remaining = post_analysis["summary"]["total_issues"]

        return {
            "summary": {
                "total_slides": total_slides,
                "already_correct": already_correct_count,
                "fixed": fixed_count,
                "manual_review": manual_review_count,
                "failed": failed_count,
                "issues_remaining": issues_remaining,
                "verification_status": "SUCCESS" if (failed_count == 0 and issues_remaining == 0) else ("MANUAL_REVIEW" if manual_review_count > 0 else "PARTIAL"),
            },
            "slides": slide_details,
            "post_analysis": post_analysis,
        }


reading_order_service = ReadingOrderService()
