import os
import tempfile
import pytest
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.shapes import MSO_SHAPE_TYPE

from app.services.rule_engine import (
    is_filename_alt_text,
    is_generic_title,
    is_generic_link_text,
    RULES,
)
from app.services.accessibility_analyzer import calculate_score
from app.services.originality_checker import originality_checker, _is_allowed_title_disambiguation
from app.services.remediation_service import remediation_service


def test_rule_engine_helpers():
    # Alt text filenames
    assert is_filename_alt_text("IMG_1234.png") is True
    assert is_filename_alt_text("diagram.jpg") is True
    assert is_filename_alt_text("A quarterly sales bar chart") is False

    # Generic titles
    assert is_generic_title("Slide 1") is True
    assert is_generic_title("Untitled") is True
    assert is_generic_title("Introduction to Quantum Mechanics") is False

    # Generic link text
    assert is_generic_link_text("click here") is True
    assert is_generic_link_text("more") is True
    assert is_generic_link_text("Download the Q3 Financial Report") is False


def test_calculate_score():
    assert calculate_score(0, 0, 0, 10) == 100.0
    assert calculate_score(1, 0, 0, 0) == 0.0
    score = calculate_score(1, 2, 0, 7)
    assert 0.0 <= score <= 100.0


def test_title_disambiguation_logic():
    assert _is_allowed_title_disambiguation("Agenda", "Agenda") is True
    assert _is_allowed_title_disambiguation("", "") is True
    assert _is_allowed_title_disambiguation("Financial Results", "Financial Results (1 of 3)") is True
    assert _is_allowed_title_disambiguation("Methodology", "Methodology (Continued)") is True
    assert _is_allowed_title_disambiguation("Original Title", "Completely Different Topic") is False


def test_remediation_and_originality():
    with tempfile.TemporaryDirectory() as tmp_dir:
        orig_file = os.path.join(tmp_dir, "orig.pptx")
        proc_file = os.path.join(tmp_dir, "proc.pptx")

        # Create a sample PPTX
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = "Q3 Overview"
        subtitle = slide.placeholders[1]
        subtitle.text = "Company Performance"
        prs.save(orig_file)

        # Apply safe fix: update slide title disambiguation and set alt text
        fixes = [
            {
                "type": "set_slide_title",
                "slide_index": 0,
                "shape_id": slide.shapes.title.shape_id,
                "value": "Q3 Overview (1 of 2)",
            }
        ]
        success, err = remediation_service.apply_fixes(orig_file, proc_file, fixes)
        assert success is True, err

        # Verify with OriginalityChecker
        result = originality_checker.check(orig_file, proc_file)
        assert result.status == "passed"
        assert result.visual_changes == 0
        assert result.content_changes == 0
        assert result.accessibility_changes >= 1

        # Test failure: modify shape position (visual alteration)
        prs_tampered = Presentation(proc_file)
        prs_tampered.slides[0].shapes[0].left += Inches(1)
        tampered_pos_file = os.path.join(tmp_dir, "tampered_pos.pptx")
        prs_tampered.save(tampered_pos_file)

        res_tampered_pos = originality_checker.check(orig_file, tampered_pos_file)
        assert res_tampered_pos.status == "failed"
        assert res_tampered_pos.layout_changes > 0

        # Test failure: modify actual body text
        prs_tampered_txt = Presentation(proc_file)
        prs_tampered_txt.slides[0].placeholders[1].text = "Unlawful text rewrite."
        tampered_txt_file = os.path.join(tmp_dir, "tampered_txt.pptx")
        prs_tampered_txt.save(tampered_txt_file)

        res_tampered_txt = originality_checker.check(orig_file, tampered_txt_file)
        assert res_tampered_txt.status == "failed"
        assert res_tampered_txt.content_changes > 0


def test_reading_order_and_outline_generation():
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_file = os.path.join(tmp_dir, "test.pptx")
        proc_file = os.path.join(tmp_dir, "proc.pptx")

        prs = Presentation()
        # Add a slide with title and multiple text boxes
        slide = prs.slides.add_slide(prs.slide_layouts[6]) # blank layout
        
        # Add textbox at bottom
        tb2 = slide.shapes.add_textbox(Inches(1), Inches(4), Inches(4), Inches(1))
        tb2.text_frame.text = "Second paragraph"
        
        # Add title textbox at top
        tb1 = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(1))
        tb1.text_frame.text = "Slide Main Title"
        
        prs.save(test_file)

        # Run safe fixes with set_reading_order
        fixes = [{
            "type": "set_reading_order",
            "slide_index": 0,
            "shape_id": None,
            "value": "Reorder",
        }]
        success, err = remediation_service.apply_fixes(test_file, proc_file, fixes)
        assert success is True, err

        # Verify shapes are ordered top to bottom and have p:ph for Outline View
        proc_prs = Presentation(proc_file)
        proc_slide = proc_prs.slides[0]
        
        # Check that tb1 (top) is now first in spTree
        first_shape = proc_slide.shapes[0]
        assert "Slide Main Title" in first_shape.text_frame.text
        
        # Check that body shapes received p:ph tags for Outline View
        second_shape = proc_slide.shapes[1]
        phs = second_shape._element.xpath(".//p:nvPr/p:ph")
        assert len(phs) > 0
        assert phs[0].get("type") == "body"

        # Check originality passed
        res = originality_checker.check(test_file, proc_file)
        assert res.status == "passed"
        assert res.visual_changes == 0
        assert res.layout_changes == 0

