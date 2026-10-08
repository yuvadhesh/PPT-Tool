#!/usr/bin/env python3
"""
Step 1 Diagnosis Script: Compare original vs fixed deck to find root causes
of the regression (more slides flagged after fix than before).
"""
import sys
import os
sys.path.insert(0, '.')

from pptx import Presentation
from lxml import etree
from app.services.reading_order_service import reading_order_service
from app.services.reading_order_config import (
    DEFAULT_SLIDE_WIDTH_EMU, DEFAULT_SLIDE_HEIGHT_EMU, BAND_TOLERANCE_RATIO
)


def get_spTree_shape_names(pptx_path, slide_idx):
    """Return list of (tag, name, shape_id) tuples in spTree order."""
    prs = Presentation(pptx_path)
    slide = prs.slides[slide_idx]
    spTree = slide.shapes._spTree
    header_tags = ('nvGrpSpPr', 'grpSpPr')
    footer_tags = ('extLst',)
    shapes = []
    for c in spTree:
        tag = c.tag.split('}')[-1]
        if tag not in header_tags and tag not in footer_tags:
            name = 'Unknown'
            shape_id = '?'
            for child in c.iter():
                ct = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if ct == 'cNvPr':
                    name = child.get('name', 'Unknown')
                    shape_id = child.get('id', '?')
                    break
            shapes.append((tag, name, shape_id))
    return shapes


def count_inversions(objects):
    """Count pairs (A,B) where A is before B in sequence but B is visually before A (top, left)."""
    n = len(objects)
    inversions = 0
    for i in range(n):
        for j in range(i+1, n):
            a = objects[i]
            b = objects[j]
            # visual order: top-to-bottom, left-to-right
            a_pos = (a['top_emu'], a['left_emu'])
            b_pos = (b['top_emu'], b['left_emu'])
            if b_pos < a_pos:
                inversions += 1
    return inversions


def main():
    orig_path = 'before_reorder_slide4.pptx'
    fixed_path = 'before_reorder_slide4_reading_order_fixed.pptx'

    if not os.path.exists(orig_path):
        print(f"ERROR: {orig_path} not found")
        sys.exit(1)
    if not os.path.exists(fixed_path):
        print(f"ERROR: {fixed_path} not found")
        sys.exit(1)

    print("=" * 80)
    print("STEP 1: DIAGNOSIS REPORT")
    print("=" * 80)

    # Analyze original
    orig_result = reading_order_service.analyze_presentation(orig_path, use_ai_fallback=False)
    # Analyze fixed
    fixed_result = reading_order_service.analyze_presentation(fixed_path, use_ai_fallback=False)

    orig_failed = [s['slide_number'] for s in orig_result['slides'] if s['status'] == 'FAIL']
    fixed_failed = [s['slide_number'] for s in fixed_result['slides'] if s['status'] == 'FAIL']

    print(f"\nOriginal deck: {len(orig_failed)} slides FAIL: {orig_failed}")
    print(f"Fixed deck:    {len(fixed_failed)} slides FAIL: {fixed_failed}")
    print()

    # Find regression slides (PASS -> FAIL)
    regression_slides = []
    improved_slides = []
    for idx in range(len(orig_result['slides'])):
        o = orig_result['slides'][idx]
        f = fixed_result['slides'][idx]
        if o['status'] == 'PASS' and f['status'] == 'FAIL':
            regression_slides.append(o['slide_number'])
        elif o['status'] == 'FAIL' and f['status'] == 'PASS':
            improved_slides.append(o['slide_number'])

    print(f"REGRESSION (PASS->FAIL): {regression_slides}")
    print(f"IMPROVED   (FAIL->PASS): {improved_slides}")
    print()

    # Detailed per-slide report
    print("=" * 80)
    print("PER-SLIDE DETAILED REPORT")
    print("=" * 80)

    for idx in range(len(orig_result['slides'])):
        o_slide = orig_result['slides'][idx]
        f_slide = fixed_result['slides'][idx]
        slide_num = o_slide['slide_number']

        orig_xml_names = get_spTree_shape_names(orig_path, idx)
        fixed_xml_names = get_spTree_shape_names(fixed_path, idx)

        orig_ids = [x[2] for x in orig_xml_names]
        fixed_ids = [x[2] for x in fixed_xml_names]

        # Count how many shapes changed position
        changed_count = sum(1 for i, (oi, fi) in enumerate(zip(orig_ids, fixed_ids)) if oi != fi)
        order_changed = orig_ids != fixed_ids

        status_changed = o_slide['status'] != f_slide['status']

        # Compute inversions in original
        orig_objs = o_slide['current_sequence']
        o_inversions = count_inversions(orig_objs)

        line = (
            f"Slide {slide_num:>3}: "
            f"Orig={o_slide['status']:<5} "
            f"Fixed={f_slide['status']:<5} "
            f"OrderChanged={str(order_changed):<6} "
            f"ShapesMoved={changed_count:<3} "
            f"OrigInversions={o_inversions:<3}"
        )
        if status_changed or (order_changed and o_inversions == 0):
            line += " <-- PROBLEM"
        print(line)

    # Detailed look at regression slides
    print()
    print("=" * 80)
    print("REGRESSION SLIDES (PASS -> FAIL after fix) -- ROOT CAUSE")
    print("=" * 80)

    for slide_num in regression_slides:
        idx = slide_num - 1
        o_slide = orig_result['slides'][idx]
        f_slide = fixed_result['slides'][idx]

        print(f"\n--- Slide {slide_num} ---")
        print(f"  Title: {o_slide.get('title', 'N/A')}")

        orig_xml = get_spTree_shape_names(orig_path, idx)
        fixed_xml = get_spTree_shape_names(fixed_path, idx)

        print(f"  Original XML order:  {[(n, sid) for t, n, sid in orig_xml]}")
        print(f"  Fixed XML order:     {[(n, sid) for t, n, sid in fixed_xml]}")

        orig_rec = o_slide['recommended_sequence']
        print(f"  Recommended order (orig analysis): {[o['name'] for o in orig_rec]}")

        print(f"  Fixed slide issues:")
        for issue in f_slide['issues']:
            print(f"    [{issue['code']}] {issue['description']}")

        # Original inversions
        orig_objs = o_slide['current_sequence']
        o_inversions = count_inversions(orig_objs)
        print(f"  Original inversions: {o_inversions}")
        print(f"  Was already correct (0 inversions): {o_inversions == 0}")

    # Slides that were already correct but were still modified
    print()
    print("=" * 80)
    print("SLIDES MODIFIED WHEN ALREADY CORRECT (inversions=0 but order changed) -- DO NOT TOUCH")
    print("=" * 80)

    for idx in range(len(orig_result['slides'])):
        o_slide = orig_result['slides'][idx]
        slide_num = o_slide['slide_number']

        orig_xml = get_spTree_shape_names(orig_path, idx)
        fixed_xml = get_spTree_shape_names(fixed_path, idx)
        orig_ids = [x[2] for x in orig_xml]
        fixed_ids = [x[2] for x in fixed_xml]
        order_changed = orig_ids != fixed_ids

        orig_objs = o_slide['current_sequence']
        o_inversions = count_inversions(orig_objs)
        was_pass = o_slide['status'] == 'PASS'

        if order_changed and was_pass:
            print(f"  Slide {slide_num}: status=PASS, inversions={o_inversions}, but ORDER WAS MODIFIED!")
            print(f"    Orig: {[(n, sid) for t, n, sid in orig_xml]}")
            print(f"    Fixed: {[(n, sid) for t, n, sid in fixed_xml]}")

    # Accidental changes check: dropped/duplicated
    print()
    print("=" * 80)
    print("ACCIDENTAL CHANGES CHECK (dropped/duplicated elements)")
    print("=" * 80)

    for idx in range(len(orig_result['slides'])):
        slide_num = idx + 1
        orig_xml = get_spTree_shape_names(orig_path, idx)
        fixed_xml = get_spTree_shape_names(fixed_path, idx)
        orig_ids = set(x[2] for x in orig_xml)
        fixed_ids = set(x[2] for x in fixed_xml)

        dropped = orig_ids - fixed_ids
        added = fixed_ids - orig_ids
        if dropped:
            print(f"  Slide {slide_num}: DROPPED shapes: {dropped}")
        if added:
            print(f"  Slide {slide_num}: ADDED shapes: {added}")
        if len(orig_xml) != len(fixed_xml):
            print(f"  Slide {slide_num}: COUNT MISMATCH orig={len(orig_xml)} fixed={len(fixed_xml)}")


if __name__ == "__main__":
    main()
