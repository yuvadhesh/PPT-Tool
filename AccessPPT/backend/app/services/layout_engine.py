"""
Recursive XY-Cut Page Segmentation Layout Engine and Z-Order Topological Safety.

Implements STEP 2 and STEP 3 of the Benchmark-Driven Reading Order Specification:
1. Recursive XY-Cut (Page Segmentation):
   - Canonical initial sorting ensuring 100% idempotency across re-evaluations.
   - Horizontal cuts find whitespace gaps (no object's [y, y+h] overlaps) > gap_threshold.
   - Vertical cuts find whitespace gaps (no object's [x, x+w] overlaps) > gap_threshold.
   - RTL presentation detection orders vertical columns Right -> Left.
   - Spanning items (> 60% region width) treated as full-width bands (top, middle, bottom segmentation).
   - Gluing rules: Captions glued to parent media; Headings glued to bodies below; Containers glued to contents.
   - Atomic units: Groups, tables, charts, SmartArt, AlternateContent.
   - Grid alignment scoring: Row vs Column alignment consistency.
2. Z-Order Topological Safety:
   - Detects visual overlap (> 2% area).
   - Generates directed constraints: background containers must precede foreground content.
   - Resolves via topological sorting.
   - Flags circular contradictions as "Manual Review" with specific conflicting objects.
"""
from typing import List, Dict, Any, Optional, Tuple, Set
import math
from app.core.logging import logger
from app.services.reading_order_config import (
    GAP_THRESHOLD_HORIZONTAL,
    GAP_THRESHOLD_VERTICAL,
    SPANNING_WIDTH_RATIO,
    BAND_TOLERANCE_RATIO,
    CAPTION_MAX_WIDTH_RATIO,
    CAPTION_MAX_GAP_RATIO,
    CAPTION_HORIZONTAL_OVERLAP,
    CAPTION_MAX_TEXT_LEN,
    HEADING_BODY_X_OVERLAP,
    HEADING_BODY_MAX_GAP_RATIO,
    GRID_ALIGNMENT_AMBIGUITY_THRESHOLD,
    Z_ORDER_OVERLAP_AREA_RATIO,
    CONTAINER_CONTAINMENT_RATIO,
    DEFAULT_SLIDE_WIDTH_EMU,
    DEFAULT_SLIDE_HEIGHT_EMU,
)


class CompositeUnit:
    """Represents an atomic glued group of objects (e.g. Media+Caption, Heading+Body, Container+Content)."""
    def __init__(self, primary_obj: Dict[str, Any]):
        self.members: List[Dict[str, Any]] = [primary_obj]
        self.primary_id = primary_obj["shape_id"]
        self.unit_type = primary_obj.get("semantic_role", "unknown")
        self._update_bbox()

    def add_member(self, obj: Dict[str, Any], place_before: bool = False):
        if place_before:
            self.members.insert(0, obj)
        else:
            self.members.append(obj)
        self._update_bbox()

    def _update_bbox(self):
        min_l = min(m["left_emu"] for m in self.members)
        min_t = min(m["top_emu"] for m in self.members)
        max_r = max(m["left_emu"] + m["width_emu"] for m in self.members)
        max_b = max(m["top_emu"] + m["height_emu"] for m in self.members)
        self.left_emu = min_l
        self.top_emu = min_t
        self.width_emu = max_r - min_l
        self.height_emu = max_b - min_t
        self.center_x = min_l + self.width_emu / 2.0
        self.center_y = min_t + self.height_emu / 2.0


def glue_relationships(
    items: List[Dict[str, Any]], slide_width: int, slide_height: int
) -> List[CompositeUnit]:
    """
    Glues related shapes into atomic units:
    1. Background containers + contained contents.
    2. Picture/Chart/Table + Caption (caption directly above or below).
    3. Heading + Body directly below it.
    4. Standalone shapes remain single-member composite units.
    Ensures 100% deterministic, idempotent grouping.
    """
    # Canonical sorting at start ensures idempotency
    sorted_items = sorted(items, key=lambda o: (o["top_emu"], o["left_emu"], o["shape_id"]))
    assigned_ids: Set[int] = set()
    units: List[CompositeUnit] = []

    media_roles = ("image", "table", "chart", "smart_art")
    heading_roles = ("heading", "subtitle")

    # 1. Background Container + Contained items gluing (simple shapes only, not groups)
    for item in sorted_items:
        if item["shape_id"] in assigned_ids:
            continue
        if item["semantic_role"] == "container" and item.get("xml_element_type") != "grpSp":
            unit = CompositeUnit(item)
            assigned_ids.add(item["shape_id"])
            c_l = item["left_emu"]
            c_t = item["top_emu"]
            c_w = max(1, item["width_emu"])
            c_h = max(1, item["height_emu"])
            c_r = c_l + c_w
            c_b = c_t + c_h

            for other in sorted_items:
                if other["shape_id"] in assigned_ids:
                    continue
                o_l = other["left_emu"]
                o_t = other["top_emu"]
                o_w = max(1, other["width_emu"])
                o_h = max(1, other["height_emu"])
                o_r = o_l + o_w
                o_b = o_t + o_h
                overlap = max(0, min(c_r, o_r) - max(c_l, o_l)) * max(0, min(c_b, o_b) - max(c_t, o_t))
                if overlap > 0.60 * (o_w * o_h):
                    unit.add_member(other, place_before=False)
                    assigned_ids.add(other["shape_id"])
            units.append(unit)

    # 2. Media + Caption gluing
    for item in sorted_items:
        if item["shape_id"] in assigned_ids:
            continue
        if item["semantic_role"] in media_roles:
            unit = CompositeUnit(item)
            assigned_ids.add(item["shape_id"])

            m_l = item["left_emu"]
            m_t = item["top_emu"]
            m_w = max(1, item["width_emu"])
            m_h = max(1, item["height_emu"])
            m_r = m_l + m_w
            m_b = m_t + m_h

            best_caption = None
            is_above = False
            best_dist = float("inf")

            for other in sorted_items:
                if other["shape_id"] in assigned_ids:
                    continue
                o_role = other["semantic_role"]
                o_text = (other.get("text_content") or "").strip()
                o_name = (other.get("name") or "").lower()

                if len(o_text) > CAPTION_MAX_TEXT_LEN:
                    continue
                if o_role not in ("caption", "body_text", "shape") and not o_name.startswith("caption"):
                    continue

                o_l = other["left_emu"]
                o_t = other["top_emu"]
                o_w = max(1, other["width_emu"])
                o_h = max(1, other["height_emu"])
                o_r = o_l + o_w
                o_b = o_t + o_h

                if o_w > m_w * CAPTION_MAX_WIDTH_RATIO:
                    continue

                overlap = min(m_r, o_r) - max(m_l, o_l)
                if overlap < CAPTION_HORIZONTAL_OVERLAP * min(m_w, o_w):
                    continue

                gap_below = o_t - m_b
                if 0 <= gap_below <= (slide_height * CAPTION_MAX_GAP_RATIO):
                    if gap_below < best_dist:
                        best_dist = gap_below
                        best_caption = other
                        is_above = False

                gap_above = m_t - o_b
                if 0 <= gap_above <= (slide_height * CAPTION_MAX_GAP_RATIO):
                    if gap_above < best_dist:
                        best_dist = gap_above
                        best_caption = other
                        is_above = True

            if best_caption:
                best_caption["semantic_role"] = "caption"
                best_caption["object_type"] = "Caption"
                unit.add_member(best_caption, place_before=is_above)
                assigned_ids.add(best_caption["shape_id"])

            units.append(unit)

    # 3. Heading + Body gluing
    for item in sorted_items:
        if item["shape_id"] in assigned_ids:
            continue
        if item["semantic_role"] in heading_roles:
            unit = CompositeUnit(item)
            assigned_ids.add(item["shape_id"])

            h_l = item["left_emu"]
            h_t = item["top_emu"]
            h_w = max(1, item["width_emu"])
            h_h = max(1, item["height_emu"])
            h_r = h_l + h_w
            h_b = h_t + h_h

            best_body = None
            best_dist = float("inf")

            for other in sorted_items:
                if other["shape_id"] in assigned_ids:
                    continue
                if other["semantic_role"] not in ("body_text", "list"):
                    continue

                o_l = other["left_emu"]
                o_t = other["top_emu"]
                o_w = max(1, other["width_emu"])
                o_h = max(1, other["height_emu"])
                o_r = o_l + o_w

                # Spanning bodies are not column-specific children of narrow headings
                if o_w > SPANNING_WIDTH_RATIO * slide_width and h_w < SPANNING_WIDTH_RATIO * slide_width:
                    continue

                overlap = min(h_r, o_r) - max(h_l, o_l)
                if overlap < HEADING_BODY_X_OVERLAP * min(h_w, o_w) or overlap < 0.30 * max(h_w, o_w):
                    continue

                gap = o_t - h_b
                if 0 <= gap <= (slide_height * HEADING_BODY_MAX_GAP_RATIO):
                    if gap < best_dist:
                        best_dist = gap
                        best_body = other

            if best_body:
                unit.add_member(best_body, place_before=False)
                assigned_ids.add(best_body["shape_id"])

            units.append(unit)

    # 4. All remaining items
    for item in sorted_items:
        if item["shape_id"] not in assigned_ids:
            unit = CompositeUnit(item)
            assigned_ids.add(item["shape_id"])
            units.append(unit)

    return units


def _find_horizontal_cuts(
    units: List[CompositeUnit], gap_threshold_emu: int
) -> List[Tuple[float, float]]:
    """Finds horizontal whitespace gaps across current region."""
    if len(units) < 2:
        return []

    intervals = sorted([(u.top_emu, u.top_emu + u.height_emu) for u in units], key=lambda x: x[0])
    merged = []
    for start, end in intervals:
        if not merged:
            merged.append((start, end))
        else:
            prev_s, prev_e = merged[-1]
            if start < prev_e:
                merged[-1] = (prev_s, max(prev_e, end))
            else:
                merged.append((start, end))

    cuts = []
    for i in range(len(merged) - 1):
        gap = merged[i+1][0] - merged[i][1]
        if gap >= gap_threshold_emu:
            split_y = merged[i][1] + gap / 2.0
            cuts.append(split_y)

    return cuts


def _find_vertical_cuts(
    units: List[CompositeUnit], gap_threshold_emu: int
) -> List[Tuple[float, float]]:
    """Finds vertical whitespace gaps across current region."""
    if len(units) < 2:
        return []

    intervals = sorted([(u.left_emu, u.left_emu + u.width_emu) for u in units], key=lambda x: x[0])
    merged = []
    for start, end in intervals:
        if not merged:
            merged.append((start, end))
        else:
            prev_s, prev_e = merged[-1]
            if start < prev_e:
                merged[-1] = (prev_s, max(prev_e, end))
            else:
                merged.append((start, end))

    cuts = []
    for i in range(len(merged) - 1):
        gap = merged[i+1][0] - merged[i][1]
        if gap >= gap_threshold_emu:
            split_x = merged[i][1] + gap / 2.0
            cuts.append(split_x)

    return cuts


def compute_grid_alignment_scores(units: List[CompositeUnit]) -> Tuple[float, float]:
    """Computes row alignment consistency vs column alignment consistency for grids."""
    if len(units) < 4:
        return 0.5, 0.5

    tops = [u.top_emu for u in units]
    lefts = [u.left_emu for u in units]

    row_clusters = []
    for t in sorted(tops):
        matched = False
        for c in row_clusters:
            if abs(t - sum(c)/len(c)) < 300000:
                c.append(t)
                matched = True
                break
        if not matched:
            row_clusters.append([t])

    col_clusters = []
    for l in sorted(lefts):
        matched = False
        for c in col_clusters:
            if abs(l - sum(c)/len(c)) < 300000:
                c.append(l)
                matched = True
                break
        if not matched:
            col_clusters.append([l])

    row_score = sum(len(c) for c in row_clusters if len(c) > 1) / len(units)
    col_score = sum(len(c) for c in col_clusters if len(c) > 1) / len(units)
    return row_score, col_score


def recursive_xy_cut(
    units: List[CompositeUnit],
    region: Tuple[int, int, int, int],
    slide_width: int,
    slide_height: int,
    is_rtl: bool = False,
    depth: int = 0,
) -> List[CompositeUnit]:
    """
    STEP 2: Recursive XY-Cut Algorithm.
    Decomposes region via alternating Horizontal and Vertical cuts.
    """
    if len(units) <= 1:
        return list(units)

    r_left, r_top, r_width, r_height = region

    # 1. Spanning elements detection across region (> 60% of region width)
    spanning = [u for u in units if u.width_emu > SPANNING_WIDTH_RATIO * r_width]
    non_spanning = [u for u in units if u not in spanning]

    if spanning and non_spanning:
        min_non_span_top = min(u.top_emu for u in non_spanning)
        max_non_span_bot = max(u.top_emu + u.height_emu for u in non_spanning)

        top_spanning = [u for u in spanning if (u.top_emu + u.height_emu) <= min_non_span_top]
        bottom_spanning = [u for u in spanning if u.top_emu >= max_non_span_bot]
        mid_spanning = [u for u in spanning if u not in top_spanning and u not in bottom_spanning]

        res = []
        if top_spanning:
            res.extend(sorted(top_spanning, key=lambda u: (u.top_emu, u.left_emu, u.primary_id)))

        if non_spanning:
            ns_region = (
                min(u.left_emu for u in non_spanning),
                min_non_span_top,
                max(u.left_emu + u.width_emu for u in non_spanning) - min(u.left_emu for u in non_spanning),
                max_non_span_bot - min_non_span_top,
            )
            res.extend(recursive_xy_cut(non_spanning, ns_region, slide_width, slide_height, is_rtl, depth+1))

        if mid_spanning:
            res.extend(sorted(mid_spanning, key=lambda u: (u.top_emu, u.left_emu, u.primary_id)))

        if bottom_spanning:
            res.extend(sorted(bottom_spanning, key=lambda u: (u.top_emu, u.left_emu, u.primary_id)))

        return res

    # 2. Try HORIZONTAL cut
    gap_h_emu = max(80000, int(slide_height * GAP_THRESHOLD_HORIZONTAL))
    h_cuts = _find_horizontal_cuts(units, gap_h_emu)
    if h_cuts:
        bands = []
        cuts_with_bounds = h_cuts + [r_top + r_height + 1000000]

        remaining_units = sorted(units, key=lambda u: (u.top_emu, u.left_emu, u.primary_id))
        for cut_y in cuts_with_bounds:
            band_units = [u for u in remaining_units if u.top_emu + u.height_emu / 2.0 < cut_y]
            if band_units:
                for bu in band_units:
                    remaining_units.remove(bu)
                bands.append(band_units)
        if remaining_units:
            bands.append(remaining_units)

        ordered = []
        for band in bands:
            ordered.extend(recursive_xy_cut(band, (r_left, min(u.top_emu for u in band), r_width, max(u.top_emu + u.height_emu for u in band) - min(u.top_emu for u in band)), slide_width, slide_height, is_rtl, depth+1))
        return ordered

    # 3. Else try VERTICAL cut
    gap_v_emu = max(80000, int(slide_width * GAP_THRESHOLD_VERTICAL))
    v_cuts = _find_vertical_cuts(units, gap_v_emu)
    if v_cuts:
        columns = []
        cuts_with_bounds = v_cuts + [r_left + r_width + 1000000]
        remaining_units = sorted(units, key=lambda u: (u.left_emu, u.top_emu, u.primary_id))
        for cut_x in cuts_with_bounds:
            col_units = [u for u in remaining_units if u.left_emu + u.width_emu / 2.0 < cut_x]
            if col_units:
                for cu in col_units:
                    remaining_units.remove(cu)
                columns.append(col_units)
        if remaining_units:
            columns.append(remaining_units)

        if is_rtl:
            columns.reverse()

        ordered = []
        for col in columns:
            ordered.extend(recursive_xy_cut(col, (min(u.left_emu for u in col), r_top, max(u.left_emu + u.width_emu for u in col) - min(u.left_emu for u in col), r_height), slide_width, slide_height, is_rtl, depth+1))
        return ordered

    # 4. Dense cluster / Grid alignment fallback (Strictly deterministic with tie-breakers)
    row_score, col_score = compute_grid_alignment_scores(units)
    band_size = max(200000, int(slide_height * BAND_TOLERANCE_RATIO))

    if row_score > col_score and (row_score - col_score) >= GRID_ALIGNMENT_AMBIGUITY_THRESHOLD:
        return sorted(units, key=lambda u: (round(u.top_emu / band_size), -u.left_emu if is_rtl else u.left_emu, u.top_emu, u.primary_id))
    elif col_score > row_score and (col_score - row_score) >= GRID_ALIGNMENT_AMBIGUITY_THRESHOLD:
        band_x = max(200000, int(slide_width * BAND_TOLERANCE_RATIO))
        return sorted(units, key=lambda u: (round((-u.left_emu if is_rtl else u.left_emu) / band_x), u.top_emu, u.primary_id))

    return sorted(units, key=lambda u: (round(u.top_emu / band_size), -u.left_emu if is_rtl else u.left_emu, u.top_emu, u.primary_id))


def _is_shape_visible(shape) -> bool:
    """Helper to detect if a shape has visible content (text, media, fill, or line)."""
    try:
        if getattr(shape, "has_text_frame", False):
            if any(p.text.strip() for p in shape.text_frame.paragraphs):
                return True
        if getattr(shape, "has_table", False) or getattr(shape, "has_chart", False):
            return True
        elem = getattr(shape, "_element", shape)
        tag = getattr(elem, "tag", "")
        if any(tag.endswith(t) for t in ("pic", "graphicFrame", "grpSp")):
            return True
        # Check fill and line in spPr
        for child in elem.iter():
            if child.tag.endswith("spPr"):
                if any(c.tag.endswith(("solidFill", "gradFill", "blipFill", "pattFill", "ln")) for c in child):
                    if not any(c.tag.endswith("noFill") for c in child):
                        return True
    except Exception:
        pass
    return False


def enforce_z_order_topological_sort(
    slide,
    recommended_sequence: List[Dict[str, Any]],
    primary_title_id: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], bool, Optional[str]]:
    """
    STEP 3 & 4: Z-Order Overlap Safety via Topological Sorting.
    Enforces Z-edges for every visible overlapping pair (intersection > 2% of smaller shape)
    where shape A was below shape B in original XML.
    Returns (adjusted_sequence, is_safe, reason).
    """
    raw_shapes = {s.shape_id: s for s in slide.shapes}
    shapes_list = list(slide.shapes)
    n = len(shapes_list)

    must_precede: Dict[int, Set[int]] = {o["shape_id"]: set() for o in recommended_sequence}

    for i in range(n):
        s1 = shapes_list[i]
        for j in range(i + 1, n):
            s2 = shapes_list[j]

            if primary_title_id is not None and (s1.shape_id == primary_title_id or s2.shape_id == primary_title_id):
                continue

            l1, t1, w1, h1 = getattr(s1, "left", 0) or 0, getattr(s1, "top", 0) or 0, getattr(s1, "width", 0) or 0, getattr(s1, "height", 0) or 0
            l2, t2, w2, h2 = getattr(s2, "left", 0) or 0, getattr(s2, "top", 0) or 0, getattr(s2, "width", 0) or 0, getattr(s2, "height", 0) or 0

            overlap_w = max(0, min(l1 + w1, l2 + w2) - max(l1, l2))
            overlap_h = max(0, min(t1 + h1, t2 + h2) - max(t1, t2))
            overlap_area = overlap_w * overlap_h
            area1 = max(1, w1 * h1)
            area2 = max(1, w2 * h2)
            min_area = min(area1, area2)

            if overlap_area > Z_ORDER_OVERLAP_AREA_RATIO * min_area:
                s1_text = ""
                s2_text = ""
                try:
                    if s1.has_text_frame:
                        s1_text = "".join(p.text for p in s1.text_frame.paragraphs).strip()
                    if s2.has_text_frame:
                        s2_text = "".join(p.text for p in s2.text_frame.paragraphs).strip()
                except Exception:
                    pass

                # Container background detection
                if area1 > area2 and overlap_area > CONTAINER_CONTAINMENT_RATIO * area2:
                    if not s1_text or "card" in (s1.name or "").lower():
                        if s1.shape_id in must_precede and s2.shape_id in must_precede:
                            must_precede[s1.shape_id].add(s2.shape_id)
                elif area2 > area1 and overlap_area > CONTAINER_CONTAINMENT_RATIO * area1:
                    if not s2_text or "card" in (s2.name or "").lower():
                        if s1.shape_id in must_precede and s2.shape_id in must_precede:
                            must_precede[s2.shape_id].add(s1.shape_id)
                elif s1_text and s2_text:
                    # Both visible text shapes overlapping (e.g. callout/highlight over text)
                    if s1.shape_id in must_precede and s2.shape_id in must_precede:
                        must_precede[s1.shape_id].add(s2.shape_id)

    # Topological sort preserving recommended order priority
    rec_priority = {o["shape_id"]: idx for idx, o in enumerate(recommended_sequence)}
    in_degrees = {sid: 0 for sid in must_precede}
    for sid, targets in must_precede.items():
        for t in targets:
            in_degrees[t] += 1

    ready = [sid for sid, deg in in_degrees.items() if deg == 0]
    ready.sort(key=lambda x: rec_priority.get(x, 9999))

    sorted_ids = []
    while ready:
        curr = ready.pop(0)
        sorted_ids.append(curr)
        for nxt in must_precede.get(curr, []):
            in_degrees[nxt] -= 1
            if in_degrees[nxt] == 0:
                ready.append(nxt)
                ready.sort(key=lambda x: rec_priority.get(x, 9999))

    if len(sorted_ids) != len(recommended_sequence):
        cycle_sids = [sid for sid, deg in in_degrees.items() if deg > 0]
        cycle_names = [raw_shapes[sid].name for sid in cycle_sids if sid in raw_shapes]
        conflict_msg = f"Circular visual overlap conflict between shapes: {', '.join(cycle_names)}"
        return recommended_sequence, False, conflict_msg

    id_to_obj = {o["shape_id"]: o for o in recommended_sequence}
    sorted_sequence = [id_to_obj[sid] for sid in sorted_ids if sid in id_to_obj]

    return sorted_sequence, True, None
