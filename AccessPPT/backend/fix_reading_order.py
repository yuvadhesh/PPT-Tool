#!/usr/bin/env python3
"""
fix_reading_order.py — CLI for measurement-driven reading order fixing

Usage:
    python fix_reading_order.py input.pptx [--strategy hybrid|visual|xycut]
    python fix_reading_order.py input.pptx --all-strategies
    python fix_reading_order.py --compare strategy_results.json
    python fix_reading_order.py input.pptx --diagnose
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from pptx import Presentation
from app.services.reading_order_fixer import (
    ReadingOrderFixer,
    generate_strategy_files,
    _compute_inversions,
    _detect_multicolumn,
)
from app.services.reading_order_service import reading_order_service
from app.services.reading_order_config import (
    DEFAULT_SLIDE_WIDTH_EMU,
    DEFAULT_SLIDE_HEIGHT_EMU,
    BAND_TOLERANCE_RATIO,
)
from app.services.geometry_helpers import (
    resolve_placeholder_geometry,
    compute_rotated_bbox,
    detect_ooxml_element_type,
    is_shape_decorative,
)
from app.services.reading_order_config import Z_ORDER_OVERLAP_AREA_RATIO


def cmd_fix(args):
    """Fix a single deck with one strategy."""
    input_path = args.input
    if not os.path.exists(input_path):
        print(f"ERROR: File not found: {input_path}")
        sys.exit(1)

    base = os.path.splitext(input_path)[0]
    strategy = args.strategy
    output_path = args.output or f"{base}_fixed_{strategy}.pptx"

    print(f"Fixing: {input_path}")
    print(f"Strategy: {strategy}")
    print(f"Output: {output_path}")
    print()

    fixer = ReadingOrderFixer(strategy=strategy)
    try:
        result = fixer.fix_presentation(input_path, output_path)
    except RuntimeError as e:
        print(f"\n[REGRESSION GATE FIRED]\n{e}")
        sys.exit(2)

    s = result["summary"]
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Strategy:          {s['strategy']}")
    print(f"  Total slides:      {s['total_slides']}")
    print(f"  Already correct:   {s['already_correct']}")
    print(f"  Fixed:             {s['fixed']}")
    print(f"  Manual review:     {s['manual_review']}")
    print(f"  Inversions before: {s['total_inversions_before']}")
    print(f"  Inversions after:  {s['total_inversions_after']}")
    print()

    print("PER-SLIDE STATUS")
    print("-" * 80)
    print(f"{'Slide':<7} {'Status':<15} {'Inv.Before':<12} {'Inv.After':<11} {'Moved':<7} {'Reason'}")
    print("-" * 80)
    for d in result["slides"]:
        inv_b = d.get("inversions_before", 0)
        inv_a = d.get("inversions_after", 0)
        moved = d.get("shapes_moved", 0)
        reason = d.get("reason", "")
        print(f"{d['slide_number']:<7} {d['status']:<15} {inv_b:<12} {inv_a:<11} {moved:<7} {reason}")

    print()
    print(f"Output saved to: {output_path}")


def cmd_all_strategies(args):
    """Generate all 3 strategy files and template."""
    input_path = args.input
    if not os.path.exists(input_path):
        print(f"ERROR: File not found: {input_path}")
        sys.exit(1)

    print(f"Generating A/B/C strategy files for: {input_path}")
    print()

    paths = generate_strategy_files(input_path, output_dir=os.path.dirname(input_path) or ".")
    print()
    print("Files generated:")
    for key, path in paths.items():
        print(f"  [{key}] {path}")

    print()
    print("Next steps:")
    print("  1. Open each _fix_A.pptx, _fix_B.pptx, _fix_C.pptx in PowerPoint")
    print("  2. Run Accessibility Checker (Review > Check Accessibility)")
    print("  3. Record flagged slide numbers for each strategy in strategy_results.json")
    print("  4. Run: python fix_reading_order.py --compare strategy_results.json")


def cmd_compare(args):
    """Compare strategy results and derive rules."""
    results_path = args.compare
    if not os.path.exists(results_path):
        print(f"ERROR: File not found: {results_path}")
        sys.exit(1)

    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    original_flagged = set(data.get("original", []))
    a_flagged = set(data.get("A", []))
    b_flagged = set(data.get("B", []))
    c_flagged = set(data.get("C", []))

    # The original pptx to get slide features
    pptx_path = args.input
    if not pptx_path or not os.path.exists(pptx_path):
        print("ERROR: --input <original.pptx> is required for --compare")
        sys.exit(1)

    prs = Presentation(pptx_path)
    sw = prs.slide_width or DEFAULT_SLIDE_WIDTH_EMU
    sh = prs.slide_height or DEFAULT_SLIDE_HEIGHT_EMU
    tolerance = max(180000, int(sh * BAND_TOLERANCE_RATIO))

    print("=" * 80)
    print("STRATEGY COMPARISON REPORT")
    print("=" * 80)
    print(f"Original flagged: {sorted(original_flagged)}")
    print(f"Strategy A (visual) flagged: {sorted(a_flagged)}")
    print(f"Strategy B (xycut) flagged:  {sorted(b_flagged)}")
    print(f"Strategy C (hybrid) flagged: {sorted(c_flagged)}")
    print()

    # Per-slide: which strategy won
    all_slide_nums = set(data.get("original", [])) | a_flagged | b_flagged | c_flagged
    if not all_slide_nums:
        all_slide_nums = set(range(1, len(prs.slides) + 1))

    print(f"{'Slide':<7} {'Orig':<6} {'A':<6} {'B':<6} {'C':<6} {'Best':<8} {'Layout Features'}")
    print("-" * 100)

    strategy_wins = {"A": 0, "B": 0, "C": 0, "tie": 0}

    for slide_num in sorted(all_slide_nums):
        idx = slide_num - 1
        if idx >= len(prs.slides):
            continue
        slide = prs.slides[idx]
        shapes = list(slide.shapes)

        # Extract shape features
        shape_geoms = []
        count_groups = 0
        count_overlapping = 0
        count_rotated = 0
        count_tables = 0
        count_charts = 0
        has_connector = False
        has_alternateContent = False

        for s in shapes:
            left, top, width, height, _ = resolve_placeholder_geometry(s, slide)
            rot = getattr(s, "rotation", 0) or 0
            if rot != 0:
                count_rotated += 1
                left, top, width, height = compute_rotated_bbox(left, top, width, height, int(rot * 60000))
            stype = detect_ooxml_element_type(s)
            if stype == "group":
                count_groups += 1
            if stype == "connector":
                has_connector = True
            if stype == "AlternateContent":
                has_alternateContent = True
            if stype == "table":
                count_tables += 1
            if stype == "chart":
                count_charts += 1
            shape_geoms.append({"left": left, "top": top, "width": width, "height": height, "id": s.shape_id})

        for i in range(len(shape_geoms)):
            for j in range(i + 1, len(shape_geoms)):
                g1, g2 = shape_geoms[i], shape_geoms[j]
                ow = max(0, min(g1["left"] + g1["width"], g2["left"] + g2["width"]) - max(g1["left"], g2["left"]))
                oh = max(0, min(g1["top"] + g1["height"], g2["top"] + g2["height"]) - max(g1["top"], g2["top"]))
                oa = ow * oh
                ma = min(max(1, g1["width"] * g1["height"]), max(1, g2["width"] * g2["height"]))
                if oa > Z_ORDER_OVERLAP_AREA_RATIO * ma:
                    count_overlapping += 1

        # Build simple object list for multicolumn detection
        objs = [
            {
                "shape_id": s.shape_id,
                "left_emu": shape_geoms[i]["left"],
                "top_emu": shape_geoms[i]["top"],
                "width_emu": shape_geoms[i]["width"],
                "height_emu": shape_geoms[i]["height"],
                "is_title": False,
                "semantic_role": "body_text",
                "is_decorative": is_shape_decorative(s),
            }
            for i, s in enumerate(shapes)
        ]
        is_multicol = _detect_multicolumn(objs, sw, sh)

        features = (
            f"shapes={len(shapes)} "
            f"groups={count_groups} "
            f"overlaps={count_overlapping} "
            f"rotated={count_rotated} "
            f"tables={count_tables} "
            f"charts={count_charts} "
            f"multicol={is_multicol} "
            f"connector={has_connector} "
            f"altcontent={has_alternateContent}"
        )

        in_orig = "Y" if slide_num in original_flagged else "-"
        in_a = "Y" if slide_num in a_flagged else "-"
        in_b = "Y" if slide_num in b_flagged else "-"
        in_c = "Y" if slide_num in c_flagged else "-"

        # Determine best strategy (fewest flags = best)
        counts = {
            "A": 1 if slide_num in a_flagged else 0,
            "B": 1 if slide_num in b_flagged else 0,
            "C": 1 if slide_num in c_flagged else 0,
        }
        min_count = min(counts.values())
        best = [k for k, v in counts.items() if v == min_count]
        if len(best) == 3:
            best_str = "all_pass" if min_count == 0 else "all_flag"
        else:
            best_str = "/".join(best)

        print(f"{slide_num:<7} {in_orig:<6} {in_a:<6} {in_b:<6} {in_c:<6} {best_str:<8} {features}")

    # Summary
    print()
    print("SUMMARY COUNTS:")
    print(f"  Original:   {len(original_flagged)} flagged")
    print(f"  Strategy A: {len(a_flagged)} flagged")
    print(f"  Strategy B: {len(b_flagged)} flagged")
    print(f"  Strategy C: {len(c_flagged)} flagged")

    best_strategy = min(
        [("A", len(a_flagged)), ("B", len(b_flagged)), ("C", len(c_flagged))],
        key=lambda x: x[1]
    )
    print(f"\nBest performing strategy: {best_strategy[0]} ({best_strategy[1]} flags)")


def cmd_diagnose(args):
    """Diagnose inversions per slide in a deck."""
    input_path = args.input
    if not os.path.exists(input_path):
        print(f"ERROR: File not found: {input_path}")
        sys.exit(1)

    prs = Presentation(input_path)
    sw = prs.slide_width or DEFAULT_SLIDE_WIDTH_EMU
    sh = prs.slide_height or DEFAULT_SLIDE_HEIGHT_EMU
    tolerance = max(180000, int(sh * BAND_TOLERANCE_RATIO))

    result = reading_order_service.analyze_presentation(input_path, use_ai_fallback=False)

    print(f"Diagnosing: {input_path}")
    print(f"Total slides: {len(prs.slides)}")
    print()

    total_inversions = 0
    for slide_data in result["slides"]:
        objs = slide_data["current_sequence"]
        inv = _compute_inversions(objs, sh, tolerance)
        total_inversions += inv
        mc = _detect_multicolumn(objs, sw, sh)
        status = slide_data["status"]
        print(
            f"Slide {slide_data['slide_number']:>3}: "
            f"status={status:<5} "
            f"inversions={inv:<4} "
            f"shapes={len(objs):<4} "
            f"multicol={mc}"
        )

    print(f"\nTotal inversions: {total_inversions}")


def main():
    parser = argparse.ArgumentParser(
        description="Measurement-driven PowerPoint reading order fixer"
    )
    parser.add_argument("input", nargs="?", help="Input PPTX file")
    parser.add_argument("--strategy", default="hybrid",
                        choices=["visual", "xycut", "hybrid"],
                        help="Reordering strategy (default: hybrid)")
    parser.add_argument("--output", help="Output PPTX path")
    parser.add_argument("--all-strategies", action="store_true",
                        help="Generate A/B/C strategy files + template JSON")
    parser.add_argument("--compare", metavar="RESULTS_JSON",
                        help="Compare strategy results from PowerPoint Accessibility Checker")
    parser.add_argument("--diagnose", action="store_true",
                        help="Print per-slide inversion counts without fixing")

    args = parser.parse_args()

    if args.compare:
        cmd_compare(args)
    elif args.input and args.diagnose:
        cmd_diagnose(args)
    elif args.input and args.all_strategies:
        cmd_all_strategies(args)
    elif args.input:
        cmd_fix(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
