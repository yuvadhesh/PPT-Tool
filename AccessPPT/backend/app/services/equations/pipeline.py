"""Scan and conversion orchestration for the Equation → MathType feature."""
from __future__ import annotations

import shutil
from typing import Callable, Optional

from lxml import etree
from pptx import Presentation

from app.services.equations.conversion_report import build_report, inventory
from app.services.equations.conversion_validator import sha256_file, validate_mathtype_object, validate_output
from app.services.equations.equation_classifier import ELIGIBLE, classify
from app.services.equations.equation_detector import EquationCandidate, equation_detector, text_animated_shape_ids
from app.services.equations.mathtype_adapter import (
    ConversionRequest,
    MathTypeAdapter,
    MathTypeConversionError,
    MathTypeUnavailableError,
)
from app.services.equations.omml_processor import combine_mathml
from app.services.equations.pptx_preservation import replace_with_mathtype_object

ProgressFn = Callable[[int, str], None]


def _detect(prs) -> list[EquationCandidate]:
    candidates = equation_detector.detect(prs)
    animated = {i: text_animated_shape_ids(s) for i, s in enumerate(prs.slides, start=1)}
    return classify(candidates, animated)


def scan_file(path: str) -> dict:
    prs = Presentation(path)
    return inventory(_detect(prs), len(prs.slides))


def convert_file(
    original_path: str,
    working_path: str,
    output_path: str,
    adapter: MathTypeAdapter,
    progress: Optional[ProgressFn] = None,
) -> dict:
    progress = progress or (lambda pct, msg: None)
    status = adapter.status()
    if not status.available:
        raise MathTypeUnavailableError(status.details or "MathType integration unavailable")

    original_sha = sha256_file(original_path)
    shutil.copyfile(original_path, working_path)
    progress(5, "Scanning equations...")
    prs = Presentation(working_path)
    candidates = _detect(prs)
    before = inventory(candidates, len(prs.slides))

    units: dict[str, list[EquationCandidate]] = {}
    for c in candidates:
        if c.eligibility == ELIGIBLE and c.unit_id:
            units.setdefault(c.unit_id, []).append(c)

    results: dict[str, dict] = {}
    converted: list[tuple[int, int]] = []
    for n, (unit_id, group) in enumerate(units.items(), start=1):
        progress(10 + int(75 * (n - 1) / max(1, len(units))), f"Converting equation {n} of {len(units)}...")
        head = group[0]
        request = ConversionRequest(
            unit_id=unit_id,
            mathml=combine_mathml([c.mathml for c in group]),
            omml=[etree.tostring(c.equation_element, encoding="unicode") for c in group],
            font_size_pt=head.font_size_pt,
        )
        try:
            obj = adapter.convert(request)
            problem = validate_mathtype_object(obj)
            if problem:
                raise MathTypeConversionError(problem)
            alt = "Equation: " + "; ".join(c.text for c in group)
            replace_with_mathtype_object(prs.slides[head.slide_number - 1], head, obj, alt)
            converted.append((head.slide_number, head.shape_id))
            for c in group:
                results[c.id] = {"status": "converted", "reason": f"Replaced by MathType object ({obj.prog_id})."}
        except (MathTypeConversionError, MathTypeUnavailableError, ValueError) as e:
            for c in group:
                results[c.id] = {"status": "failed", "reason": str(e)}

    progress(88, "Saving and validating converted presentation...")
    prs.save(output_path)
    validation = validate_output(original_path, original_sha, output_path, converted)
    after = scan_file(output_path)
    progress(100, "Done")
    return build_report(before, after, results, candidates, validation, status.to_dict(), original_sha)
