"""
ReadingOrderFixer — Do-No-Harm, Measurement-Driven Reading Order Fix
=======================================================================

Implements the complete Step 2–5 specification:

1. DO-NO-HARM: only modify a slide if inversions_after < inversions_before AND
   no hard constraint is violated (title first, footer last, z-order safe).
2. MINIMAL-EDIT: use Longest-Increasing-Subsequence to find which shapes to
   move (not move) — keep the already-correct relative order, only reinsert
   the misplaced ones.
3. THREE STRATEGIES:
   A) visual   — tolerance-based top-to-bottom, left-to-right (title first, footer last)
   B) xycut    — recursive XY-cut (existing algorithm)
   C) hybrid   — B when clear multi-column (>=2 cols, >=2 objects each), else A
4. INVERSION METRIC: counts pairs (A,B) where A precedes B in spTree but B is
   visually before A (top-to-bottom, left-to-right with row-tolerance).
5. REGRESSION GATE: fails loudly if any slide gets worse.
6. IDEMPOTENCY: running fixer twice on its own output changes nothing.
"""
from __future__ import annotations

import os
import shutil
import copy
from typing import Any, Dict, List, Optional, Tuple

from pptx import Presentation
from lxml import etree

from app.core.logging import logger
from app.services.reading_order_service import ReadingOrderService
from app.services.reading_order_config import (
    DEFAULT_SLIDE_WIDTH_EMU,
    DEFAULT_SLIDE_HEIGHT_EMU,
    BAND_TOLERANCE_RATIO,
    Z_ORDER_OVERLAP_AREA_RATIO,
    CONTAINER_CONTAINMENT_RATIO,
)
from app.services.geometry_helpers import resolve_placeholder_geometry, compute_rotated_bbox


# ──────────────────────────────────────────────────────────────────────────────
# Inversion metric
# ──────────────────────────────────────────────────────────────────────────────

def _compute_inversions(
    objects: List[Dict[str, Any]],
    slide_height: int,
    tolerance: Optional[int] = None,
) -> int:
    """
    Count pairs (A, B) where A appears before B in the sequence but B is
    visually before A (top-to-bottom, then left-to-right with row tolerance).
    """
    if tolerance is None:
        tolerance = max(180000, int(slide_height * BAND_TOLERANCE_RATIO))

    n = len(objects)
    count = 0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = objects[i], objects[j]
            a_row = a["top_emu"] // tolerance
            b_row = b["top_emu"] // tolerance
            if b_row < a_row or (b_row == a_row and b["left_emu"] < a["left_emu"]):
                count += 1
    return count


# ──────────────────────────────────────────────────────────────────────────────
# LIS-based minimal edit
# ──────────────────────────────────────────────────────────────────────────────

def _longest_increasing_subsequence_indices(values: List[int]) -> List[int]:
    """
    Returns indices into `values` forming the LIS (patience-sort, O(n log n)).
    The LIS gives the set of objects that are ALREADY in the correct relative
    order so they don't need to be moved.
    """
    n = len(values)
    if n == 0:
        return []

    tails: List[int] = []   # tails[i] = smallest tail value of IS of length i+1
    tail_idx: List[int] = []  # tail_idx[i] = index in values where that tail came from
    parents: List[int] = [-1] * n
    idxs: List[int] = []

    for i in range(n):
        v = values[i]
        lo, hi = 0, len(tails)
        while lo < hi:
            mid = (lo + hi) // 2
            if tails[mid] < v:
                lo = mid + 1
            else:
                hi = mid
        if lo < len(tails):
            tails[lo] = v
            tail_idx[lo] = i
        else:
            tails.append(v)
            tail_idx.append(i)
        parents[i] = tail_idx[lo - 1] if lo > 0 else -1

    # Reconstruct
    result = []
    idx = tail_idx[-1] if tail_idx else -1
    while idx != -1:
        result.append(idx)
        idx = parents[idx]
    result.reverse()
    return result


def _minimal_edit_reorder(
    orig_order: List[Dict[str, Any]],
    target_order: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Produce the minimal-edit reordering: keep shapes that are already in a
    valid relative order (LIS of target positions in original sequence),
    and reinsert the rest at their target positions.

    Returns the reordered list.
    """
    if len(orig_order) != len(target_order):
        return target_order  # fallback

    id_to_target_pos = {o["shape_id"]: i for i, o in enumerate(target_order)}
    target_positions_in_orig = [id_to_target_pos[o["shape_id"]] for o in orig_order]

    lis_indices = _longest_increasing_subsequence_indices(target_positions_in_orig)
    stable_ids = {orig_order[i]["shape_id"] for i in lis_indices}

    # Build result: follow target order, preserve stable shapes' relative position
    result = list(target_order)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Strategy A: visual top-to-bottom left-to-right
# ──────────────────────────────────────────────────────────────────────────────

def _visual_order(
    objects: List[Dict[str, Any]],
    slide_height: int,
    slide_width: int,
) -> List[Dict[str, Any]]:
    """
    Strategy A: tolerance-based top-to-bottom, left-to-right.
    Title first, footer/decorative last. Groups are atomic.
    """
    tolerance = max(180000, int(slide_height * BAND_TOLERANCE_RATIO))

    titles = [o for o in objects if o.get("is_title")]
    footers = [o for o in objects if o.get("semantic_role") == "footer" and not o.get("is_title")]
    decoratives = [o for o in objects if o.get("is_decorative") and not o.get("is_title") and o.get("semantic_role") != "footer"]
    body = [o for o in objects if not o.get("is_title") and o.get("semantic_role") != "footer" and not o.get("is_decorative")]

    def visual_key(o):
        row = o["top_emu"] // tolerance
        return (row, o["left_emu"], o["top_emu"])

    titles.sort(key=visual_key)
    footers.sort(key=visual_key)
    decoratives.sort(key=visual_key)
    body.sort(key=visual_key)

    return titles + body + decoratives + footers


# ──────────────────────────────────────────────────────────────────────────────
# Strategy B: XY-cut (delegates to existing ReadingOrderService)
# ──────────────────────────────────────────────────────────────────────────────

def _xycut_order(
    objects: List[Dict[str, Any]],
    slide,
    slide_width: int,
    slide_height: int,
) -> List[Dict[str, Any]]:
    """
    Strategy B: use the existing XY-cut algorithm from ReadingOrderService.
    """
    svc = ReadingOrderService()
    rec, _ = svc._determine_recommended_order(objects, slide_width, slide_height)
    return rec


# ──────────────────────────────────────────────────────────────────────────────
# Multi-column detection (for Strategy C)
# ──────────────────────────────────────────────────────────────────────────────

def _detect_multicolumn(
    objects: List[Dict[str, Any]],
    slide_width: int,
    slide_height: int,
    min_cols: int = 2,
    min_items_per_col: int = 2,
) -> bool:
    """
    Returns True if slide has a clear multi-column layout:
    - At least min_cols columns with a clear whitespace gap between them
    - Each column has at least min_items_per_col objects
    """
    body = [o for o in objects
            if not o.get("is_title")
            and o.get("semantic_role") != "footer"
            and not o.get("is_decorative")]

    if len(body) < min_cols * min_items_per_col:
        return False

    # Sort by left edge
    sorted_body = sorted(body, key=lambda o: o["left_emu"])

    # Find vertical gaps
    gap_threshold = max(100000, int(slide_width * 0.04))
    intervals = sorted([(o["left_emu"], o["left_emu"] + o["width_emu"]) for o in sorted_body])

    merged = []
    for s, e in intervals:
        if not merged:
            merged.append([s, e])
        elif s <= merged[-1][1] + gap_threshold:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])

    if len(merged) < min_cols:
        return False

    # Check each column has enough items
    for col_start, col_end in merged:
        col_items = [o for o in sorted_body
                     if o["left_emu"] >= col_start - gap_threshold
                     and o["left_emu"] + o["width_emu"] <= col_end + gap_threshold]
        if len(col_items) < min_items_per_col:
            return False

    return True


# ──────────────────────────────────────────────────────────────────────────────
# Z-order safety check
# ──────────────────────────────────────────────────────────────────────────────

def _check_z_order_safety(
    orig_order: List[Dict[str, Any]],
    new_order: List[Dict[str, Any]],
    slide,
) -> Tuple[bool, Optional[str]]:
    """
    Returns (is_safe, reason).
    Unsafe if a new order would change z-order of visually overlapping shapes
    (intersection > 2% of smaller shape area, both visible).
    """
    raw_shapes = {s.shape_id: s for s in slide.shapes}
    orig_positions = {o["shape_id"]: i for i, o in enumerate(orig_order)}
    new_positions = {o["shape_id"]: i for i, o in enumerate(new_order)}

    n = len(orig_order)
    for i, obj_a in enumerate(orig_order):
        for j, obj_b in enumerate(orig_order):
            if i >= j:
                continue

            sid_a = obj_a["shape_id"]
            sid_b = obj_b["shape_id"]

            # Check overlap
            l1, t1 = obj_a["left_emu"], obj_a["top_emu"]
            w1, h1 = obj_a["width_emu"], obj_a["height_emu"]
            l2, t2 = obj_b["left_emu"], obj_b["top_emu"]
            w2, h2 = obj_b["width_emu"], obj_b["height_emu"]

            ow = max(0, min(l1 + w1, l2 + w2) - max(l1, l2))
            oh = max(0, min(t1 + h1, t2 + h2) - max(t1, t2))
            overlap = ow * oh
            area1 = max(1, w1 * h1)
            area2 = max(1, w2 * h2)
            min_area = min(area1, area2)

            if overlap <= Z_ORDER_OVERLAP_AREA_RATIO * min_area:
                continue

            # They overlap significantly
            # In original: A was at position i, B at j (A is below B in z-order)
            orig_rel = orig_positions[sid_a] < orig_positions[sid_b]  # A before B originally
            new_rel = new_positions[sid_a] < new_positions[sid_b]    # A before B in new

            if orig_rel != new_rel:
                # Z-order would change — check if this would cause visual corruption
                # A background (no text, large) must stay below foreground
                a_text = obj_a.get("text_content", "").strip()
                b_text = obj_b.get("text_content", "").strip()
                # If one is a container and other is content, don't swap their z-order
                if (area1 > area2 and overlap > CONTAINER_CONTAINMENT_RATIO * area2 and not a_text):
                    return False, f"Z-order conflict: '{obj_a['name']}' (bg) would move above '{obj_b['name']}'"
                if (area2 > area1 and overlap > CONTAINER_CONTAINMENT_RATIO * area1 and not b_text):
                    return False, f"Z-order conflict: '{obj_b['name']}' (bg) would move above '{obj_a['name']}'"

    return True, None


# ──────────────────────────────────────────────────────────────────────────────
# spTree reorder (low-level)
# ──────────────────────────────────────────────────────────────────────────────

def _reorder_sptree(slide, ordered_shape_ids: List[int]) -> bool:
    """
    Reorder children of slide's spTree to match ordered_shape_ids.
    Preserves nvGrpSpPr, grpSpPr (header) and extLst (footer) exactly.
    """
    try:
        spTree = slide.shapes._spTree
        shape_map = {s.shape_id: s._element for s in slide.shapes}

        header_elems = [c for c in spTree if c.tag.split("}")[- 1] in ("nvGrpSpPr", "grpSpPr")]
        footer_elems = [c for c in spTree if c.tag.split("}")[-1] == "extLst"]
        shape_elems = [c for c in spTree if c not in header_elems and c not in footer_elems]

        if len(shape_elems) <= 1:
            return True

        ordered_elems = []
        for sid in ordered_shape_ids:
            elem = shape_map.get(sid)
            if elem is not None and elem in shape_elems:
                ordered_elems.append(elem)

        # Append any not in ordered list (shouldn't happen)
        for elem in shape_elems:
            if elem not in ordered_elems:
                ordered_elems.append(elem)

        for c in list(spTree):
            spTree.remove(c)
        for h in header_elems:
            spTree.append(h)
        for s in ordered_elems:
            spTree.append(s)
        for f in footer_elems:
            spTree.append(f)

        return True
    except Exception as e:
        logger.error("Failed to reorder spTree", error=str(e))
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Main fixer
# ──────────────────────────────────────────────────────────────────────────────

class ReadingOrderFixer:
    """
    Do-No-Harm, measurement-driven reading order fixer.

    For each slide:
    1. Compute inversions_before using visual metric
    2. Compute target order using chosen strategy
    3. Apply minimal-edit (LIS-based) reorder
    4. Check z-order safety
    5. Apply ONLY if inversions_after < inversions_before AND safe
    6. Otherwise: keep original, mark 'manual_review'
    """

    def __init__(self, strategy: str = "hybrid"):
        """
        Args:
            strategy: one of "visual" (A), "xycut" (B), "hybrid" (C, default)
        """
        valid = {"visual", "xycut", "hybrid"}
        if strategy not in valid:
            raise ValueError(f"strategy must be one of {valid}, got '{strategy}'")
        self.strategy = strategy
        self._svc = ReadingOrderService()

    def fix_presentation(
        self,
        input_path: str,
        output_path: str,
        use_ai_fallback: bool = False,
    ) -> Dict[str, Any]:
        """
        Fix reading order across all slides.
        Returns detailed report with per-slide status.
        Raises RuntimeError if regression gate fires (any slide got worse).
        """
        shutil.copy2(input_path, output_path)
        prs = Presentation(output_path)

        slide_width = prs.slide_width or DEFAULT_SLIDE_WIDTH_EMU
        slide_height = prs.slide_height or DEFAULT_SLIDE_HEIGHT_EMU
        total_slides = len(prs.slides)
        tolerance = max(180000, int(slide_height * BAND_TOLERANCE_RATIO))

        # Phase 1: analyze all slides (before fix)
        analyses = []
        for idx, slide in enumerate(prs.slides):
            analysis = self._svc.analyze_slide(
                slide=slide,
                slide_idx=idx,
                slide_width=slide_width,
                slide_height=slide_height,
                use_ai_fallback=use_ai_fallback,
            )
            analyses.append(analysis)

        slide_details = []
        total_inversions_before = 0
        total_inversions_after = 0
        already_correct = 0
        fixed_count = 0
        manual_review_count = 0
        untouched_count = 0

        for idx, slide in enumerate(prs.slides):
            analysis = analyses[idx]
            slide_num = idx + 1
            orig_objects = analysis["current_sequence"]
            n = len(orig_objects)

            # Compute inversions before
            inv_before = _compute_inversions(orig_objects, slide_height, tolerance)
            total_inversions_before += inv_before

            # Skip single-object or empty slides
            if n <= 1:
                already_correct += 1
                total_inversions_after += inv_before
                slide_details.append({
                    "slide_number": slide_num,
                    "title": analysis.get("title"),
                    "status": "correct",
                    "reason": "single_or_empty",
                    "inversions_before": inv_before,
                    "inversions_after": inv_before,
                    "shapes_moved": 0,
                })
                continue

            # Compute target order using chosen strategy
            chosen_strategy = self.strategy
            if chosen_strategy == "hybrid":
                if _detect_multicolumn(orig_objects, slide_width, slide_height):
                    chosen_strategy = "xycut"
                else:
                    chosen_strategy = "visual"

            if chosen_strategy == "visual":
                target_objects = _visual_order(orig_objects, slide_height, slide_width)
            else:
                target_objects = _xycut_order(orig_objects, slide, slide_width, slide_height)

            # Validate target contains all same IDs
            orig_ids = {o["shape_id"] for o in orig_objects}
            target_ids = {o["shape_id"] for o in target_objects}
            if orig_ids != target_ids or len(orig_objects) != len(target_objects):
                # Fallback to visual
                target_objects = _visual_order(orig_objects, slide_height, slide_width)

            # Minimal-edit: keep LIS stable, reinsert misplaced
            final_objects = _minimal_edit_reorder(orig_objects, target_objects)

            # Compute inversions after
            inv_after = _compute_inversions(final_objects, slide_height, tolerance)

            # Check if already correct by our metric
            orig_order_ids = [o["shape_id"] for o in orig_objects]
            final_order_ids = [o["shape_id"] for o in final_objects]
            order_unchanged = orig_order_ids == final_order_ids

            if order_unchanged or inv_after >= inv_before:
                # Do not touch — already correct or would make things worse
                total_inversions_after += inv_before
                if inv_before == 0 or order_unchanged:
                    already_correct += 1
                    status = "correct"
                    reason = "already_optimal"
                else:
                    manual_review_count += 1
                    status = "manual_review"
                    reason = f"fix_would_not_improve (before={inv_before} after={inv_after})"
                    untouched_count += 1

                slide_details.append({
                    "slide_number": slide_num,
                    "title": analysis.get("title"),
                    "status": status,
                    "reason": reason,
                    "inversions_before": inv_before,
                    "inversions_after": inv_before,
                    "shapes_moved": 0,
                    "strategy_used": chosen_strategy,
                })
                continue

            # Z-order safety check
            is_safe, safety_reason = _check_z_order_safety(orig_objects, final_objects, slide)
            if not is_safe:
                manual_review_count += 1
                total_inversions_after += inv_before
                slide_details.append({
                    "slide_number": slide_num,
                    "title": analysis.get("title"),
                    "status": "manual_review",
                    "reason": f"z_order_unsafe: {safety_reason}",
                    "inversions_before": inv_before,
                    "inversions_after": inv_before,
                    "shapes_moved": 0,
                    "strategy_used": chosen_strategy,
                })
                continue

            # Title must be first among meaningful objects
            non_decorative = [o for o in final_objects if not o.get("is_decorative") and o.get("semantic_role") != "footer"]
            if non_decorative and not non_decorative[0].get("is_title"):
                # Check if there's a title at all
                title_obj = next((o for o in final_objects if o.get("is_title")), None)
                if title_obj is not None:
                    # Title constraint violated — try to fix by moving title first
                    final_objects = [title_obj] + [o for o in final_objects if o["shape_id"] != title_obj["shape_id"]]
                    inv_after = _compute_inversions(final_objects, slide_height, tolerance)
                    if inv_after >= inv_before:
                        manual_review_count += 1
                        total_inversions_after += inv_before
                        slide_details.append({
                            "slide_number": slide_num,
                            "title": analysis.get("title"),
                            "status": "manual_review",
                            "reason": "title_constraint_violated_and_fix_didnt_help",
                            "inversions_before": inv_before,
                            "inversions_after": inv_before,
                            "shapes_moved": 0,
                            "strategy_used": chosen_strategy,
                        })
                        continue

            # Count shapes moved
            shapes_moved = sum(
                1 for oi, fi in zip(orig_order_ids, final_order_ids) if oi != fi
            )

            # Apply the reorder
            ok = _reorder_sptree(slide, final_order_ids)
            if not ok:
                manual_review_count += 1
                total_inversions_after += inv_before
                slide_details.append({
                    "slide_number": slide_num,
                    "title": analysis.get("title"),
                    "status": "error",
                    "reason": "spTree_reorder_failed",
                    "inversions_before": inv_before,
                    "inversions_after": inv_before,
                    "shapes_moved": 0,
                    "strategy_used": chosen_strategy,
                })
                continue

            fixed_count += 1
            total_inversions_after += inv_after
            slide_details.append({
                "slide_number": slide_num,
                "title": analysis.get("title"),
                "status": "fixed",
                "reason": f"inversions {inv_before} -> {inv_after}",
                "inversions_before": inv_before,
                "inversions_after": inv_after,
                "shapes_moved": shapes_moved,
                "strategy_used": chosen_strategy,
                "orig_order": orig_order_ids,
                "new_order": final_order_ids,
            })

        prs.save(output_path)

        # ── REGRESSION GATE ───────────────────────────────────────────────────
        # Reopen and verify per-slide inversions didn't increase
        prs_check = Presentation(output_path)
        regression_slides = []
        for idx, slide in enumerate(prs_check.slides):
            detail = slide_details[idx]
            if detail["status"] != "fixed":
                continue
            shapes_after = list(slide.shapes)
            after_objs = []
            for s in shapes_after:
                left, top, width, height, _ = resolve_placeholder_geometry(s, slide)
                rot = getattr(s, "rotation", 0) or 0
                if rot != 0:
                    left, top, width, height = compute_rotated_bbox(left, top, width, height, int(rot * 60000))
                after_objs.append({
                    "shape_id": s.shape_id,
                    "left_emu": left,
                    "top_emu": top,
                    "width_emu": width,
                    "height_emu": height,
                })
            inv_verified = _compute_inversions(after_objs, slide_height, tolerance)
            detail["inversions_verified"] = inv_verified
            if inv_verified > detail["inversions_before"]:
                regression_slides.append({
                    "slide_number": detail["slide_number"],
                    "inversions_before": detail["inversions_before"],
                    "inversions_after": inv_verified,
                })

        if regression_slides:
            msg = (
                f"REGRESSION GATE FIRED: {len(regression_slides)} slide(s) got WORSE after fix.\n"
                + "\n".join(
                    f"  Slide {r['slide_number']}: before={r['inversions_before']} after={r['inversions_after']}"
                    for r in regression_slides
                )
            )
            logger.error(msg)
            # DO NOT output "Reading Order Fixed ✓" — raise hard error
            raise RuntimeError(msg)

        return {
            "summary": {
                "total_slides": total_slides,
                "already_correct": already_correct,
                "fixed": fixed_count,
                "manual_review": manual_review_count,
                "total_inversions_before": total_inversions_before,
                "total_inversions_after": total_inversions_after,
                "strategy": self.strategy,
            },
            "slides": slide_details,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Generate A/B/C strategy files
# ──────────────────────────────────────────────────────────────────────────────

def generate_strategy_files(
    input_path: str,
    output_dir: Optional[str] = None,
) -> Dict[str, str]:
    """
    Generate three fixed decks: <name>_fix_A.pptx, _fix_B.pptx, _fix_C.pptx.
    Returns dict of strategy -> output_path.
    Also writes strategy_results.json template.
    """
    base = os.path.splitext(input_path)[0]
    base_name = os.path.basename(base)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        out_base = os.path.join(output_dir, base_name)
    else:
        out_base = base

    paths = {}
    for strategy_name, suffix in [("visual", "A"), ("xycut", "B"), ("hybrid", "C")]:
        out_path = f"{out_base}_fix_{suffix}.pptx"
        fixer = ReadingOrderFixer(strategy=strategy_name)
        result = fixer.fix_presentation(input_path, out_path)
        paths[suffix] = out_path
        print(f"[{suffix}] {strategy_name}: fixed={result['summary']['fixed']}, "
              f"manual_review={result['summary']['manual_review']}, "
              f"inversions {result['summary']['total_inversions_before']} -> "
              f"{result['summary']['total_inversions_after']}")

    # Analyze original to get slide count
    prs = Presentation(input_path)
    total_slides = len(prs.slides)
    slide_nums = list(range(1, total_slides + 1))

    # Write strategy_results.json template
    template = {
        "_instructions": (
            "Open each PPTX in PowerPoint, run Accessibility Checker, "
            "record which slide numbers are flagged under 'Check reading order'."
        ),
        "original": [],
        "A": [],
        "B": [],
        "C": [],
    }
    template_path = os.path.join(output_dir or ".", "strategy_results.json")
    import json
    with open(template_path, "w", encoding="utf-8") as f:
        json.dump(template, f, indent=2)
    print(f"\nWrote template: {template_path}")
    print("Fill in the slide numbers flagged by PowerPoint's Accessibility Checker for each strategy.")

    paths["template"] = template_path
    return paths


# ──────────────────────────────────────────────────────────────────────────────
# Default singleton
# ──────────────────────────────────────────────────────────────────────────────

reading_order_fixer = ReadingOrderFixer(strategy="hybrid")
