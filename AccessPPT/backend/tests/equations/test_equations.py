import hashlib

import pytest
from pptx import Presentation

from app.services.equations.conversion_validator import inspect_ole
from app.services.equations.mathtype_adapter import (
    AdapterStatus,
    MathTypeAdapter,
    MathTypeObject,
    MathTypeUnavailableError,
    UnavailableAdapter,
    WindowsWorkerAdapter,
)
from app.services.equations.pipeline import convert_file, scan_file
from tests.equations.fixtures import PNG_1PX, build_test_deck, fake_mathtype_ole


class FakeMathTypeAdapter(MathTypeAdapter):
    """Stands in for a MathType worker; returns an OLE compound file with an Equation Native stream."""

    name = "fake"

    def __init__(self, ole: bytes | None = None):
        self.ole = ole if ole is not None else fake_mathtype_ole()
        self.requests = []

    def status(self):
        return AdapterStatus(self.name, True, mathtype_version="test", conversion_method="fake")

    def convert(self, request):
        self.requests.append(request)
        return MathTypeObject("Equation.DSMT4", self.ole, PNG_1PX, "image/png", 914400, 457200)


def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


@pytest.fixture
def deck(tmp_path):
    path = str(tmp_path / "deck.pptx")
    build_test_deck(path)
    return path


def _items(inv):
    return [e for s in inv["slides"] for e in s["equations"]]


def test_scan_classifies_every_category(deck):
    inv = scan_file(deck)
    by = {}
    for e in _items(inv):
        by.setdefault((e["slide_number"], e["category"], e["placement"]), []).append(e)

    assert inv["by_category"] == {"omml": 9, "mathtype_ole": 1, "math_text": 1, "image": 1}
    eligible = [e for e in _items(inv) if e["eligibility"] == "eligible"]
    # slide 1: 3 boxes; slide 2: matrix + eqArr; slide 3: grouped box
    assert len(eligible) == 6
    assert len({e["unit_id"] for e in eligible}) == 6
    assert by[(2, "omml", "inline_text")][0]["eligibility"] == "needs_review"
    assert by[(2, "omml", "table_cell")][0]["eligibility"] == "needs_review"
    assert by[(3, "mathtype_ole", "standalone_shape")][0]["eligibility"] == "already_mathtype"
    assert by[(3, "math_text", "standalone_shape")][0]["eligibility"] == "needs_review"
    assert by[(3, "image", "standalone_shape")][0]["eligibility"] == "needs_review"
    grouped = by[(3, "omml", "standalone_shape")][0]
    assert grouped["group_path"] and grouped["eligibility"] == "eligible"
    animated = by[(4, "omml", "standalone_shape")][0]
    assert animated["eligibility"] == "needs_review" and "animation" in animated["reason"]


def test_plain_text_is_not_flagged(deck):
    texts = [e["text"] for e in _items(scan_file(deck))]
    assert "Introduction to trigonometry" not in texts
    assert "plain" not in texts and "label" not in texts


def test_omml_structure_is_preserved_in_mathml(deck):
    items = {e["id"]: e for e in _items(scan_file(deck))}
    constructs = {c for e in items.values() for c in e["constructs"]}
    for needed in ("fraction", "radical", "superscript", "subscript", "integral", "matrix", "equation_array"):
        assert needed in constructs
    texts = [e["text"] for e in items.values()]
    assert "a/b" in texts and "√x" in texts and "x^2+y_1; ∫_0^1 xdx" in texts
    frac = next(e for e in items.values() if e["text"] == "a/b")
    assert "<mfrac>" in frac["mathml"] and 'xmlns="http://www.w3.org/1998/Math/MathML"' in frac["mathml"]


def test_scan_does_not_modify_input(deck):
    before = _sha(deck)
    scan_file(deck)
    assert _sha(deck) == before


def test_convert_refuses_without_mathtype(deck, tmp_path):
    with pytest.raises(MathTypeUnavailableError):
        convert_file(deck, str(tmp_path / "w.pptx"), str(tmp_path / "o.pptx"), UnavailableAdapter())
    assert not (tmp_path / "o.pptx").exists()


def test_unreachable_worker_reports_unavailable():
    status = WindowsWorkerAdapter("http://127.0.0.1:9").status()
    assert status.available is False and status.guidance


def test_convert_with_mathtype_preserves_deck(deck, tmp_path):
    before_sha = _sha(deck)
    out = str(tmp_path / "out.pptx")
    adapter = FakeMathTypeAdapter()
    report = convert_file(deck, str(tmp_path / "w.pptx"), out, adapter)

    assert _sha(deck) == before_sha
    assert report["validation"]["passed"], report["validation"]["checks"]
    assert report["summary"]["converted"] == 6 and report["summary"]["failed"] == 0
    assert len(adapter.requests) == 6
    assert report["summary"]["after"]["mathtype_ole"] == 7
    assert report["summary"]["after"]["omml"] == 3

    src, dst = Presentation(deck), Presentation(out)
    assert len(src.slides) == len(dst.slides)
    assert dst.slides[0].notes_slide.notes_text_frame.text == "Speaker notes"
    s1_text = [sh.text_frame.text for sh in dst.slides[0].shapes if sh.has_text_frame]
    assert "Introduction to trigonometry" in s1_text
    s3_types = {sh.shape_type for sh in dst.slides[2].shapes}
    assert any(sh.has_chart for sh in dst.slides[2].shapes if hasattr(sh, "has_chart"))
    assert len(s3_types) >= 4
    for frame in dst.slides[0].shapes:
        if frame.shape_type is not None and frame.shape_type.name == "EMBEDDED_OLE_OBJECT":
            assert frame.ole_format.prog_id == "Equation.DSMT4"
            assert inspect_ole(frame.ole_format.blob) is None
            assert frame.left == src.slides[0].shapes[0].left or frame.left > 0


def test_rerun_does_not_duplicate(deck, tmp_path):
    first = str(tmp_path / "first.pptx")
    convert_file(deck, str(tmp_path / "w1.pptx"), first, FakeMathTypeAdapter())
    adapter = FakeMathTypeAdapter()
    report = convert_file(first, str(tmp_path / "w2.pptx"), str(tmp_path / "second.pptx"), adapter)
    assert adapter.requests == []
    assert report["summary"]["converted"] == 0
    assert report["summary"]["after"]["mathtype_ole"] == 7
    assert report["summary"]["skipped"] == 7


def test_non_mathtype_payload_is_rejected(deck, tmp_path):
    out = str(tmp_path / "out.pptx")
    report = convert_file(deck, str(tmp_path / "w.pptx"), out, FakeMathTypeAdapter(ole=PNG_1PX))
    assert report["summary"]["converted"] == 0 and report["summary"]["failed"] == 6
    assert report["summary"]["after"] == report["summary"]["before"]
