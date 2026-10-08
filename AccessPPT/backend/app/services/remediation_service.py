"""
Safe Remediation Service — applies ONLY accessibility metadata changes to PPTX.
Never modifies visible content, colors, fonts, positions, or images.
"""
import shutil
from typing import Optional
from pathlib import Path

from pptx import Presentation as PptxPresentation
from pptx.util import Emu
from pptx.oxml import parse_xml
from pptx.oxml.ns import nsdecls
from lxml import etree

from app.core.logging import logger


# Allowed safe fix types
SAFE_FIX_TYPES = {
    "set_alt_text",
    "mark_decorative",
    "set_table_header",
    "set_language",
    "set_reading_order",
    "set_chart_description",
    "set_slide_title",
    "remove_animations",
}


class RemediationService:
    """
    Applies safe accessibility metadata changes to a copy of the PPTX.
    The original file is NEVER modified.
    """

    def apply_fixes(
        self,
        original_path: str,
        output_path: str,
        fixes: list[dict],
    ) -> tuple[bool, str]:
        """
        Apply a list of fixes to a copy of the PPTX.

        Each fix dict:
        {
            "type": "set_alt_text",
            "slide_index": 0,
            "shape_id": 5,
            "value": "Bar chart showing quarterly revenue..."
        }

        Returns (success, error_message)
        """
        # Create working copy — never touch the original
        try:
            shutil.copy2(original_path, output_path)
        except Exception as e:
            return False, f"Failed to copy original: {e}"

        try:
            prs = PptxPresentation(output_path)
        except Exception as e:
            return False, f"Failed to open PPTX copy: {e}"

        applied = 0
        errors = []

        for fix in fixes:
            fix_type = fix.get("type")
            if fix_type not in SAFE_FIX_TYPES:
                errors.append(f"Unsafe fix type rejected: {fix_type}")
                logger.warning("Rejected unsafe fix type", fix_type=fix_type)
                continue

            slide_idx = fix.get("slide_index")
            shape_id = fix.get("shape_id")
            value = fix.get("value")

            try:
                if slide_idx is not None and 0 <= slide_idx < len(prs.slides):
                    slide = prs.slides[slide_idx]
                    shape = self._find_shape(slide, shape_id)
                    if shape is None and shape_id is not None:
                        errors.append(f"Shape {shape_id} not found on slide {slide_idx}")
                        continue

                    if fix_type == "set_alt_text":
                        self._set_alt_text(shape, value or "")
                        applied += 1
                    elif fix_type == "mark_decorative":
                        self._mark_decorative(shape, bool(value))
                        applied += 1
                    elif fix_type == "set_table_header":
                        self._set_table_header(shape)
                        applied += 1
                    elif fix_type == "set_reading_order":
                        self._reorder_reading_order(slide)
                        applied += 1
                    elif fix_type == "set_chart_description":
                        self._set_alt_text(shape, value or "")
                        applied += 1
                    elif fix_type == "set_slide_title":
                        title_shape = shape if shape is not None else self._find_title_shape(slide)
                        if title_shape is not None:
                            self._set_slide_title(title_shape, value or "")
                            applied += 1
                        else:
                            errors.append(f"Title shape not found on slide {slide_idx}")
                    elif fix_type == "remove_animations":
                        self._remove_animations(slide)
                        applied += 1

                elif fix_type == "set_language":
                    self._set_language(prs, value or "en-US")
                    applied += 1

            except Exception as e:
                errors.append(f"Fix {fix_type} failed: {e}")
                logger.error("Fix application error", fix=fix, error=str(e))

        # Always synchronize reading order and outline view placeholders across all slides
        self.sync_all_slides_reading_order_and_outline(prs)

        try:
            prs.save(output_path)
        except Exception as e:
            return False, f"Failed to save remediated PPTX: {e}"

        logger.info("Fixes applied", applied=applied, errors=len(errors))
        if errors:
            logger.warning("Some fixes failed", errors=errors)

        return True, "; ".join(errors) if errors else ""

    def _find_shape(self, slide, shape_id: Optional[int]):
        """Find a shape by ID on a slide, recursively searching groups if needed."""
        if shape_id is None:
            return None
        return self._search_shapes(slide.shapes, shape_id)

    def _search_shapes(self, shapes, shape_id: int):
        for shape in shapes:
            if shape.shape_id == shape_id:
                return shape
            if getattr(shape, "shape_type", None) == 6 or hasattr(shape, "shapes"):  # MSO_SHAPE_TYPE.GROUP
                try:
                    nested = self._search_shapes(shape.shapes, shape_id)
                    if nested is not None:
                        return nested
                except Exception:
                    pass
        return None

    def _set_alt_text(self, shape, description: str):
        """Set the alt text (descr attribute) on a shape."""
        for elem in shape.element.iter():
            if elem.tag.endswith("cNvPr"):
                elem.set("descr", description)
                return
        raise ValueError("Could not find cNvPr element to set alt text")

    def _mark_decorative(self, shape, is_decorative: bool):
        """Set or remove the isDecorative attribute on a shape."""
        for elem in shape.element.iter():
            if elem.tag.endswith("cNvPr"):
                if is_decorative:
                    elem.set("isDecorative", "1")
                    elem.set("descr", "")  # Decorative images should have empty alt text
                else:
                    if "isDecorative" in elem.attrib:
                        del elem.attrib["isDecorative"]
                return

    def _set_table_header(self, shape):
        """Enable the first row as a header row on a table."""
        try:
            shape.table._tbl.set("firstRow", "1")
        except Exception as e:
            raise ValueError(f"Failed to set table header: {e}")

    def _set_language(self, prs: PptxPresentation, language_tag: str):
        """Set the presentation default language in the XML."""
        try:
            # Set on core properties
            prs.core_properties.language = language_tag
        except Exception as e:
            logger.warning("Could not set language via core_properties", error=str(e))

    def _find_title_shape(self, slide):
        """Locate title shape on a slide via .title or placeholder type."""
        try:
            if slide.shapes.title is not None:
                return slide.shapes.title
        except Exception:
            pass
        for shape in slide.shapes:
            try:
                if shape.is_placeholder and shape.placeholder_format.type in (1, 3):
                    return shape
            except Exception:
                pass
        return None

    def _set_slide_title(self, shape, new_title: str):
        """
        Update slide title text preserving all formatting, fonts, bold, and runs.
        """
        if not shape or not getattr(shape, "has_text_frame", False):
            return

        tf = shape.text_frame
        current_text = tf.text.strip()
        new_title = new_title.strip()

        if not new_title or current_text == new_title:
            return

        # Case 1: If new_title is an extension/continuation of current_title (e.g. adding ' (1 of 4)')
        if new_title.startswith(current_text):
            suffix = new_title[len(current_text):]
            paragraphs_with_text = [p for p in tf.paragraphs if p.text.strip()]
            target_p = paragraphs_with_text[-1] if paragraphs_with_text else tf.paragraphs[-1]
            if target_p.runs:
                target_p.runs[-1].text += suffix
            else:
                target_p.text += suffix
            return

        # Case 2: Clean replacement while preserving font styling of the first run
        paragraphs = tf.paragraphs
        if not paragraphs:
            tf.text = new_title
            return

        first_p = paragraphs[0]
        if first_p.runs:
            first_p.runs[0].text = new_title
            for r in first_p.runs[1:]:
                r.text = ""
            for p in paragraphs[1:]:
                for r in p.runs:
                    r.text = ""
        else:
            first_p.text = new_title
            for p in paragraphs[1:]:
                p.text = ""

    def _remove_animations(self, slide):
        """Remove animation timing elements so all content is statically accessible."""
        try:
            timing = slide.element.find(
                "{http://schemas.openxmlformats.org/presentationml/2006/main}timing"
            )
            if timing is not None:
                slide.element.remove(timing)
                return True
        except Exception as e:
            logger.warning("Could not remove animation timing", error=str(e))
        return False

    def _freeze_shape_geometries(self, slide):
        """
        Freeze explicit left, top, width, height on all slide shapes.
        This guarantees that even when placeholder indices or types are updated,
        the shape's geometry never loses inheritance or shifts on screen.
        """
        for s in slide.shapes:
            try:
                if s.left is not None:
                    l, t, w, h = s.left, s.top, s.width, s.height
                    s.left, s.top, s.width, s.height = l, t, w, h
            except Exception:
                pass

    def _reorder_reading_order(self, slide):
        """
        Reorder OpenXML shapes in the slide's spTree so screen readers follow
        the natural visual reading sequence, directly updating PowerPoint Reading Order pane.
        """
        try:
            from app.services.reading_order_service import reading_order_service
            slide_width = 9144000
            slide_height = 6858000
            try:
                prs = slide.part.package.presentation_part.presentation
                slide_width = prs.slide_width or slide_width
                slide_height = prs.slide_height or slide_height
            except Exception:
                pass

            analysis = reading_order_service.analyze_slide(
                slide=slide,
                slide_idx=0,
                slide_width=slide_width,
                slide_height=slide_height,
                use_ai_fallback=False,
            )
            reading_order_service.reorder_slide_shapes(slide, analysis["recommended_sequence"])

            # Outline View Placeholder Generation & Resequencing
            title_shape = getattr(slide.shapes, "title", None)
            text_shapes = []
            for s in slide.shapes:
                if s == title_shape or (
                    getattr(s, "is_placeholder", False)
                    and getattr(s.placeholder_format, "type", None) in (1, 3)
                ):
                    continue
                if getattr(s, "has_text_frame", False) and s.text_frame.text.strip():
                    text_shapes.append(s)

            for idx_num, s in enumerate(text_shapes, start=1):
                nvPr = s._element.xpath('.//p:nvPr')
                if nvPr:
                    existing_ph = nvPr[0].xpath('./p:ph')
                    if existing_ph:
                        existing_ph[0].set('idx', str(idx_num))
                    else:
                        ph_xml = parse_xml(f'<p:ph {nsdecls("p")} type="body" idx="{idx_num}"/>')
                        nvPr[0].append(ph_xml)
        except Exception as e:
            logger.warning("Could not reorder slide shapes for reading order", error=str(e))

    def sync_all_slides_reading_order_and_outline(self, prs):
        """
        Synchronize Reading Order and Outline View placeholders across all slides in presentation.
        """
        for slide in prs.slides:
            self._reorder_reading_order(slide)


remediation_service = RemediationService()
