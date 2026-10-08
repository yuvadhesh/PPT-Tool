"""
PPTX Parser Service — extracts slides, objects, text, and metadata.
Uses python-pptx for high-level access and lxml for OOXML-level accessibility properties.
"""
import hashlib
import io
from typing import Optional, Any
from pathlib import Path

from pptx import Presentation as PptxPresentation
from pptx.util import Emu
from pptx.enum.shapes import MSO_SHAPE_TYPE, PP_PLACEHOLDER
from lxml import etree

from app.core.logging import logger


# OOXML namespaces
NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "dgm": "http://schemas.openxmlformats.org/drawingml/2006/diagram",
}


def _get_alt_text(shape) -> tuple[Optional[str], Optional[str]]:
    """Extract alt text (description) and title from shape XML."""
    try:
        nvSpPr = shape.element.find(".//{%s}nvSpPr" % "http://schemas.openxmlformats.org/presentationml/2006/main")
        if nvSpPr is None:
            nvSpPr = shape.element.find(".//{%s}nvPicPr" % "http://schemas.openxmlformats.org/presentationml/2006/main")
        if nvSpPr is None:
            nvSpPr = shape.element.find(".//{%s}nvCxnSpPr" % "http://schemas.openxmlformats.org/presentationml/2006/main")
        if nvSpPr is None:
            nvSpPr = shape.element.find(".//{%s}nvGraphicFramePr" % "http://schemas.openxmlformats.org/presentationml/2006/main")
        if nvSpPr is None:
            nvSpPr = shape.element.find(".//{%s}nvGrpSpPr" % "http://schemas.openxmlformats.org/presentationml/2006/main")

        if nvSpPr is not None:
            cNvPr = nvSpPr.find("{%s}cNvPr" % "http://schemas.openxmlformats.org/presentationml/2006/main")
            if cNvPr is None:
                # Try without namespace prefix
                for child in nvSpPr:
                    if child.tag.endswith("cNvPr"):
                        cNvPr = child
                        break

            if cNvPr is not None:
                title = cNvPr.get("title", "")
                desc = cNvPr.get("descr", "")
                return desc or None, title or None

        # Fallback: search the entire element tree
        for elem in shape.element.iter():
            if elem.tag.endswith("cNvPr"):
                title = elem.get("title", "")
                desc = elem.get("descr", "")
                return desc or None, title or None

    except Exception as e:
        logger.debug("Error extracting alt text", error=str(e))
    return None, None


def _is_decorative(shape) -> bool:
    """Check if shape is marked as decorative via XML attribute."""
    try:
        for elem in shape.element.iter():
            if elem.tag.endswith("cNvPr"):
                return elem.get("isDecorative", "0") == "1"
    except Exception:
        pass
    return False


def _get_shape_type_str(shape) -> str:
    """Return a string classification of the shape type."""
    try:
        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            return "image"
        if shape.shape_type == MSO_SHAPE_TYPE.TABLE:
            return "table"
        if shape.shape_type == MSO_SHAPE_TYPE.CHART:
            return "chart"
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            return "group"
        if shape.shape_type == MSO_SHAPE_TYPE.MEDIA:
            return "video"
        if hasattr(shape, "is_placeholder") and shape.is_placeholder:
            ph_type = shape.placeholder_format.type if shape.placeholder_format else None
            if ph_type in (PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE):
                return "text_box"
        # Check for SmartArt (dgm namespace in element)
        if shape.element.tag.endswith("graphicFrame"):
            for elem in shape.element.iter():
                if "diagram" in elem.tag or "dgm" in elem.tag:
                    return "smart_art"
        if shape.has_text_frame:
            return "text_box"
    except Exception:
        pass
    return "shape"


def _extract_text_from_shape(shape) -> str:
    """Safely extract all text from a shape."""
    try:
        if shape.has_text_frame:
            return "\n".join(
                para.text for para in shape.text_frame.paragraphs
            )
    except Exception:
        pass
    return ""


def _get_image_hash(shape) -> Optional[str]:
    """Get SHA256 hash of image data for a picture shape."""
    try:
        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            image_data = shape.image.blob
            return hashlib.sha256(image_data).hexdigest()
    except Exception:
        pass
    return None


def _check_table_headers(shape) -> tuple[bool, bool, int, int, bool]:
    """Check table for header row, header column, empty cells, merged cells."""
    has_header_row = False
    has_header_col = False
    empty_cells = 0
    merged_cells = 0
    is_complex = False

    try:
        table = shape.table
        has_header_row = table.first_row
        has_header_col = table.first_col

        for row in table.rows:
            for cell in row.cells:
                if not cell.text.strip():
                    empty_cells += 1
                # Check for spans
                tc = cell._tc
                if int(tc.get("rowSpan", 1)) > 1 or int(tc.get("gridSpan", 1)) > 1:
                    merged_cells += 1

        is_complex = merged_cells > 0 or (len(table.rows) > 5 and len(table.columns) > 5)
    except Exception as e:
        logger.debug("Error checking table headers", error=str(e))

    return has_header_row, has_header_col, empty_cells, merged_cells, is_complex


def _extract_font_sizes(shape) -> list[float]:
    """Extract all font sizes from a shape's text."""
    sizes = []
    try:
        if shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    if run.font.size:
                        sizes.append(run.font.size.pt)
    except Exception:
        pass
    return sizes


def _check_animations(slide) -> tuple[bool, int, list[dict]]:
    """Check for animations on a slide."""
    has_animations = False
    animation_count = 0
    animation_list = []

    try:
        # Look for timing element in slide XML
        timing = slide.element.find(
            "{http://schemas.openxmlformats.org/presentationml/2006/main}timing"
        )
        if timing is not None:
            # Count animation nodes
            anim_nodes = timing.findall(
                ".//{http://schemas.openxmlformats.org/presentationml/2006/main}animEffect"
            )
            par_nodes = timing.findall(
                ".//{http://schemas.openxmlformats.org/presentationml/2006/main}par"
            )
            if par_nodes or anim_nodes:
                has_animations = True
                animation_count = len(anim_nodes) or len(par_nodes)
                for node in (anim_nodes or par_nodes)[:10]:
                    animation_list.append({
                        "tag": node.tag.split("}")[-1],
                        "attribs": dict(list(node.attrib.items())[:5]),
                    })
    except Exception as e:
        logger.debug("Error checking animations", error=str(e))

    return has_animations, animation_count, animation_list


def _extract_hyperlinks(shape) -> list[dict]:
    """Extract hyperlinks from a text shape."""
    links = []
    try:
        if shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    if run._r.rPr is not None:
                        # Look for hlinkClick element
                        for child in run._r.rPr:
                            if child.tag.endswith("hlinkClick"):
                                r_id = child.get(
                                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", ""
                                )
                                url = ""
                                try:
                                    url = shape.part.rels[r_id].target_ref
                                except Exception:
                                    pass
                                links.append({
                                    "text": run.text,
                                    "url": url,
                                    "run_text": run.text,
                                })
    except Exception:
        pass
    return links


def _calculate_contrast_ratio(fg_rgb: Optional[tuple], bg_rgb: Optional[tuple]) -> Optional[float]:
    """Calculate WCAG contrast ratio between two RGB colors."""
    if not fg_rgb or not bg_rgb:
        return None

    def relative_luminance(rgb):
        r, g, b = [c / 255.0 for c in rgb]
        r = r / 12.92 if r <= 0.03928 else ((r + 0.055) / 1.055) ** 2.4
        g = g / 12.92 if g <= 0.03928 else ((g + 0.055) / 1.055) ** 2.4
        b = b / 12.92 if b <= 0.03928 else ((b + 0.055) / 1.055) ** 2.4
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    l1 = relative_luminance(fg_rgb)
    l2 = relative_luminance(bg_rgb)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


class PptxParserService:
    """Parses PPTX files and extracts structured data for accessibility analysis."""

    def parse_presentation(self, pptx_path: str) -> dict:
        """Parse a PPTX file and return structured metadata."""
        prs = PptxPresentation(pptx_path)
        slide_width = prs.slide_width or 9144000
        slide_height = prs.slide_height or 6858000

        # Detect presentation language from core properties
        prs_language = None
        try:
            if prs.core_properties.language:
                prs_language = prs.core_properties.language
        except Exception:
            pass

        slides_data = []
        all_titles = []

        for slide_idx, slide in enumerate(prs.slides):
            slide_data = self._parse_slide(slide, slide_idx, pptx_path)
            slides_data.append(slide_data)
            if slide_data.get("title"):
                all_titles.append((slide_idx, slide_data["title"]))

        # Mark duplicate titles
        title_counts = {}
        for idx, title in all_titles:
            title_lower = title.lower().strip()
            if title_lower not in title_counts:
                title_counts[title_lower] = []
            title_counts[title_lower].append(idx)

        duplicates = {
            title: idxs for title, idxs in title_counts.items() if len(idxs) > 1
        }
        for slide_data in slides_data:
            t = (slide_data.get("title") or "").lower().strip()
            slide_data["has_duplicate_title"] = t in duplicates

        return {
            "slide_count": len(prs.slides),
            "slide_width_emu": slide_width,
            "slide_height_emu": slide_height,
            "presentation_language": prs_language,
            "slides": slides_data,
            "duplicate_titles": duplicates,
        }

    def _parse_slide(self, slide, slide_idx: int, pptx_path: str) -> dict:
        """Parse a single slide and all its objects."""
        slide_number = slide_idx + 1

        # Speaker notes
        notes_text = ""
        has_notes = False
        try:
            if slide.has_notes_slide:
                notes_frame = slide.notes_slide.notes_text_frame
                notes_text = notes_frame.text if notes_frame else ""
                has_notes = bool(notes_text.strip())
        except Exception:
            pass

        # Title
        slide_title = None
        title_placeholder_id = None
        try:
            title_shape = slide.shapes.title
            if title_shape:
                slide_title = title_shape.text.strip() or None
                title_placeholder_id = str(title_shape.shape_id)
        except Exception:
            pass

        # Animations
        has_animations, animation_count, animation_list = _check_animations(slide)

        # Hash the slide XML
        slide_xml_hash = hashlib.sha256(
            etree.tostring(slide.element, pretty_print=False)
        ).hexdigest()

        objects_data = []
        for shape in slide.shapes:
            obj_data = self._parse_shape(shape, slide_idx)
            objects_data.append(obj_data)

        # Compute natural reading order (title first, then top-to-bottom, left-to-right)
        title_id = str(title_placeholder_id) if title_placeholder_id else None
        def reading_sort_key(obj):
            sid = str(obj.get("shape_id"))
            if title_id and sid == title_id:
                return (-1, 0, 0)
            top = obj.get("top_emu") or 0
            left = obj.get("left_emu") or 0
            row = round(top / 350000)
            return (0, row, left)

        sorted_objs = sorted(objects_data, key=reading_sort_key)
        for order_idx, obj in enumerate(sorted_objs, start=1):
            obj["reading_order"] = order_idx

        return {
            "slide_index": slide_idx,
            "slide_number": slide_number,
            "title": slide_title,
            "title_placeholder_id": title_placeholder_id,
            "speaker_notes": notes_text,
            "has_notes": has_notes,
            "has_animations": has_animations,
            "animation_count": animation_count,
            "animation_list": animation_list,
            "slide_xml_hash": slide_xml_hash,
            "object_count": len(objects_data),
            "objects": objects_data,
        }

    def _parse_shape(self, shape, slide_idx: int) -> dict:
        """Parse a single shape and return structured data."""
        object_type = _get_shape_type_str(shape)
        alt_text, alt_title = _get_alt_text(shape)
        is_decorative = _is_decorative(shape)
        text_content = _extract_text_from_shape(shape)
        image_hash = _get_image_hash(shape)
        font_sizes = _extract_font_sizes(shape)

        extra_data = {}
        has_table_headers = None
        chart_title = None
        has_audio = False
        has_video = False

        if object_type == "table":
            has_header_row, has_header_col, empty_cells, merged_cells, is_complex = _check_table_headers(shape)
            extra_data = {
                "has_header_row": has_header_row,
                "has_header_col": has_header_col,
                "empty_cells": empty_cells,
                "merged_cells": merged_cells,
                "is_complex": is_complex,
            }
            has_table_headers = has_header_row

        elif object_type == "chart":
            try:
                chart = shape.chart
                chart_title = chart.chart_title.text_frame.text if chart.has_title else None
                extra_data = {
                    "chart_type": str(chart.chart_type),
                    "has_legend": chart.has_legend,
                    "series_count": len(chart.series),
                }
            except Exception:
                pass

        elif object_type == "video":
            has_video = True

        hyperlinks = _extract_hyperlinks(shape)

        try:
            left = shape.left or 0
            top = shape.top or 0
            width = shape.width or 0
            height = shape.height or 0
        except Exception:
            left = top = width = height = 0

        return {
            "shape_id": shape.shape_id,
            "name": shape.name,
            "object_type": object_type,
            "left_emu": left,
            "top_emu": top,
            "width_emu": width,
            "height_emu": height,
            "text_content": text_content or None,
            "alt_text": alt_text,
            "alt_text_title": alt_title,
            "is_decorative": is_decorative,
            "reading_order": None,  # Will be determined by analysis
            "has_audio": has_audio,
            "has_video": has_video,
            "has_animation": False,
            "chart_title": chart_title,
            "has_table_headers": has_table_headers,
            "image_hash": image_hash,
            "font_sizes": font_sizes,
            "hyperlinks": hyperlinks,
            "extra_data": extra_data,
        }

    def get_image_data(self, pptx_path: str, slide_idx: int, shape_id: int) -> Optional[bytes]:
        """Extract raw image bytes from a specific shape."""
        try:
            prs = PptxPresentation(pptx_path)
            slide = prs.slides[slide_idx]
            for shape in slide.shapes:
                if shape.shape_id == shape_id and shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                    return shape.image.blob
        except Exception as e:
            logger.error("Error extracting image data", error=str(e))
        return None


pptx_parser = PptxParserService()
