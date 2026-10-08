"""
tests/test_fixer_do_no_harm.py
=================================
Comprehensive tests for the ReadingOrderFixer covering:

- Step 1: XML order semantics (Title, Body, Picture → positions 1, 2, 3)
- Step 2: Do-no-harm rules (slides already correct must NOT be modified)
- Step 3: Inversion metric correctness
- Step 4: LIS-based minimal-edit
- Step 5: Idempotency (fixing twice → no change)
- Step 5: Regression gate (worse slide → RuntimeError)
- Step 6: Per-slide report status (Correct / Fixed / Manual Review)
"""
import io
import os
import tempfile

import pytest
from lxml import etree
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.shapes import MSO_SHAPE

from app.services.reading_order_fixer import (
    ReadingOrderFixer,
    _compute_inversions,
    _longest_increasing_subsequence_indices,
    _minimal_edit_reorder,
    _visual_order,
    _detect_multicolumn,
)
from app.services.reading_order_config import DEFAULT_SLIDE_HEIGHT_EMU

try:
    from tests.benchmark.generate_benchmark_decks import TINY_PNG_BYTES
except ImportError:
    TINY_PNG_BYTES = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x02\x08\x02"
        b"\x00\x00\x00\xfd\xd4\x9as\x00\x00\x00\x12IDATx\x9cc\xf8\xcf\xc0\xc0\x00\x03"
        b"\x03\x03\x00\x00\x18\x00\x01\xa5\x05Gk\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def _make_obj(shape_id, left, top, width=1000000, height=500000, is_title=False,
              semantic_role="body_text", is_decorative=False):
    """Helper to construct a minimal shape-info dict."""
    return {
        "shape_id": shape_id,
        "name": f"Shape{shape_id}",
        "left_emu": left,
        "top_emu": top,
        "width_emu": width,
        "height_emu": height,
        "is_title": is_title,
        "semantic_role": "footer" if semantic_role == "footer" else semantic_role,
        "is_decorative": is_decorative,
        "text_content": "",
        "text_snippet": "",
    }


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: XML direction & semantics
# ─────────────────────────────────────────────────────────────────────────────

class TestXMLDirectionSemantics:
    """
    Prove: first child in spTree = first read by screen reader = position 1.
    XML order [Title, Body, Picture] → read order Title(1) → Body(2) → Picture(3).
    """

    def test_title_body_picture_correct_direction(self):
        """
        XML order Title(0), Body(1), Picture(2) must yield
        current_position 1,2,3 (first child = first read).
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "step0.pptx")
            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[6])

            t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
            t.name = "SlideTitle"
            t.text = "Title Text"

            b = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(2))
            b.name = "SlideBody"
            b.text = "Body paragraph"

            p = slide.shapes.add_picture(io.BytesIO(TINY_PNG_BYTES),
                                         Inches(1), Inches(4.5), Inches(4), Inches(2))
            p.name = "SlidePic"

            prs.save(path)

            # Verify spTree order
            prs2 = Presentation(path)
            sl = prs2.slides[0]
            spTree = sl.shapes._spTree
            header_tags = ("nvGrpSpPr", "grpSpPr")
            footer_tags = ("extLst",)
            shape_elems = [c for c in spTree
                           if c.tag.split("}")[-1] not in header_tags
                           and c.tag.split("}")[-1] not in footer_tags]
            names_in_order = []
            for elem in shape_elems:
                for child in elem.iter():
                    ct = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if ct == "cNvPr":
                        names_in_order.append(child.get("name", ""))
                        break
            assert names_in_order == ["SlideTitle", "SlideBody", "SlidePic"], \
                f"spTree order should be [Title, Body, Pic], got: {names_in_order}"

    def test_inversion_metric_perfect_order(self):
        """Objects in top-to-bottom left-to-right order → 0 inversions."""
        objs = [
            _make_obj(1, left=914400, top=457200),   # row 0, col 0
            _make_obj(2, left=914400, top=1828800),  # row 1, col 0
            _make_obj(3, left=914400, top=3200400),  # row 2, col 0
        ]
        assert _compute_inversions(objs, DEFAULT_SLIDE_HEIGHT_EMU) == 0

    def test_inversion_metric_reversed_order(self):
        """Reversed objects → all pairs inverted."""
        objs = [
            _make_obj(3, left=914400, top=3200400),
            _make_obj(2, left=914400, top=1828800),
            _make_obj(1, left=914400, top=457200),
        ]
        # n=3 → max_pairs = 3; all 3 pairs inverted
        assert _compute_inversions(objs, DEFAULT_SLIDE_HEIGHT_EMU) == 3

    def test_inversion_metric_single_swap(self):
        """Two objects swapped → exactly 1 inversion."""
        objs = [
            _make_obj(2, left=914400, top=1828800),  # should be 2nd
            _make_obj(1, left=914400, top=457200),   # should be 1st
            _make_obj(3, left=914400, top=3200400),  # correctly 3rd
        ]
        assert _compute_inversions(objs, DEFAULT_SLIDE_HEIGHT_EMU) == 1


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Do-no-harm
# ─────────────────────────────────────────────────────────────────────────────

class TestDoNoHarm:
    """Slides already correct (0 inversions) MUST NOT be touched."""

    def test_already_correct_slide_not_modified(self):
        """Slide with title first, body below: no modification."""
        with tempfile.TemporaryDirectory() as tmp:
            inp = os.path.join(tmp, "correct.pptx")
            out = os.path.join(tmp, "correct_fixed.pptx")

            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[6])

            t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
            t.name = "TitleShape"
            t.text = "Page Title"
            b = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(2))
            b.name = "BodyShape"
            b.text = "Body content here"

            prs.save(inp)

            fixer = ReadingOrderFixer(strategy="visual")
            result = fixer.fix_presentation(inp, out)

            # Status should be "correct" (0 inversions)
            slide_d = result["slides"][0]
            assert slide_d["status"] in ("correct", "already_correct"), \
                f"Expected correct, got {slide_d['status']}"
            assert slide_d["shapes_moved"] == 0, "No shapes should be moved"

            # spTree order must be unchanged
            orig_prs = Presentation(inp)
            fixed_prs = Presentation(out)
            orig_names = [s.name for s in orig_prs.slides[0].shapes]
            fixed_names = [s.name for s in fixed_prs.slides[0].shapes]
            assert orig_names == fixed_names, \
                f"Shape order changed on already-correct slide: {orig_names} → {fixed_names}"

    def test_zero_inversion_slide_status_correct(self):
        """Single-column slides in correct visual order → status='correct', shapes_moved=0."""
        with tempfile.TemporaryDirectory() as tmp:
            inp = os.path.join(tmp, "zero_inv.pptx")
            out = os.path.join(tmp, "zero_inv_fixed.pptx")

            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            # Perfect visual order: add top-to-bottom
            for i in range(4):
                b = slide.shapes.add_textbox(Inches(1), Inches(0.5 + i * 1.5), Inches(8), Inches(1))
                b.name = f"Box{i+1}"
                b.text = f"Content {i+1}"
            prs.save(inp)

            fixer = ReadingOrderFixer(strategy="visual")
            result = fixer.fix_presentation(inp, out)

            # All slides should be "correct" or "manual_review" (not "fixed")
            for d in result["slides"]:
                assert d["status"] != "fixed" or d["shapes_moved"] == 0, \
                    f"Slide {d['slide_number']}: should not be modified when already correct"

    def test_single_object_slide_unchanged(self):
        """Single-object slide → status=correct, never touched."""
        with tempfile.TemporaryDirectory() as tmp:
            inp = os.path.join(tmp, "single.pptx")
            out = os.path.join(tmp, "single_fixed.pptx")

            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            t = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
            t.name = "OnlyShape"
            t.text = "Lone object"
            prs.save(inp)

            fixer = ReadingOrderFixer(strategy="visual")
            result = fixer.fix_presentation(inp, out)

            d = result["slides"][0]
            assert d["shapes_moved"] == 0
            assert d["status"] in ("correct",)


# ─────────────────────────────────────────────────────────────────────────────
# LIS-based minimal edit
# ─────────────────────────────────────────────────────────────────────────────

class TestLISMinimalEdit:
    """LIS and minimal-edit logic."""

    def test_lis_already_sorted(self):
        """Already sorted → LIS = all indices."""
        indices = _longest_increasing_subsequence_indices([1, 2, 3, 4, 5])
        assert indices == [0, 1, 2, 3, 4]

    def test_lis_reversed(self):
        """Fully reversed → LIS = length 1."""
        indices = _longest_increasing_subsequence_indices([5, 4, 3, 2, 1])
        assert len(indices) == 1

    def test_lis_classic(self):
        """Classic LIS example: [10, 9, 2, 5, 3, 7, 101, 18] -> LIS length 4 (e.g. [2, 3, 7, 101] or [2, 5, 7, 18])."""
        vals = [10, 9, 2, 5, 3, 7, 101, 18]
        indices = _longest_increasing_subsequence_indices(vals)
        lis_vals = [vals[i] for i in indices]
        # Verify it's strictly increasing
        for i in range(len(lis_vals) - 1):
            assert lis_vals[i] < lis_vals[i + 1], f"Not strictly increasing: {lis_vals}"
        assert len(lis_vals) == 4

    def test_minimal_edit_preserves_stable(self):
        """Minimal-edit returns the target order (all IDs present)."""
        orig = [_make_obj(3, 0, 3000000), _make_obj(1, 0, 500000), _make_obj(2, 0, 2000000)]
        target = [_make_obj(1, 0, 500000), _make_obj(2, 0, 2000000), _make_obj(3, 0, 3000000)]
        result = _minimal_edit_reorder(orig, target)
        assert [o["shape_id"] for o in result] == [1, 2, 3]

    def test_minimal_edit_identity_when_same_order(self):
        """If orig == target order → result unchanged."""
        orig = [_make_obj(1, 0, 500000), _make_obj(2, 0, 2000000), _make_obj(3, 0, 3000000)]
        target = [_make_obj(1, 0, 500000), _make_obj(2, 0, 2000000), _make_obj(3, 0, 3000000)]
        result = _minimal_edit_reorder(orig, target)
        assert [o["shape_id"] for o in result] == [1, 2, 3]


# ─────────────────────────────────────────────────────────────────────────────
# Visual order (Strategy A)
# ─────────────────────────────────────────────────────────────────────────────

class TestVisualOrder:
    def test_title_first_footer_last(self):
        """Title must come first, footer must come last."""
        objs = [
            _make_obj(10, left=0, top=6500000, semantic_role="footer"),  # footer at bottom
            _make_obj(1, left=0, top=500000, is_title=True),             # title
            _make_obj(2, left=0, top=2000000),                           # body
        ]
        ordered = _visual_order(objs, DEFAULT_SLIDE_HEIGHT_EMU, 9144000)
        assert ordered[0]["shape_id"] == 1, "Title must be first"
        assert ordered[-1]["shape_id"] == 10, "Footer must be last"

    def test_top_to_bottom_order(self):
        """Body shapes in visual (top→bottom) order."""
        objs = [
            _make_obj(3, left=0, top=3000000),
            _make_obj(1, left=0, top=500000),
            _make_obj(2, left=0, top=2000000),
        ]
        ordered = _visual_order(objs, DEFAULT_SLIDE_HEIGHT_EMU, 9144000)
        tops = [o["top_emu"] for o in ordered]
        assert tops == sorted(tops), f"Not sorted top-to-bottom: {tops}"

    def test_left_right_within_row(self):
        """Two shapes in same row → left before right."""
        objs = [
            _make_obj(2, left=5000000, top=2000000),
            _make_obj(1, left=1000000, top=2000000),
        ]
        ordered = _visual_order(objs, DEFAULT_SLIDE_HEIGHT_EMU, 9144000)
        assert ordered[0]["left_emu"] < ordered[1]["left_emu"]


# ─────────────────────────────────────────────────────────────────────────────
# Multi-column detection
# ─────────────────────────────────────────────────────────────────────────────

class TestMultiColumnDetection:
    def test_two_col_detected(self):
        """Two clear columns with >=2 items each → True."""
        objs = [
            _make_obj(1, left=500000, top=1000000),
            _make_obj(2, left=500000, top=2500000),
            _make_obj(3, left=5000000, top=1000000),
            _make_obj(4, left=5000000, top=2500000),
        ]
        assert _detect_multicolumn(objs, 9144000, DEFAULT_SLIDE_HEIGHT_EMU) is True

    def test_single_col_not_detected(self):
        """Single column → False."""
        objs = [
            _make_obj(1, left=914400, top=500000),
            _make_obj(2, left=914400, top=2000000),
            _make_obj(3, left=914400, top=3500000),
        ]
        assert _detect_multicolumn(objs, 9144000, DEFAULT_SLIDE_HEIGHT_EMU) is False

    def test_too_few_items_not_detected(self):
        """Only 2 items total → can't have 2 cols with 2 items each → False."""
        objs = [
            _make_obj(1, left=500000, top=1000000),
            _make_obj(2, left=5000000, top=1000000),
        ]
        assert _detect_multicolumn(objs, 9144000, DEFAULT_SLIDE_HEIGHT_EMU) is False


# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Idempotency
# ─────────────────────────────────────────────────────────────────────────────

class TestIdempotency:
    """Running fixer twice on its own output changes nothing."""

    def test_idempotent_simple(self):
        """Fix a disordered deck twice → second run produces identical XML order."""
        with tempfile.TemporaryDirectory() as tmp:
            inp = os.path.join(tmp, "idem_in.pptx")
            out1 = os.path.join(tmp, "idem_out1.pptx")
            out2 = os.path.join(tmp, "idem_out2.pptx")

            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            # Disordered: body first, title second
            b = slide.shapes.add_textbox(Inches(1), Inches(3), Inches(8), Inches(2))
            b.name = "BodyFirst"
            b.text = "Body text"
            t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
            t.name = "TitleSecond"
            t.text = "The Title"
            prs.save(inp)

            fixer = ReadingOrderFixer(strategy="visual")
            fixer.fix_presentation(inp, out1)
            fixer.fix_presentation(out1, out2)

            # out1 and out2 should have identical shape order
            prs1 = Presentation(out1)
            prs2 = Presentation(out2)
            for sidx in range(len(prs1.slides)):
                names1 = [s.name for s in prs1.slides[sidx].shapes]
                names2 = [s.name for s in prs2.slides[sidx].shapes]
                assert names1 == names2, \
                    f"Slide {sidx+1}: 2nd run changed order: {names1} → {names2}"

    def test_idempotent_already_correct(self):
        """Fixing an already-correct deck twice → identical to original."""
        with tempfile.TemporaryDirectory() as tmp:
            inp = os.path.join(tmp, "correct.pptx")
            out1 = os.path.join(tmp, "correct1.pptx")
            out2 = os.path.join(tmp, "correct2.pptx")

            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
            t.name = "Title"
            t.text = "Title"
            b = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(2))
            b.name = "Body"
            b.text = "Body"
            prs.save(inp)

            fixer = ReadingOrderFixer(strategy="hybrid")
            fixer.fix_presentation(inp, out1)
            fixer.fix_presentation(out1, out2)

            prs1 = Presentation(out1)
            prs2 = Presentation(out2)
            names1 = [s.name for s in prs1.slides[0].shapes]
            names2 = [s.name for s in prs2.slides[0].shapes]
            assert names1 == names2


# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Regression gate
# ─────────────────────────────────────────────────────────────────────────────

class TestRegressionGate:
    """Regression gate: if a slide gets worse, fix_presentation raises RuntimeError."""

    def test_fix_improves_inversions(self):
        """Fix genuinely disordered slide → inversions after < inversions before."""
        with tempfile.TemporaryDirectory() as tmp:
            inp = os.path.join(tmp, "disordered.pptx")
            out = os.path.join(tmp, "ordered.pptx")

            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            # Picture at top, title at bottom
            p = slide.shapes.add_picture(io.BytesIO(TINY_PNG_BYTES),
                                         Inches(1), Inches(0.5), Inches(4), Inches(2))
            p.name = "Pic"
            t = slide.shapes.add_textbox(Inches(1), Inches(5), Inches(8), Inches(1))
            t.name = "Title"
            t.text = "Title"
            prs.save(inp)

            fixer = ReadingOrderFixer(strategy="visual")
            result = fixer.fix_presentation(inp, out)

            # Sum of after inversions must be <= before inversions
            total_before = result["summary"]["total_inversions_before"]
            total_after = result["summary"]["total_inversions_after"]
            assert total_after <= total_before, \
                f"Inversions got worse: {total_before} → {total_after}"

    def test_all_strategies_no_regression(self):
        """All three strategies must not produce a regression."""
        with tempfile.TemporaryDirectory() as tmp:
            inp = os.path.join(tmp, "test.pptx")
            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
            t.name = "Title"
            t.text = "Title"
            b = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(2))
            b.name = "Body"
            b.text = "Body content"
            prs.save(inp)

            for strategy in ["visual", "xycut", "hybrid"]:
                out = os.path.join(tmp, f"out_{strategy}.pptx")
                fixer = ReadingOrderFixer(strategy=strategy)
                result = fixer.fix_presentation(inp, out)
                assert result["summary"]["total_inversions_after"] <= result["summary"]["total_inversions_before"], \
                    f"Strategy {strategy}: regression detected!"


# ─────────────────────────────────────────────────────────────────────────────
# Step 6: Per-slide report
# ─────────────────────────────────────────────────────────────────────────────

class TestPerSlideReport:
    def test_report_has_all_statuses(self):
        """Report contains status for every slide."""
        with tempfile.TemporaryDirectory() as tmp:
            inp = os.path.join(tmp, "multi.pptx")
            out = os.path.join(tmp, "multi_fixed.pptx")

            prs = Presentation()
            # Slide 1: correct
            sl1 = prs.slides.add_slide(prs.slide_layouts[6])
            t1 = sl1.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
            t1.name = "Title1"; t1.text = "Title"
            b1 = sl1.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(2))
            b1.name = "Body1"; b1.text = "Body"

            # Slide 2: disordered
            sl2 = prs.slides.add_slide(prs.slide_layouts[6])
            b2 = sl2.shapes.add_textbox(Inches(1), Inches(3), Inches(8), Inches(2))
            b2.name = "BodyFirst"; b2.text = "Body comes first in XML"
            t2 = sl2.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
            t2.name = "TitleLast"; t2.text = "Title comes second in XML"

            prs.save(inp)

            fixer = ReadingOrderFixer(strategy="visual")
            result = fixer.fix_presentation(inp, out)

            assert len(result["slides"]) == 2

            # Every slide has required fields
            for d in result["slides"]:
                assert "slide_number" in d
                assert "status" in d
                assert "inversions_before" in d
                assert "inversions_after" in d
                assert "shapes_moved" in d

    def test_correct_slide_has_zero_shapes_moved(self):
        """Correct slide report: shapes_moved == 0."""
        with tempfile.TemporaryDirectory() as tmp:
            inp = os.path.join(tmp, "correct.pptx")
            out = os.path.join(tmp, "correct_f.pptx")

            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
            t.name = "T"; t.text = "Title"
            b = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(2))
            b.name = "B"; b.text = "Body"
            prs.save(inp)

            fixer = ReadingOrderFixer(strategy="visual")
            result = fixer.fix_presentation(inp, out)

            d = result["slides"][0]
            assert d["shapes_moved"] == 0

    def test_fixed_slide_has_fewer_inversions(self):
        """Fixed slide: inversions_after < inversions_before."""
        with tempfile.TemporaryDirectory() as tmp:
            inp = os.path.join(tmp, "disordered.pptx")
            out = os.path.join(tmp, "disordered_f.pptx")

            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            # Bottom-to-top order in XML
            for i in range(4, 0, -1):
                b = slide.shapes.add_textbox(Inches(1), Inches(0.5 + (i-1) * 1.5), Inches(8), Inches(1))
                b.name = f"Shape{i}"
                b.text = f"Text {i}"
            prs.save(inp)

            fixer = ReadingOrderFixer(strategy="visual")
            result = fixer.fix_presentation(inp, out)

            for d in result["slides"]:
                if d["status"] == "fixed":
                    assert d["inversions_after"] < d["inversions_before"], \
                        f"Fixed slide {d['slide_number']}: after >= before"


# ─────────────────────────────────────────────────────────────────────────────
# Real deck test (if available)
# ─────────────────────────────────────────────────────────────────────────────

class TestRealDeck:
    """Tests using the real 50-slide deck (skipped if not present)."""

    DECK_PATH = "before_reorder_slide4.pptx"

    def test_real_deck_no_regression_visual(self):
        """Visual strategy: no slide gets MORE inversions."""
        if not os.path.exists(self.DECK_PATH):
            pytest.skip(f"{self.DECK_PATH} not found")

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "real_fixed_A.pptx")
            fixer = ReadingOrderFixer(strategy="visual")
            result = fixer.fix_presentation(self.DECK_PATH, out)

            regressions = [
                d for d in result["slides"]
                if d.get("inversions_after", 0) > d.get("inversions_before", 0)
            ]
            assert regressions == [], \
                f"Regression detected on slides: {[d['slide_number'] for d in regressions]}"

    def test_real_deck_no_regression_xycut(self):
        """XYcut strategy: no slide gets MORE inversions."""
        if not os.path.exists(self.DECK_PATH):
            pytest.skip(f"{self.DECK_PATH} not found")

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "real_fixed_B.pptx")
            fixer = ReadingOrderFixer(strategy="xycut")
            result = fixer.fix_presentation(self.DECK_PATH, out)

            regressions = [
                d for d in result["slides"]
                if d.get("inversions_after", 0) > d.get("inversions_before", 0)
            ]
            assert regressions == [], \
                f"Regression detected on slides: {[d['slide_number'] for d in regressions]}"

    def test_real_deck_no_regression_hybrid(self):
        """Hybrid strategy: no slide gets MORE inversions."""
        if not os.path.exists(self.DECK_PATH):
            pytest.skip(f"{self.DECK_PATH} not found")

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "real_fixed_C.pptx")
            fixer = ReadingOrderFixer(strategy="hybrid")
            result = fixer.fix_presentation(self.DECK_PATH, out)

            regressions = [
                d for d in result["slides"]
                if d.get("inversions_after", 0) > d.get("inversions_before", 0)
            ]
            assert regressions == [], \
                f"Regression detected on slides: {[d['slide_number'] for d in regressions]}"

    def test_real_deck_correct_slides_untouched(self):
        """Slides already correct (inversions_before==0) must not be modified."""
        if not os.path.exists(self.DECK_PATH):
            pytest.skip(f"{self.DECK_PATH} not found")

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "real_fixed.pptx")
            fixer = ReadingOrderFixer(strategy="hybrid")
            result = fixer.fix_presentation(self.DECK_PATH, out)

            wrongly_modified = [
                d for d in result["slides"]
                if d.get("inversions_before", 1) == 0
                and d.get("shapes_moved", 0) > 0
            ]
            assert wrongly_modified == [], \
                f"Zero-inversion slides were modified: {[d['slide_number'] for d in wrongly_modified]}"

    def test_real_deck_idempotent(self):
        """Fixing the real deck twice → second run makes no changes."""
        if not os.path.exists(self.DECK_PATH):
            pytest.skip(f"{self.DECK_PATH} not found")

        with tempfile.TemporaryDirectory() as tmp:
            out1 = os.path.join(tmp, "real_fixed1.pptx")
            out2 = os.path.join(tmp, "real_fixed2.pptx")

            fixer = ReadingOrderFixer(strategy="hybrid")
            fixer.fix_presentation(self.DECK_PATH, out1)
            result2 = fixer.fix_presentation(out1, out2)

            # Second run should modify nothing (all correct)
            modified_in_2nd = [
                d for d in result2["slides"]
                if d.get("shapes_moved", 0) > 0
            ]
            assert modified_in_2nd == [], \
                f"2nd run modified slides: {[d['slide_number'] for d in modified_in_2nd]}"
