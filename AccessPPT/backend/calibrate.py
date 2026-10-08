#!/usr/bin/env python3
"""
calibrate.py - Calibration Tool & PowerPoint Accessibility Flag Emulator

Extracts comprehensive geometric, structural, and semantic features per slide
from a PowerPoint presentation, correlates with ground-truth flags from PowerPoint's
built-in Accessibility Assistant ("Check reading order"), learns the simplest decision rule,
and outputs pptx_checker_model.py ("PowerPointFlagEmulator").

Usage:
  python calibrate.py --pptx before_reorder_slide4.pptx --flags flagged_slides.json
  python calibrate.py --update flagged_after.json
  python calibrate.py --predict fixed.pptx
"""

import os
import sys
import json
import csv
import argparse
from typing import List, Dict, Any, Tuple, Optional
import pptx
from pptx.enum.shapes import MSO_SHAPE_TYPE

# Import geometry helpers from backend service
from app.services.geometry_helpers import (
    resolve_placeholder_geometry,
    compute_rotated_bbox,
    detect_ooxml_element_type,
    is_shape_decorative,
)
from app.services.reading_order_config import (
    DEFAULT_SLIDE_WIDTH_EMU,
    DEFAULT_SLIDE_HEIGHT_EMU,
    Z_ORDER_OVERLAP_AREA_RATIO,
    BAND_TOLERANCE_RATIO,
)


def _get_shape_text(shape) -> str:
    try:
        if shape.has_text_frame:
            return "".join(p.text for p in shape.text_frame.paragraphs).strip()
    except Exception:
        pass
    return ""


def _get_group_depth(shape, current_depth: int = 1) -> int:
    if getattr(shape, "shape_type", None) == MSO_SHAPE_TYPE.GROUP or hasattr(shape, "shapes"):
        max_child_depth = current_depth
        for child in shape.shapes:
            child_depth = _get_group_depth(child, current_depth + 1)
            if child_depth > max_child_depth:
                max_child_depth = child_depth
        return max_child_depth
    return current_depth


def extract_slide_features(slide, slide_idx: int, slide_width: int, slide_height: int) -> Dict[str, Any]:
    slide_num = slide_idx + 1
    raw_shapes = list(slide.shapes)
    shape_count = len(raw_shapes)

    count_placeholder = 0
    count_textbox = 0
    count_picture = 0
    count_table = 0
    count_chart = 0
    count_group = 0
    count_connector = 0
    count_graphicFrame = 0
    count_alternateContent = 0

    empty_textboxes_count = 0
    shapes_no_alt_text_count = 0
    off_slide_shapes_count = 0
    rotated_shapes_count = 0
    max_group_nesting = 0

    shape_geoms = []

    for s in raw_shapes:
        s_type = detect_ooxml_element_type(s)
        if s_type == "placeholder":
            count_placeholder += 1
        elif s_type == "textbox":
            count_textbox += 1
        elif s_type == "picture":
            count_picture += 1
        elif s_type == "table":
            count_table += 1
        elif s_type == "chart":
            count_chart += 1
        elif s_type == "group":
            count_group += 1
            max_group_nesting = max(max_group_nesting, _get_group_depth(s))
        elif s_type == "connector":
            count_connector += 1
        elif s_type == "graphicFrame":
            count_graphicFrame += 1
        elif s_type == "AlternateContent":
            count_alternateContent += 1

        left, top, width, height, geom_src = resolve_placeholder_geometry(s, slide)
        rot = getattr(s, "rotation", 0) or 0
        if rot != 0:
            rotated_shapes_count += 1
            left, top, width, height = compute_rotated_bbox(left, top, width, height, int(rot * 60000))

        # Check off-slide
        if (left + width < 0 or top + height < 0 or left > slide_width or top > slide_height):
            off_slide_shapes_count += 1

        # Check empty textbox
        txt = _get_shape_text(s)
        if s_type in ("textbox", "placeholder") and not txt:
            empty_textboxes_count += 1

        # Check alt text
        alt_txt = ""
        try:
            alt_txt = (getattr(s, "description", None) or getattr(s, "alt_text", None) or "").strip()
        except Exception:
            pass
        is_dec = is_shape_decorative(s)
        if s_type in ("picture", "chart", "table", "graphicFrame") and not is_dec and not alt_txt:
            shapes_no_alt_text_count += 1

        ph_type = None
        if getattr(s, "is_placeholder", False):
            try:
                ph_type = s.placeholder_format.type
            except Exception:
                pass

        shape_geoms.append({
            "shape": s,
            "id": s.shape_id,
            "type": s_type,
            "left": left,
            "top": top,
            "width": width,
            "height": height,
            "text": txt,
            "is_ph": getattr(s, "is_placeholder", False),
            "ph_type": ph_type,
        })

    # 1. Overlapping shape pairs (intersection > 2% of smaller)
    overlapping_pairs = 0
    for i in range(shape_count):
        g1 = shape_geoms[i]
        for j in range(i + 1, shape_count):
            g2 = shape_geoms[j]
            ow = max(0, min(g1["left"] + g1["width"], g2["left"] + g2["width"]) - max(g1["left"], g2["left"]))
            oh = max(0, min(g1["top"] + g1["height"], g2["top"] + g2["height"]) - max(g1["top"], g2["top"]))
            o_area = ow * oh
            min_area = min(max(1, g1["width"] * g1["height"]), max(1, g2["width"] * g2["height"]))
            if o_area > Z_ORDER_OVERLAP_AREA_RATIO * min_area:
                overlapping_pairs += 1

    # 2. Visual reading order: top-to-bottom then left-to-right with tolerance
    band_tolerance = max(180000, int(slide_height * BAND_TOLERANCE_RATIO))
    # Sort key: band_row, left
    visual_sorted = sorted(
        shape_geoms,
        key=lambda g: (round(g["top"] / band_tolerance), g["left"], g["top"])
    )
    visual_rank = {g["id"]: idx for idx, g in enumerate(visual_sorted)}

    # 3. Inversions count: pairs (A, B) where A is before B in XML, but B is visually before A
    inversions_count = 0
    xml_ranks = [visual_rank[g["id"]] for g in shape_geoms]
    for i in range(len(xml_ranks)):
        for j in range(i + 1, len(xml_ranks)):
            if xml_ranks[i] > xml_ranks[j]:
                inversions_count += 1

    # Kendall-tau distance: inversions / max_pairs
    max_pairs = (shape_count * (shape_count - 1)) / 2 if shape_count > 1 else 1
    kendall_tau = round(inversions_count / max_pairs, 4)

    # 4. Title placeholder first in spTree?
    is_title_first = False
    non_ph_before_title = False
    title_idx = -1
    for idx, g in enumerate(shape_geoms):
        is_title = False
        if g["is_ph"] and g["ph_type"] in (1, 3):  # TITLE or CTR_TITLE
            is_title = True
        elif "title" in (getattr(g["shape"], "name", None) or "").lower() and g["text"]:
            is_title = True
        if is_title:
            title_idx = idx
            break

    if title_idx == 0:
        is_title_first = True
    elif title_idx > 0:
        for idx in range(title_idx):
            if not shape_geoms[idx]["is_ph"]:
                non_ph_before_title = True
                break

    return {
        "slide_number": slide_num,
        "shape_count": shape_count,
        "count_placeholder": count_placeholder,
        "count_textbox": count_textbox,
        "count_picture": count_picture,
        "count_table": count_table,
        "count_chart": count_chart,
        "count_group": count_group,
        "count_connector": count_connector,
        "count_graphicFrame": count_graphicFrame,
        "count_alternateContent": count_alternateContent,
        "overlapping_pairs": overlapping_pairs,
        "inversions": inversions_count,
        "kendall_tau": kendall_tau,
        "is_title_first": 1 if is_title_first else 0,
        "non_ph_before_title": 1 if non_ph_before_title else 0,
        "off_slide_shapes": off_slide_shapes_count,
        "empty_textboxes": empty_textboxes_count,
        "shapes_no_alt_text": shapes_no_alt_text_count,
        "max_group_depth": max_group_nesting,
        "rotated_shapes": rotated_shapes_count,
    }


class SimpleDecisionTree:
    """Pure-Python decision tree classifier (depth <= 3) for rule inference."""

    def __init__(self, max_depth: int = 3):
        self.max_depth = max_depth
        self.tree = None

    def fit(self, X: List[Dict[str, float]], y: List[int], feature_names: List[str]):
        self.feature_names = feature_names
        self.tree = self._build_node(X, y, depth=0)

    def _gini(self, y: List[int]) -> float:
        if not y:
            return 0.0
        p = sum(y) / len(y)
        return 2.0 * p * (1.0 - p)

    def _build_node(self, X: List[Dict[str, float]], y: List[int], depth: int) -> Dict[str, Any]:
        n_samples = len(y)
        n_pos = sum(y)
        pred = 1 if n_pos > (n_samples / 2) else 0

        # Base case
        if depth >= self.max_depth or n_pos == 0 or n_pos == n_samples or n_samples <= 2:
            return {"leaf": True, "pred": pred, "samples": n_samples, "pos": n_pos}

        best_gain = -1.0
        best_feat = None
        best_thresh = None
        best_left_idx = None
        best_right_idx = None

        parent_impurity = self._gini(y)

        for feat in self.feature_names:
            vals = sorted(list(set(row[feat] for row in X)))
            if len(vals) <= 1:
                continue

            # Try candidate midpoints
            for i in range(len(vals) - 1):
                thresh = (vals[i] + vals[i + 1]) / 2.0
                left_idx = [idx for idx, row in enumerate(X) if row[feat] <= thresh]
                right_idx = [idx for idx, row in enumerate(X) if row[feat] > thresh]

                if not left_idx or not right_idx:
                    continue

                y_left = [y[idx] for idx in left_idx]
                y_right = [y[idx] for idx in right_idx]

                impurity = (len(y_left) / n_samples) * self._gini(y_left) + (len(y_right) / n_samples) * self._gini(y_right)
                gain = parent_impurity - impurity

                if gain > best_gain:
                    best_gain = gain
                    best_feat = feat
                    best_thresh = thresh
                    best_left_idx = left_idx
                    best_right_idx = right_idx

        if best_gain <= 0.001 or best_feat is None:
            return {"leaf": True, "pred": pred, "samples": n_samples, "pos": n_pos}

        X_left = [X[i] for i in best_left_idx]
        y_left = [y[i] for i in best_left_idx]
        X_right = [X[i] for i in best_right_idx]
        y_right = [y[i] for i in best_right_idx]

        return {
            "leaf": False,
            "feature": best_feat,
            "threshold": round(best_thresh, 4),
            "left": self._build_node(X_left, y_left, depth + 1),
            "right": self._build_node(X_right, y_right, depth + 1),
            "samples": n_samples,
            "pos": n_pos,
        }

    def predict_one(self, row: Dict[str, float], node: Optional[Dict[str, Any]] = None) -> int:
        if node is None:
            node = self.tree
        if node["leaf"]:
            return node["pred"]
        if row[node["feature"]] <= node["threshold"]:
            return self.predict_one(row, node["left"])
        else:
            return self.predict_one(row, node["right"])

    def predict(self, X: List[Dict[str, float]]) -> List[int]:
        return [self.predict_one(row) for row in X]

    def to_code_rule(self, node: Optional[Dict[str, Any]] = None, indent: int = 4) -> str:
        if node is None:
            node = self.tree
        spaces = " " * indent
        if node["leaf"]:
            return f"{spaces}return {'True' if node['pred'] == 1 else 'False'}  # ({node['pos']}/{node['samples']} flagged)"
        feat = node["feature"]
        thresh = node["threshold"]
        left_code = self.to_code_rule(node["left"], indent + 4)
        right_code = self.to_code_rule(node["right"], indent + 4)
        return (
            f"{spaces}if features['{feat}'] <= {thresh}:\n"
            f"{left_code}\n"
            f"{spaces}else:\n"
            f"{right_code}"
        )


def evaluate_metrics(y_true: List[int], y_pred: List[int]) -> Dict[str, float]:
    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 1)
    tn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 0)
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 1)
    fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 0)

    acc = (tp + tn) / len(y_true) if y_true else 0.0
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

    return {
        "accuracy": round(acc, 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(f1, 4),
        "tp": tp, "tn": tn, "fp": fp, "fn": fn
    }


def generate_emulator_module(tree: SimpleDecisionTree, feature_names: List[str], metrics: Dict[str, float], output_path: str):
    code = f'''"""
pptx_checker_model.py - PowerPoint Accessibility Checker Flag Emulator

Auto-generated by calibrate.py.
Predicts whether Microsoft PowerPoint's Accessibility Assistant will raise
the "Check reading order" warning for a given slide.

Trained Performance:
  Precision: {metrics['precision'] * 100:.1f}%
  Recall   : {metrics['recall'] * 100:.1f}%
  Accuracy : {metrics['accuracy'] * 100:.1f}%
  F1 Score : {metrics['f1']:.3f}
"""

from typing import Dict, Any, List
import pptx


class PowerPointFlagEmulator:
    """
    Emulates Microsoft PowerPoint's 'Check reading order' inspection rule.
    Returns True if PowerPoint is predicted to flag the slide, False otherwise.
    """

    @staticmethod
    def predict_slide(features: Dict[str, Any]) -> bool:
        """Evaluate inferred decision tree rule on slide feature dictionary."""
{tree.to_code_rule(indent=8)}

    @classmethod
    def predict_presentation(cls, pptx_path: str) -> Dict[str, Any]:
        """Inspect all slides in a presentation and return predicted flagged slide indices."""
        from calibrate import extract_slide_features
        prs = pptx.Presentation(pptx_path)
        sw = prs.slide_width or 9144000
        sh = prs.slide_height or 5143500

        flagged_slides = []
        details = []
        for idx, slide in enumerate(prs.slides):
            feats = extract_slide_features(slide, idx, sw, sh)
            is_flagged = cls.predict_slide(feats)
            feats["predicted_flagged"] = is_flagged
            details.append(feats)
            if is_flagged:
                flagged_slides.append(idx + 1)

        return {{
            "pptx_path": pptx_path,
            "total_slides": len(prs.slides),
            "flagged_count": len(flagged_slides),
            "flagged_slides": flagged_slides,
            "details": details,
        }}
'''
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"\n[OK] Saved emulator module to: {output_path}")


def run_calibration(pptx_path: str, flags_path: Optional[str], csv_out: str, model_out: str):
    if not os.path.exists(pptx_path):
        print(f"[Error] PPTX not found: {pptx_path}")
        sys.exit(1)

    prs = pptx.Presentation(pptx_path)
    sw = prs.slide_width or DEFAULT_SLIDE_WIDTH_EMU
    sh = prs.slide_height or DEFAULT_SLIDE_HEIGHT_EMU
    total_slides = len(prs.slides)

    print(f"Loading presentation: {pptx_path} ({total_slides} slides)")

    flagged_set = set()
    if flags_path and os.path.exists(flags_path):
        with open(flags_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            flagged_set = set(data.get("flagged", []))
        print(f"Loaded ground-truth flags from {flags_path}: {len(flagged_set)} flagged slides")
    else:
        print(f"[Notice] No ground truth file found ({flags_path}). Generating feature matrix only.")

    rows = []
    for idx, slide in enumerate(prs.slides):
        feats = extract_slide_features(slide, idx, sw, sh)
        feats["flagged"] = 1 if (idx + 1) in flagged_set else 0
        rows.append(feats)

    # Save CSV
    if rows:
        fieldnames = list(rows[0].keys())
        with open(csv_out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[OK] Exported feature matrix to: {csv_out}")

    # Print summary table
    print("\nFeature Summary Table (First 15 Slides):")
    print(f"{'Slide':<6} | {'Shapes':<7} | {'Overlaps':<9} | {'Inversions':<11} | {'Kendall-Tau':<12} | {'Title 1st':<10} | {'Flagged':<8}")
    print("-" * 75)
    for r in rows[:15]:
        print(f"{r['slide_number']:<6} | {r['shape_count']:<7} | {r['overlapping_pairs']:<9} | {r['inversions']:<11} | {r['kendall_tau']:<12.3f} | {r['is_title_first']:<10} | {r['flagged']:<8}")

    if flagged_set:
        # Fit Decision Tree
        feature_cols = [
            "shape_count", "count_placeholder", "count_textbox", "count_picture",
            "count_table", "count_chart", "count_group", "overlapping_pairs",
            "inversions", "kendall_tau", "is_title_first", "non_ph_before_title",
            "off_slide_shapes", "empty_textboxes", "shapes_no_alt_text", "rotated_shapes"
        ]
        X = [{c: r[c] for c in feature_cols} for r in rows]
        y = [r["flagged"] for r in rows]

        tree = SimpleDecisionTree(max_depth=3)
        tree.fit(X, y, feature_cols)
        preds = tree.predict(X)
        metrics = evaluate_metrics(y, preds)

        print("\n" + "=" * 60)
        print("         CALIBRATION RESULTS (PowerPoint Flag Model)")
        print("=" * 60)
        print(f"Accuracy : {metrics['accuracy'] * 100:.1f}%")
        print(f"Precision: {metrics['precision'] * 100:.1f}%")
        print(f"Recall   : {metrics['recall'] * 100:.1f}%")
        print(f"F1-Score : {metrics['f1']:.3f}")
        print(f"Matrix   : TP={metrics['tp']}, TN={metrics['tn']}, FP={metrics['fp']}, FN={metrics['fn']}")
        print("\nInferred PowerPoint Rule Tree:")
        print(tree.to_code_rule())
        print("=" * 60)

        generate_emulator_module(tree, feature_cols, metrics, model_out)
    else:
        print("\nTo train the PowerPointFlagEmulator, provide flagged_slides.json with:")
        print('  {"flagged": [slide_numbers...], "not_flagged": [slide_numbers...]}')


def main():
    parser = argparse.ArgumentParser(description="Calibrate Reading Order against PowerPoint flags.")
    parser.add_argument("--pptx", default="before_reorder_slide4.pptx", help="Path to input presentation")
    parser.add_argument("--flags", default="flagged_slides.json", help="Path to flagged_slides.json")
    parser.add_argument("--output-csv", default="calibration_features.csv", help="Path to output feature CSV")
    parser.add_argument("--model-out", default="app/services/pptx_checker_model.py", help="Output model python path")
    parser.add_argument("--predict", help="Predict PowerPoint flags on a specified PPTX")
    parser.add_argument("--update", help="Update emulator model with flagged_after.json")

    args = parser.parse_args()

    if args.predict:
        from app.services.pptx_checker_model import PowerPointFlagEmulator
        res = PowerPointFlagEmulator.predict_presentation(args.predict)
        print(f"\nPredictions for {args.predict}:")
        print(f"Total slides  : {res['total_slides']}")
        print(f"Flagged slides: {res['flagged_count']} -> {res['flagged_slides']}")
        return

    if args.update:
        run_calibration(args.pptx, args.update, args.output_csv, args.model_out)
        return

    run_calibration(args.pptx, args.flags, args.output_csv, args.model_out)


if __name__ == "__main__":
    main()
