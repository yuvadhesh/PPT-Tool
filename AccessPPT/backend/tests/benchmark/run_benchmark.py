"""
Benchmark Runner for PowerPoint Reading Order Algorithm.
Evaluates accuracy across the benchmark suite:
- Exact-match rate (% and count)
- Normalized Kendall-Tau distance
- Pairwise-order accuracy
- Manual Review count
- Failure count & detailed reasons
"""
import os
import sys
import json
import tempfile
from pathlib import Path
from typing import List, Tuple
import pptx

# Add backend to path
BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.reading_order_service import reading_order_service


def compute_pairwise_accuracy(expected: List[str], produced: List[str]) -> Tuple[float, float]:
    """
    Computes pairwise accuracy and normalized Kendall-tau distance between two permutations.
    Returns (pairwise_accuracy, kendall_tau_distance).
    """
    if len(expected) <= 1:
        return 1.0, 0.0

    # Common items only
    items = [x for x in expected if x in produced]
    n = len(items)
    if n <= 1:
        return 1.0, 0.0

    exp_pos = {item: i for i, item in enumerate(expected)}
    prod_pos = {item: i for i, item in enumerate(produced)}

    concordant = 0
    discordant = 0
    total_pairs = n * (n - 1) // 2

    for i in range(n):
        for j in range(i + 1, n):
            u, v = items[i], items[j]
            exp_order = exp_pos[u] < exp_pos[v]
            prod_order = prod_pos[u] < prod_pos[v]
            if exp_order == prod_order:
                concordant += 1
            else:
                discordant += 1

    pairwise_acc = concordant / total_pairs if total_pairs > 0 else 1.0
    kendall_tau_dist = discordant / total_pairs if total_pairs > 0 else 0.0
    return round(pairwise_acc, 4), round(kendall_tau_dist, 4)


def run_benchmark(verbose: bool = True) -> dict:
    decks_dir = Path(__file__).resolve().parent / "decks"
    case_files = sorted(decks_dir.glob("*_expected.json"))

    if not case_files:
        print("No benchmark cases found. Please run generate_benchmark_decks.py first.")
        return {}

    total_cases = len(case_files)
    exact_matches = 0
    manual_reviews = 0
    failures = 0
    total_pairwise = 0.0
    total_kendall = 0.0

    results_table = []

    print(f"\n=======================================================")
    print(f"       RUNNING BENCHMARK ACROSS {total_cases} CASES")
    print(f"=======================================================\n")

    for meta_file in case_files:
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)

        case_name = meta["case_name"]
        expected_order = meta["expected_order"]
        deck_path = decks_dir / f"{case_name}.pptx"

        with tempfile.TemporaryDirectory() as tmp_dir:
            fixed_deck = Path(tmp_dir) / f"{case_name}_fixed.pptx"

            try:
                res = reading_order_service.fix_presentation_reading_order(
                    str(deck_path), str(fixed_deck), use_ai_fallback=False
                )

                # Reopen fixed deck and get actual shape sequence names
                prs_fixed = pptx.Presentation(str(fixed_deck))
                slide0 = prs_fixed.slides[0]
                produced_order = [s.name for s in slide0.shapes]

                # Check manual review status
                slide_status = res["slides"][0]["status"] if res["slides"] else "unknown"
                is_manual_review = (slide_status == "manual_review")

                is_exact = (produced_order == expected_order)
                if is_exact:
                    exact_matches += 1
                    status_str = "EXACT MATCH"
                elif is_manual_review:
                    manual_reviews += 1
                    status_str = "MANUAL REVIEW"
                else:
                    failures += 1
                    status_str = "MISMATCH"

                pair_acc, kendall_d = compute_pairwise_accuracy(expected_order, produced_order)
                total_pairwise += pair_acc
                total_kendall += kendall_d

                diff_reason = None
                if not is_exact:
                    if len(expected_order) != len(produced_order):
                        diff_reason = f"Count mismatch: expected {len(expected_order)}, got {len(produced_order)}"
                    elif set(expected_order) != set(produced_order):
                        diff_reason = f"Set mismatch: missing {set(expected_order) - set(produced_order)}"
                    else:
                        first_diff = next(
                            (f"pos {idx}: exp '{e}' != got '{g}'" for idx, (e, g) in enumerate(zip(expected_order, produced_order)) if e != g),
                            "order discrepancy"
                        )
                        diff_reason = first_diff

                results_table.append({
                    "case_name": case_name,
                    "status": status_str,
                    "exact": is_exact,
                    "pairwise_acc": pair_acc,
                    "kendall_dist": kendall_d,
                    "expected": expected_order,
                    "produced": produced_order,
                    "reason": diff_reason or ("Safe manual review" if is_manual_review else "OK"),
                })

            except Exception as e:
                failures += 1
                results_table.append({
                    "case_name": case_name,
                    "status": "ERROR",
                    "exact": False,
                    "pairwise_acc": 0.0,
                    "kendall_dist": 1.0,
                    "expected": expected_order,
                    "produced": [],
                    "reason": str(e),
                })

    # Summary metrics
    exact_rate = round((exact_matches / total_cases) * 100, 2)
    avg_pairwise = round((total_pairwise / total_cases) * 100, 2)
    avg_kendall = round(total_kendall / total_cases, 4)

    print(f"{'Case Name':<35} | {'Status':<14} | {'Pairwise':<9} | Reason")
    print("-" * 90)
    for r in results_table:
        print(f"{r['case_name']:<35} | {r['status']:<14} | {r['pairwise_acc']*100:>6.1f}%   | {r['reason']}")

    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY METRICS:")
    print("=" * 60)
    print(f"Total Test Cases       : {total_cases}")
    print(f"Exact Matches          : {exact_matches} ({exact_rate}%)")
    print(f"Manual Reviews         : {manual_reviews}")
    print(f"Failures (Mismatches)  : {failures}")
    print(f"Mean Pairwise Accuracy : {avg_pairwise}%")
    print(f"Mean Kendall-Tau Dist  : {avg_kendall}")
    print("=" * 60)

    return {
        "total_cases": total_cases,
        "exact_matches": exact_matches,
        "exact_rate": exact_rate,
        "manual_reviews": manual_reviews,
        "failures": failures,
        "avg_pairwise": avg_pairwise,
        "avg_kendall": avg_kendall,
        "table": results_table,
    }


if __name__ == "__main__":
    run_benchmark()
