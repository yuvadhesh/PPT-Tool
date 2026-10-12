"""Builds the scan inventory and the conversion report returned to the UI."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from app.services.equations.equation_classifier import CATEGORY_LABELS
from app.services.equations.equation_detector import EquationCandidate


def inventory(candidates: list[EquationCandidate], slide_count: int) -> dict:
    by_category = Counter(c.category for c in candidates)
    by_eligibility = Counter(c.eligibility for c in candidates)
    slides = []
    for n in range(1, slide_count + 1):
        items = [c.to_dict() for c in candidates if c.slide_number == n]
        if items:
            slides.append({"slide_number": n, "equations": items})
    return {
        "slide_count": slide_count,
        "total": len(candidates),
        "by_category": dict(by_category),
        "by_eligibility": dict(by_eligibility),
        "category_labels": CATEGORY_LABELS,
        "slides": slides,
    }


def build_report(
    before: dict,
    after: Optional[dict],
    results: dict[str, dict],
    candidates: list[EquationCandidate],
    validation: list[dict],
    adapter_status: dict,
    original_sha256: str,
) -> dict:
    items = []
    for c in candidates:
        res = results.get(c.id)
        if res:
            status, reason = res["status"], res["reason"]
        elif c.eligibility == "already_mathtype":
            status, reason = "skipped", c.reason
        else:
            status, reason = "needs_review", c.reason
        items.append({
            "id": c.id,
            "slide_number": c.slide_number,
            "shape_id": c.shape_id,
            "shape_name": c.shape_name,
            "category": c.category,
            "text": c.text,
            "status": status,
            "reason": reason,
        })
    counts = Counter(i["status"] for i in items)
    validation_passed = all(v["passed"] for v in validation) if validation else False
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "adapter": adapter_status,
        "original_sha256": original_sha256,
        "summary": {
            "before": before.get("by_category", {}),
            "after": (after or {}).get("by_category", {}),
            "converted": counts.get("converted", 0),
            "failed": counts.get("failed", 0),
            "skipped": counts.get("skipped", 0),
            "needs_review": counts.get("needs_review", 0),
        },
        "validation": {"passed": validation_passed, "checks": validation},
        "items": items,
    }
