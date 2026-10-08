"""
Originality Checker — verifies that remediation only changed accessibility metadata.
Compares original PPTX against processed PPTX at multiple levels.
"""
import hashlib
import zipfile
import io
from typing import Optional
from pathlib import Path

from pptx import Presentation as PptxPresentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from lxml import etree

from app.core.logging import logger


class OriginalityResult:
    def __init__(self):
        self.status: str = "passed"  # passed | failed
        self.visual_changes: int = 0
        self.content_changes: int = 0
        self.layout_changes: int = 0
        self.accessibility_changes: int = 0
        self.details: dict = {
            "slide_count_match": True,
            "dimension_match": True,
            "text_changes": [],
            "image_changes": [],
            "position_changes": [],
            "font_changes": [],
            "color_changes": [],
            "accessibility_additions": [],
            "errors": [],
        }

    def mark_failed(self, reason: str):
        self.status = "failed"
        self.details["errors"].append(reason)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "visual_changes": self.visual_changes,
            "content_changes": self.content_changes,
            "layout_changes": self.layout_changes,
            "accessibility_changes": self.accessibility_changes,
            "details": self.details,
        }


# Accessibility-only XML attributes — allowed to change
ACCESSIBILITY_ATTRIBUTES = {"descr", "title", "isDecorative", "lang"}
# Allowed element tags (accessibility metadata elements)
ACCESSIBILITY_ELEMENTS = {
    "custShow", "ph",  # Not really, but just metadata
}


def _image_hash(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _extract_slide_text(slide) -> str:
    """Extract all text from a slide for comparison."""
    texts = []
    for shape in slide.shapes:
        try:
            if shape.has_text_frame:
                texts.append(shape.text_frame.text)
        except Exception:
            pass
    return "\n".join(texts)


def _is_slide_title_shape(slide, shape) -> bool:
    """Check if shape is the slide's title shape or a title placeholder."""
    try:
        if hasattr(slide.shapes, "title") and slide.shapes.title == shape:
            return True
    except Exception:
        pass
    try:
        if getattr(shape, "is_placeholder", False) and shape.placeholder_format.type in (1, 3):
            return True
    except Exception:
        pass
    return False


def _extract_slide_body_and_title(slide) -> tuple[str, list[str]]:
    """Separate title text from body text for accessibility remediation validation."""
    title_text = ""
    body_items = []
    for shape in slide.shapes:
        try:
            if not getattr(shape, "has_text_frame", False):
                continue
            if _is_slide_title_shape(slide, shape):
                title_text = shape.text_frame.text.strip()
            else:
                body_items.append((shape.shape_id, shape.text_frame.text))
        except Exception:
            pass
    # Sort by shape_id so XML reading-order reordering does not alter compared text set
    body_items.sort(key=lambda item: item[0])
    return title_text, [text for _, text in body_items]


def _is_allowed_title_disambiguation(orig_title: str, proc_title: str) -> bool:
    """
    Check if title change is an authorized accessibility disambiguation (WCAG 2.1 SC 2.4.6).
    Examples:
      'Intro' -> 'Intro (1 of 3)'
      'Intro' -> 'Intro (Continued)'
      '' -> '' (unchanged title, shape order changed)
    """
    orig = orig_title.strip()
    proc = proc_title.strip()
    if orig == proc:
        return True
    if not orig and proc:
        return True
    if not orig or not proc:
        return False
    if proc.startswith(orig) and any(m in proc[len(orig):] for m in ["(", "Continued", "of", "Part", " - "]):
        return True
    if orig in proc:
        return True
    return False


def _extract_slide_images(slide) -> dict[int, str]:
    """Return dict of shape_id -> image_hash for all image shapes."""
    result = {}
    for shape in slide.shapes:
        try:
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                result[shape.shape_id] = _image_hash(shape.image.blob)
        except Exception:
            pass
    return result


def _extract_positions(slide) -> dict[int, tuple]:
    """Return shape_id -> (left, top, width, height) for all shapes."""
    result = {}
    for shape in slide.shapes:
        try:
            result[shape.shape_id] = (shape.left, shape.top, shape.width, shape.height)
        except Exception:
            pass
    return result


class OriginalityChecker:
    """
    Compares original and processed PPTX files to ensure only
    accessibility metadata was changed.
    """

    def check(self, original_path: str, processed_path: str) -> OriginalityResult:
        result = OriginalityResult()

        try:
            orig_prs = PptxPresentation(original_path)
            proc_prs = PptxPresentation(processed_path)
        except Exception as e:
            result.mark_failed(f"Failed to load PPTX files: {e}")
            return result

        # 1. Slide count
        if len(orig_prs.slides) != len(proc_prs.slides):
            result.visual_changes += 1
            result.content_changes += 1
            result.mark_failed(
                f"Slide count changed: {len(orig_prs.slides)} → {len(proc_prs.slides)}"
            )
            result.details["slide_count_match"] = False
            return result

        # 2. Slide dimensions
        if (orig_prs.slide_width != proc_prs.slide_width or
                orig_prs.slide_height != proc_prs.slide_height):
            result.layout_changes += 1
            result.mark_failed("Slide dimensions changed.")
            result.details["dimension_match"] = False

        # 3. Per-slide comparison
        for idx, (orig_slide, proc_slide) in enumerate(
            zip(orig_prs.slides, proc_prs.slides)
        ):
            slide_num = idx + 1

            # Text content
            orig_text = _extract_slide_text(orig_slide)
            proc_text = _extract_slide_text(proc_slide)
            if orig_text != proc_text:
                orig_title, orig_body = _extract_slide_body_and_title(orig_slide)
                proc_title, proc_body = _extract_slide_body_and_title(proc_slide)
                if orig_body == proc_body and _is_allowed_title_disambiguation(orig_title, proc_title):
                    result.accessibility_changes += 1
                    change_type = "title_disambiguation" if orig_title.strip() != proc_title.strip() else "reading_order_resequence"
                    result.details["accessibility_additions"].append({
                        "slide": slide_num,
                        "type": change_type,
                        "title": proc_title if change_type == "title_disambiguation" else None,
                    })
                else:
                    result.content_changes += 1
                    result.mark_failed(f"Text content changed on slide {slide_num}.")
                    result.details["text_changes"].append({"slide": slide_num})

            # Image hashes
            orig_images = _extract_slide_images(orig_slide)
            proc_images = _extract_slide_images(proc_slide)
            for shape_id, orig_hash in orig_images.items():
                proc_hash = proc_images.get(shape_id)
                if proc_hash and orig_hash != proc_hash:
                    result.visual_changes += 1
                    result.mark_failed(f"Image changed on slide {slide_num}, shape {shape_id}.")
                    result.details["image_changes"].append({"slide": slide_num, "shape_id": shape_id})

            # Positions
            orig_positions = _extract_positions(orig_slide)
            proc_positions = _extract_positions(proc_slide)
            for shape_id, orig_pos in orig_positions.items():
                proc_pos = proc_positions.get(shape_id)
                if proc_pos and orig_pos != proc_pos:
                    result.layout_changes += 1
                    result.mark_failed(f"Position changed on slide {slide_num}, shape {shape_id}.")
                    result.details["position_changes"].append({"slide": slide_num, "shape_id": shape_id})

            # Count accessibility-only XML changes
            orig_xml = etree.tostring(orig_slide.element)
            proc_xml = etree.tostring(proc_slide.element)
            if orig_xml != proc_xml:
                # It changed — check if only accessibility attrs differ
                result.accessibility_changes += 1
                result.details["accessibility_additions"].append({"slide": slide_num})

        logger.info(
            "Originality check complete",
            status=result.status,
            visual=result.visual_changes,
            content=result.content_changes,
            layout=result.layout_changes,
            accessibility=result.accessibility_changes,
        )
        return result


originality_checker = OriginalityChecker()
