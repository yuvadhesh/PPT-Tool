"""
Unit tests for the dedicated Reading Order Checker Service.
Tests PowerPoint OOXML extraction, logical reading sequence validation,
discrepancy detection, and summary calculations.
"""
import os
import tempfile
import pytest
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.shapes import MSO_SHAPE_TYPE, MSO_SHAPE

from app.services.reading_order_service import reading_order_service


def test_reading_order_title_first_detection():
    """Verify that a slide where title is not read first fails with TITLE_NOT_FIRST."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        deck_path = os.path.join(tmp_dir, "title_test.pptx")
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank layout

        # Add a random textbox first (will be shape index 1 in XML)
        box1 = slide.shapes.add_textbox(Inches(1), Inches(4), Inches(4), Inches(2))
        box1.text = "Some body content that should not be read first"

        # Add a title at the top second (will be shape index 2 in XML)
        title_box = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
        title_box.text = "Quarterly Business Review"

        prs.save(deck_path)

        result = reading_order_service.analyze_presentation(deck_path, use_ai_fallback=False)
        assert result["summary"]["total_slides_checked"] == 1
        slide_res = result["slides"][0]

        assert slide_res["status"] == "FAIL"
        assert len(slide_res["issues"]) > 0
        issue_codes = [i["code"] for i in slide_res["issues"]]
        assert "TITLE_NOT_FIRST" in issue_codes
        assert "Quarterly Business Review" in slide_res["issues"][0]["description"]


def test_reading_order_correct_sequence_passes():
    """Verify that a slide with title first, then body text in order passes."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        deck_path = os.path.join(tmp_dir, "correct_test.pptx")
        prs = Presentation()
        # Title and content layout: title is shape 1, content is shape 2
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = "Accessible Presentation Title"
        slide.placeholders[1].text = "Subtitle and introduction text"

        prs.save(deck_path)

        result = reading_order_service.analyze_presentation(deck_path, use_ai_fallback=False)
        slide_res = result["slides"][0]
        assert slide_res["status"] == "PASS"
        assert len(slide_res["issues"]) == 0
        assert result["summary"]["slides_passed"] == 1
        assert result["summary"]["slides_failed"] == 0
        assert result["summary"]["compliance_rate"] == 100.0


def test_reading_order_two_column_layout():
    """Verify that a two-column slide orders column 1 top-to-bottom, then column 2."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        deck_path = os.path.join(tmp_dir, "two_column_test.pptx")
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        # Title
        t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
        t.text = "Comparison Slide"

        # Left Column (x = 1.0 inch)
        col1_head = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(3.5), Inches(0.8))
        col1_head.text = "Option A Heading"
        col1_body = slide.shapes.add_textbox(Inches(1), Inches(3.2), Inches(3.5), Inches(2))
        col1_body.text = "Option A Detailed points"

        # Right Column (x = 5.5 inches)
        col2_head = slide.shapes.add_textbox(Inches(5.5), Inches(2), Inches(3.5), Inches(0.8))
        col2_head.text = "Option B Heading"
        col2_body = slide.shapes.add_textbox(Inches(5.5), Inches(3.2), Inches(3.5), Inches(2))
        col2_body.text = "Option B Detailed points"

        prs.save(deck_path)

        result = reading_order_service.analyze_presentation(deck_path, use_ai_fallback=False)
        slide_res = result["slides"][0]

        # Recommended sequence should start with Title, then Col1 items, then Col2 items
        rec_names = [o["text_snippet"] for o in slide_res["recommended_sequence"]]
        assert "Comparison Slide" in rec_names[0]
        # Option A should come before Option B
        idx_a_head = next(i for i, n in enumerate(rec_names) if "Option A Heading" in n)
        idx_a_body = next(i for i, n in enumerate(rec_names) if "Option A Detailed" in n)
        idx_b_head = next(i for i, n in enumerate(rec_names) if "Option B Heading" in n)

        assert idx_a_head < idx_a_body
        assert idx_a_body < idx_b_head


def test_reading_order_mixed_objects_with_table():
    """Verify that a slide with title, text, table, and footer orders table in sequence and footer at end."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        deck_path = os.path.join(tmp_dir, "table_test.pptx")
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        # Title
        t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
        t.text = "Sales Performance"

        # Body text
        b = slide.shapes.add_textbox(Inches(1), Inches(1.8), Inches(8), Inches(1))
        b.text = "Summary of regional revenue:"

        # Table
        tbl_shape = slide.shapes.add_table(2, 2, Inches(1), Inches(3), Inches(6), Inches(2))
        tbl_shape.table.cell(0, 0).text = "Region"
        tbl_shape.table.cell(0, 1).text = "Revenue"
        tbl_shape.table.cell(1, 0).text = "North America"
        tbl_shape.table.cell(1, 1).text = "$10M"

        # Footer at bottom (y = 7.0 inches on standard slide)
        f = slide.shapes.add_textbox(Inches(1), Inches(7.0), Inches(4), Inches(0.5))
        f.text = "Confidential - Page 1"

        prs.save(deck_path)

        result = reading_order_service.analyze_presentation(deck_path, use_ai_fallback=False)
        slide_res = result["slides"][0]

        rec = slide_res["recommended_sequence"]
        assert rec[0]["is_title"] is True
        assert rec[-1]["semantic_role"] == "footer" or "Page 1" in rec[-1]["text_snippet"]


def test_empty_and_single_object_slides():
    """Verify that slides with 0 or 1 object always pass without issues."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        deck_path = os.path.join(tmp_dir, "empty_test.pptx")
        prs = Presentation()
        # Slide 1: completely blank
        prs.slides.add_slide(prs.slide_layouts[6])

        # Slide 2: single textbox
        s2 = prs.slides.add_slide(prs.slide_layouts[6])
        b = s2.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
        b.text = "Lone shape"

        prs.save(deck_path)

        result = reading_order_service.analyze_presentation(deck_path, use_ai_fallback=False)
        assert result["summary"]["total_slides_checked"] == 2
        assert result["summary"]["slides_passed"] == 2
        assert result["summary"]["slides_failed"] == 0
        assert result["summary"]["total_issues"] == 0


def test_reading_order_reorder_image_body_title_heading_correction():
    """
    Test the specification scenario:
    CURRENT PPTX:
    1. Image
    2. Body
    3. Title
    4. Heading
    becomes:
    CORRECTED PPTX:
    1. Title
    2. Heading
    3. Body
    4. Image
    inside the actual PowerPoint file.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_deck = os.path.join(tmp_dir, "input_deck.pptx")
        output_deck = os.path.join(tmp_dir, "output_deck.pptx")

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        # 1. Image in XML
        img = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(4.5), Inches(3), Inches(2))
        img.name = "Picture 1"

        # 2. Body in XML
        body = slide.shapes.add_textbox(Inches(1), Inches(2.5), Inches(8), Inches(1.5))
        body.name = "Content Placeholder 2"
        body.text = "Body paragraph explaining the section in detail."

        # 3. Title in XML
        title = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
        title.name = "Title 1"
        title.text = "Work and Energy"

        # 4. Heading in XML
        heading = slide.shapes.add_textbox(Inches(1), Inches(1.5), Inches(8), Inches(0.8))
        heading.name = "Heading 3"
        heading.text = "Work Done by a Constant Force"

        prs.save(input_deck)

        # Pre-fix analysis: should FAIL due to incorrect sequence
        pre_res = reading_order_service.analyze_presentation(input_deck, use_ai_fallback=False)
        assert pre_res["summary"]["slides_failed"] == 1
        curr_seq_names = [o["name"] for o in pre_res["slides"][0]["current_sequence"]]
        assert curr_seq_names == ["Picture 1", "Content Placeholder 2", "Title 1", "Heading 3"]

        # Run fix_presentation_reading_order
        fix_res = reading_order_service.fix_presentation_reading_order(input_deck, output_deck, use_ai_fallback=False)
        assert fix_res["summary"]["verification_status"] == "SUCCESS"
        assert fix_res["summary"]["fixed"] == 1
        assert fix_res["summary"]["issues_remaining"] == 0

        # Verify saved PPTX internal shape tree order
        fixed_prs = Presentation(output_deck)
        fixed_slide = fixed_prs.slides[0]
        fixed_shape_names = [s.name for s in fixed_slide.shapes]
        assert fixed_shape_names == ["Title 1", "Heading 3", "Content Placeholder 2", "Picture 1"]

        # Re-analyze output PPTX: must be PASS with 0 issues
        post_res = reading_order_service.analyze_presentation(output_deck, use_ai_fallback=False)
        assert post_res["summary"]["slides_passed"] == 1
        assert post_res["summary"]["slides_failed"] == 0
        assert post_res["summary"]["total_issues"] == 0


def test_ooxml_placeholder_type_labels():
    """
    Verify that actual OOXML placeholders and PowerPoint objects are labeled
    with accurate, human-friendly PowerPoint object types (Content Placeholder, Title, Picture, etc.)
    instead of generic names like 'Object 1' or 'Text 1'.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        deck_path = os.path.join(tmp_dir, "ph_labels_test.pptx")
        prs = Presentation()

        # Layout 0: Title and Subtitle
        slide1 = prs.slides.add_slide(prs.slide_layouts[0])
        slide1.shapes.title.text = "Chapter 6 Introduction"
        slide1.placeholders[1].text = "Subtitle and Overview"

        # Layout 1: Title and Content Placeholder
        slide2 = prs.slides.add_slide(prs.slide_layouts[1])
        slide2.shapes.title.text = "Chapter Objectives"
        slide2.placeholders[1].text = "• Objective 1\n• Objective 2\n• Objective 3"

        prs.save(deck_path)

        res = reading_order_service.analyze_presentation(deck_path, use_ai_fallback=False)
        s1_objs = res["slides"][0]["current_sequence"]
        s2_objs = res["slides"][1]["current_sequence"]

        # Slide 1: Title and Subtitle placeholders
        assert s1_objs[0]["object_type"] == "Title"
        assert s1_objs[1]["object_type"] == "Subtitle"

        # Slide 2: Title and Content Placeholder
        assert s2_objs[0]["object_type"] == "Title"
        assert s2_objs[1]["object_type"] == "Content Placeholder"
        assert "Content Placeholder" in s2_objs[1]["object_type"]


def test_before_reorder_50_slide_deck_fix():
    """
    Test real 50-slide presentation (Ch06_GLN_Student_AU) fixing and verification:
    Detect -> Calculate Correct Order -> Reorder XML -> Save -> Re-open/Verify.
    """
    deck_in = "before_reorder_slide4.pptx"
    if not os.path.exists(deck_in):
        pytest.skip(f"{deck_in} not found")

    with tempfile.TemporaryDirectory() as tmp_dir:
        deck_out = os.path.join(tmp_dir, "fixed_ch06.pptx")

        # Fix reading order across all slides
        fix_res = reading_order_service.fix_presentation_reading_order(deck_in, deck_out, use_ai_fallback=False)

        summary = fix_res["summary"]
        assert summary["total_slides"] == 50
        assert summary["fixed"] > 0
        assert summary["verification_status"] == "SUCCESS"
        assert summary["issues_remaining"] == 0

        # Check Slide 2: had Title 1 at pos 2, should now be at pos 1
        reopened_res = reading_order_service.analyze_presentation(deck_out, use_ai_fallback=False)
        s2 = reopened_res["slides"][1]
        assert s2["status"] == "PASS"
        assert s2["current_sequence"][0]["object_type"] == "Title"
        assert s2["current_sequence"][1]["object_type"] == "Content Placeholder"


def test_three_column_layout_order():
    """Verify that a 3-column layout orders column 1, then column 2, then column 3."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        deck_path = os.path.join(tmp_dir, "three_col.pptx")
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        # Title
        t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
        t.text = "Three Column Architecture"

        # Col 1 (left = 0.8 in)
        c1 = slide.shapes.add_textbox(Inches(0.8), Inches(2), Inches(2.2), Inches(3))
        c1.text = "Column 1 Details"

        # Col 2 (left = 3.6 in)
        c2 = slide.shapes.add_textbox(Inches(3.6), Inches(2), Inches(2.2), Inches(3))
        c2.text = "Column 2 Details"

        # Col 3 (left = 6.4 in)
        c3 = slide.shapes.add_textbox(Inches(6.4), Inches(2), Inches(2.2), Inches(3))
        c3.text = "Column 3 Details"

        prs.save(deck_path)
        res = reading_order_service.analyze_presentation(deck_path, use_ai_fallback=False)
        slide_res = res["slides"][0]
        rec = [o["text_snippet"] for o in slide_res["recommended_sequence"]]
        assert "Three Column Architecture" in rec[0]
        assert "Column 1 Details" in rec[1]
        assert "Column 2 Details" in rec[2]
        assert "Column 3 Details" in rec[3]


def test_picture_with_caption_pairing():
    """Verify that a picture and its immediate caption stay paired together."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        deck_path = os.path.join(tmp_dir, "caption_pair.pptx")
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        title = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
        title.text = "Solar Energy Systems"

        # Unrelated text box
        aside = slide.shapes.add_textbox(Inches(5.5), Inches(2), Inches(3.5), Inches(2))
        aside.text = "Side analysis of photovoltaic cells."

        # Picture
        pic = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(2), Inches(3.5), Inches(2.5))
        pic.name = "Picture 1"

        # Caption directly below picture
        cap = slide.shapes.add_textbox(Inches(1), Inches(4.6), Inches(3.5), Inches(0.6))
        cap.name = "Caption 1"
        cap.text = "Figure 1: High efficiency solar panel"

        prs.save(deck_path)
        res = reading_order_service.analyze_presentation(deck_path, use_ai_fallback=False)
        rec = [o["shape_name"] for o in res["slides"][0]["recommended_sequence"]]
        pic_idx = rec.index("Picture 1")
        cap_idx = rec.index("Caption 1")
        # Caption must follow picture directly
        assert cap_idx == pic_idx + 1


def test_chart_and_table_logical_units():
    """Verify that charts and tables are identified and retained as logical units."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        deck_path = os.path.join(tmp_dir, "table_chart.pptx")
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        title = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
        title.text = "Financial Summary"

        # Table
        tbl_shape = slide.shapes.add_table(3, 3, Inches(1), Inches(2), Inches(4), Inches(2))
        tbl_shape.name = "Table 1"

        # Chart placeholder / shape
        chart_shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(5.5), Inches(2), Inches(3.5), Inches(2))
        chart_shape.name = "Chart 1"

        prs.save(deck_path)
        res = reading_order_service.analyze_presentation(deck_path, use_ai_fallback=False)
        types = {o["shape_name"]: o["object_type"] for o in res["slides"][0]["current_sequence"]}
        assert types["Table 1"] == "Table"
        assert types["Chart 1"] == "Chart"


def test_decorative_objects_placed_last():
    """Verify that decorative shapes are placed at the end and excluded from primary reading flow."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        deck_path = os.path.join(tmp_dir, "decorative.pptx")
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        # Decorative shape (top-left background banner)
        dec = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.2), Inches(0.2), Inches(9), Inches(0.2))
        dec.name = "Decorative Banner"

        # Title
        title = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
        title.text = "Slide with Decorative Elements"

        # Content
        body = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(2))
        body.text = "Substantive instructional content."

        prs.save(deck_path)
        res = reading_order_service.analyze_presentation(deck_path, use_ai_fallback=False)
        rec = res["slides"][0]["recommended_sequence"]
        # Title must be first, decorative object must be last
        assert rec[0]["object_type"] == "Title"
        assert rec[1]["object_type"] in ("Text Box", "Content Placeholder")
        assert rec[-1]["shape_name"] == "Decorative Banner"


def test_footer_placed_at_end():
    """Verify footer and slide number objects are placed at the very end of reading sequence."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        deck_path = os.path.join(tmp_dir, "footer.pptx")
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        # Footer added first in XML at top of slide tree
        footer = slide.shapes.add_textbox(Inches(1), Inches(7.0), Inches(4), Inches(0.5))
        footer.name = "Footer Text"
        footer.text = "Confidential - Internal Use Only"

        # Slide Number
        num = slide.shapes.add_textbox(Inches(8.5), Inches(7.0), Inches(1), Inches(0.5))
        num.name = "Slide Number"
        num.text = "42"

        # Title
        title = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
        title.name = "Title 1"
        title.text = "Corporate Presentation"

        prs.save(deck_path)
        res = reading_order_service.analyze_presentation(deck_path, use_ai_fallback=False)
        rec = [o["shape_name"] for o in res["slides"][0]["recommended_sequence"]]
        assert rec[0] == "Title 1"
        # Footers must be at end
        assert rec[-1] in ("Footer Text", "Slide Number")
        assert rec[-2] in ("Footer Text", "Slide Number")


def test_overlapping_objects_z_order_safety():
    """
    Phase 15: Overlapping background card under foreground text.
    Reordering should not blindly reverse visual stacking when background would obscure text.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        deck_in = os.path.join(tmp_dir, "overlap_in.pptx")
        deck_out = os.path.join(tmp_dir, "overlap_out.pptx")
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        # Title
        t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
        t.name = "Title"
        t.text = "Overlapping Card Test"

        # Shape 1: Background card (added first, no text)
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1), Inches(2), Inches(4), Inches(3))
        card.name = "Card Background"

        # Shape 2: Foreground text inside card (added second, on top)
        fg_text = slide.shapes.add_textbox(Inches(1.2), Inches(2.2), Inches(3.6), Inches(2.6))
        fg_text.name = "Card Foreground Text"
        fg_text.text = "Important content inside the card"

        prs.save(deck_in)
        fix_res = reading_order_service.fix_presentation_reading_order(deck_in, deck_out, use_ai_fallback=False)
        # Should complete safely without crashing or corrupting visual stacking
        assert fix_res["summary"]["verification_status"] in ("SUCCESS", "MANUAL_REVIEW")


def test_title_subtitle_content_order():
    """Test 2: Title + Subtitle + Content Placeholder logical reading flow."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        deck_in = os.path.join(tmp_dir, "title_sub_content_in.pptx")
        deck_out = os.path.join(tmp_dir, "title_sub_content_out.pptx")
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        # Add content first (misplaced in XML order)
        content = slide.shapes.add_textbox(Inches(1), Inches(3.5), Inches(8), Inches(2.5))
        content.name = "Content Placeholder 1"
        content.text = "Primary bulleted discussion of the presentation topic."

        # Add subtitle second
        sub = slide.shapes.add_textbox(Inches(1), Inches(1.8), Inches(8), Inches(1))
        sub.name = "Subtitle 1"
        sub.text = "Comprehensive Research Findings"

        # Add title third (pos 3 in XML)
        title = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
        title.name = "Title 1"
        title.text = "Global Accessibility Initiative"

        prs.save(deck_in)
        fix_res = reading_order_service.fix_presentation_reading_order(deck_in, deck_out, use_ai_fallback=False)
        assert fix_res["summary"]["verification_status"] == "SUCCESS"

        reopened = reading_order_service.analyze_presentation(deck_out, use_ai_fallback=False)
        s1 = reopened["slides"][0]
        assert s1["status"] == "PASS"
        seq = s1["current_sequence"]
        assert seq[0]["object_type"] == "Title"
        assert seq[1]["object_type"] == "Subtitle"
        assert seq[2]["object_type"] in ("Content Placeholder", "Text Box")


def test_text_plus_picture_flow():
    """Test 6: Explanatory text on left followed by supporting picture on right."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        deck_in = os.path.join(tmp_dir, "text_pic_in.pptx")
        deck_out = os.path.join(tmp_dir, "text_pic_out.pptx")
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        # Title
        t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
        t.name = "Title"
        t.text = "Microscopic Cell Structure"

        # Picture added first in body XML
        pic = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(5.5), Inches(2), Inches(3.8), Inches(3))
        pic.name = "Picture 1"

        # Text added second in body XML (left side)
        txt = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(4), Inches(3))
        txt.name = "Text 1"
        txt.text = "Cell membrane provides protection and facilitates nutrient transport."

        prs.save(deck_in)
        fix_res = reading_order_service.fix_presentation_reading_order(deck_in, deck_out, use_ai_fallback=False)
        assert fix_res["summary"]["verification_status"] == "SUCCESS"

        reopened = reading_order_service.analyze_presentation(deck_out, use_ai_fallback=False)
        seq = reopened["slides"][0]["current_sequence"]
        assert seq[0]["object_type"] == "Title"
        text_pos = next(i for i, o in enumerate(seq) if o["shape_name"] == "Text 1")
        pic_pos = next(i for i, o in enumerate(seq) if o["shape_name"] == "Picture 1")
        assert text_pos < pic_pos


def test_smartart_diagram_classification_and_order():
    """Test 9: SmartArt diagram classification and logical reading order."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        deck_in = os.path.join(tmp_dir, "smartart_in.pptx")
        deck_out = os.path.join(tmp_dir, "smartart_out.pptx")
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
        t.name = "Title"
        t.text = "Organizational Workflow"

        # SmartArt shape (named diagram / smartart)
        dgm = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(2), Inches(8), Inches(3))
        dgm.name = "SmartArt Diagram 1"

        cap = slide.shapes.add_textbox(Inches(1), Inches(5.2), Inches(8), Inches(0.6))
        cap.name = "Caption 1"
        cap.text = "Figure: Iterative design life cycle"

        prs.save(deck_in)
        res = reading_order_service.analyze_presentation(deck_in, use_ai_fallback=False)
        objs = {o["shape_name"]: o for o in res["slides"][0]["current_sequence"]}
        assert objs["SmartArt Diagram 1"]["object_type"] == "SmartArt"

        fix_res = reading_order_service.fix_presentation_reading_order(deck_in, deck_out, use_ai_fallback=False)
        assert fix_res["summary"]["verification_status"] == "SUCCESS"
        reopened = reading_order_service.analyze_presentation(deck_out, use_ai_fallback=False)
        seq = reopened["slides"][0]["current_sequence"]
        assert seq[0]["object_type"] == "Title"
        assert seq[1]["object_type"] == "SmartArt"


def test_grouped_diagram_preservation():
    """Test 10: Grouped diagram shapes are preserved and treated as logical reading unit."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        deck_in = os.path.join(tmp_dir, "group_in.pptx")
        deck_out = os.path.join(tmp_dir, "group_out.pptx")
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        # Out of order: group first, title second
        grp = slide.shapes.add_group_shape()
        grp.name = "Group 1"
        c1 = grp.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(2), Inches(2), Inches(1))
        c1.text = "Input Step"
        c2 = grp.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(3.2), Inches(2.2), Inches(1), Inches(0.6))
        c3 = grp.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(4.5), Inches(2), Inches(2), Inches(1))
        c3.text = "Output Result"

        t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
        t.name = "Title"
        t.text = "System Data Flow"

        prs.save(deck_in)
        fix_res = reading_order_service.fix_presentation_reading_order(deck_in, deck_out, use_ai_fallback=False)
        assert fix_res["summary"]["verification_status"] == "SUCCESS"

        reopened = reading_order_service.analyze_presentation(deck_out, use_ai_fallback=False)
        seq = reopened["slides"][0]["current_sequence"]
        assert seq[0]["object_type"] == "Title"
        assert seq[1]["object_type"] == "Group"


def test_multiple_text_boxes_row_and_column_flow():
    """Test 14: Multiple text boxes structured as a 2x2 grid with step sequences."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        deck_in = os.path.join(tmp_dir, "grid_in.pptx")
        deck_out = os.path.join(tmp_dir, "grid_out.pptx")
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(0.8))
        t.name = "Title"
        t.text = "Implementation Milestones"

        # Step 1: top-left
        b1 = slide.shapes.add_textbox(Inches(1), Inches(1.8), Inches(3.8), Inches(1.5))
        b1.name = "Step 1 Box"
        b1.text = "Step 1: Requirements gathering and stakeholder review."

        # Step 2: top-right
        b2 = slide.shapes.add_textbox(Inches(5.2), Inches(1.8), Inches(3.8), Inches(1.5))
        b2.name = "Step 2 Box"
        b2.text = "Step 2: Architecture specification and wireframing."

        # Step 3: bottom-left
        b3 = slide.shapes.add_textbox(Inches(1), Inches(4.8), Inches(3.8), Inches(1.5))
        b3.name = "Step 3 Box"
        b3.text = "Step 3: Component implementation and test coverage."

        # Step 4: bottom-right
        b4 = slide.shapes.add_textbox(Inches(5.2), Inches(4.8), Inches(3.8), Inches(1.5))
        b4.name = "Step 4 Box"
        b4.text = "Step 4: Production release and verification."

        prs.save(deck_in)
        fix_res = reading_order_service.fix_presentation_reading_order(deck_in, deck_out, use_ai_fallback=False)
        assert fix_res["summary"]["verification_status"] == "SUCCESS"

        reopened = reading_order_service.analyze_presentation(deck_out, use_ai_fallback=False)
        seq = [o["shape_name"] for o in reopened["slides"][0]["current_sequence"]]
        assert seq[0] == "Title"
        assert seq.index("Step 1 Box") < seq.index("Step 2 Box")
        assert seq.index("Step 2 Box") < seq.index("Step 3 Box")
        assert seq.index("Step 3 Box") < seq.index("Step 4 Box")


def test_complex_academic_slide_ordering():
    """Test 15: Academic layout: Title -> Full-width Abstract -> 2-Column Methodology / Results -> Footer."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        deck_in = os.path.join(tmp_dir, "academic_in.pptx")
        deck_out = os.path.join(tmp_dir, "academic_out.pptx")
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        # Footer added first
        ftr = slide.shapes.add_textbox(Inches(1), Inches(7.0), Inches(5), Inches(0.4))
        ftr.name = "Footer"
        ftr.text = "Journal of Artificial Intelligence Research 2026"

        # Title
        t = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(8.4), Inches(0.8))
        t.name = "Title"
        t.text = "Neural Reading Order Optimization in Complex Documents"

        # Full-width Abstract banner
        abstract = slide.shapes.add_textbox(Inches(0.8), Inches(1.4), Inches(8.4), Inches(1.2))
        abstract.name = "Abstract"
        abstract.text = "Abstract: We propose a hybrid structural layout reading order algorithm."

        # Left Column
        c1_head = slide.shapes.add_textbox(Inches(0.8), Inches(3.0), Inches(4.0), Inches(0.6))
        c1_head.name = "Method Heading"
        c1_head.text = "Methodology"

        c1_body = slide.shapes.add_textbox(Inches(0.8), Inches(3.8), Inches(4.0), Inches(2.5))
        c1_body.name = "Method Body"
        c1_body.text = "Topological layout sorting with semantic prioritization."

        # Right Column
        c2_head = slide.shapes.add_textbox(Inches(5.2), Inches(3.0), Inches(4.0), Inches(0.6))
        c2_head.name = "Results Heading"
        c2_head.text = "Experimental Results"

        c2_body = slide.shapes.add_textbox(Inches(5.2), Inches(3.8), Inches(4.0), Inches(2.5))
        c2_body.name = "Results Body"
        c2_body.text = "100% compliance rate achieved on standard benchmark suite."

        prs.save(deck_in)
        fix_res = reading_order_service.fix_presentation_reading_order(deck_in, deck_out, use_ai_fallback=False)
        assert fix_res["summary"]["verification_status"] == "SUCCESS"

        reopened = reading_order_service.analyze_presentation(deck_out, use_ai_fallback=False)
        seq = [o["shape_name"] for o in reopened["slides"][0]["current_sequence"]]
        assert seq[0] == "Title"
        assert seq[1] == "Abstract"
        assert seq[2] == "Method Heading"
        assert seq[3] == "Method Body"
        assert seq[4] == "Results Heading"
        assert seq[5] == "Results Body"
        assert seq[-1] == "Footer"


def test_reading_order_semantics_title_body_picture():
    """
    STEP 0 UNIT TEST:
    Proves that a slide with XML document order [Title, Body, Picture]
    is reported as read order Title -> Body -> Picture (positions 1 -> 2 -> 3).
    Verifies that:
    - Reading order = document order of children inside <p:cSld>/<p:spTree>.
    - FIRST element in spTree = read FIRST by screen readers.
    - Z-order is the same order: first element = back-most, last = front-most.
    - Internal data structures use: reading_index 0 = first read = first in XML.
    """
    import io
    from tests.benchmark.generate_benchmark_decks import TINY_PNG_BYTES
    with tempfile.TemporaryDirectory() as tmp_dir:
        deck_path = os.path.join(tmp_dir, "step0_semantics.pptx")
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        # 1. Add Title first (XML child 0)
        t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
        t.name = "Slide Title"
        t.text = "Quarterly Business Update"

        # 2. Add Body second (XML child 1)
        b = slide.shapes.add_textbox(Inches(1), Inches(2.0), Inches(8), Inches(2.5))
        b.name = "Slide Body"
        b.text = "Body text describing financial performance and milestones."

        # 3. Add Picture third (XML child 2)
        pic = slide.shapes.add_picture(io.BytesIO(TINY_PNG_BYTES), Inches(1), Inches(4.8), Inches(4), Inches(2))
        pic.name = "Performance Chart Photo"

        prs.save(deck_path)

        res = reading_order_service.analyze_presentation(deck_path, use_ai_fallback=False)
        slide_res = res["slides"][0]

        assert slide_res["status"] == "PASS"
        assert len(slide_res["issues"]) == 0

        # Document order in XML
        curr_seq = slide_res["current_sequence"]
        assert len(curr_seq) == 3
        assert curr_seq[0]["shape_name"] == "Slide Title"
        assert curr_seq[0]["current_position"] == 1
        assert curr_seq[1]["shape_name"] == "Slide Body"
        assert curr_seq[1]["current_position"] == 2
        assert curr_seq[2]["shape_name"] == "Performance Chart Photo"
        assert curr_seq[2]["current_position"] == 3

        # Recommended sequence matches XML document order exactly
        rec_seq = slide_res["recommended_sequence"]
        assert rec_seq[0]["shape_name"] == "Slide Title"
        assert rec_seq[1]["shape_name"] == "Slide Body"
        assert rec_seq[2]["shape_name"] == "Performance Chart Photo"





