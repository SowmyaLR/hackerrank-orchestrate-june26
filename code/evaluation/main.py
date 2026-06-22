"""
Evaluation script: runs the pipeline on sample_claims.csv and compares
predicted outputs against expected (labeled) outputs.

Usage:
    GOOGLE_API_KEY=your_key python code/evaluation/main.py
"""
import csv
import os
import sys
import time
from pathlib import Path
import json
import argparse
from dotenv import load_dotenv

# Load env variables
load_dotenv()

# Ensure code/ is on the path
EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(EVAL_DIR)
sys.path.insert(0, CODE_DIR)

from utils.data_loader import (
    load_claims,
    load_user_history,
    load_evidence_requirements,
    load_images,
)
from utils.output_writer import write_output
from agents.claim_parser import parse_claim
from agents.image_analyst import analyze_images
from agents.evidence_checker import get_requirement, check_evidence_met
from agents.risk_assessor import assess_risk
from agents.verdict_aggregator import aggregate
from rules import OUTPUT_COLUMNS

# Import the process_claim function from main
sys.path.insert(0, os.path.dirname(CODE_DIR))

INTER_CALL_SLEEP = 4


def process_claim_for_eval(row, user_history, evidence_requirements, base_dir, idx):
    """Process a single claim — same logic as main.py."""
    user_id = row["user_id"]
    claim_object = row["claim_object"]
    user_claim = row["user_claim"]
    image_paths_str = row["image_paths"]

    print(f"\n[{idx:03d}] Evaluating user={user_id} object={claim_object}")

    # Step 1: Parse claim
    claim_parse = parse_claim(user_claim, claim_object)
    print(f"  [DEBUG] Raw claim_parser output:\n{json.dumps(claim_parse, indent=2)}")
    time.sleep(INTER_CALL_SLEEP)

    # Step 2: Get evidence requirement
    issue_family = claim_parse.get("issue_family", "other")
    requirement_text = get_requirement(
        evidence_requirements, claim_object, issue_family
    )

    # Step 3: Load images
    images = load_images(image_paths_str, base_dir)

    # Step 4: Vision analysis
    claimed_parts = claim_parse.get("claimed_parts", ["unknown"])
    primary_part = claimed_parts[0] if claimed_parts else "unknown"
    extracted_claim = claim_parse.get("extracted_claim", user_claim[:200])
    if claim_parse.get("injection_detected", False):
        extracted_claim = claim_parse.get("sanitised_claim", extracted_claim)

    vision_result = analyze_images(
        claim_object=claim_object,
        extracted_claim=extracted_claim,
        claimed_part=primary_part,
        all_claimed_parts=claimed_parts,
        evidence_requirement=requirement_text,
        image_paths=[img[1] for img in images],
        image_ids=[img[0] for img in images]
    )
    print(f"  [DEBUG] Raw image_analyst output:\n{json.dumps(vision_result, indent=2)}")
    time.sleep(INTER_CALL_SLEEP)

    # Step 5: Evidence check
    evidence_met, evidence_reason = check_evidence_met(
        vision_result, claim_object, issue_family, evidence_requirements
    )

    # Step 6: Risk assessment
    user_hist = user_history.get(user_id)
    history_risk_flags = assess_risk(user_hist)

    # Step 7: Aggregate
    output_row = aggregate(
        input_row=row,
        claim_parse=claim_parse,
        vision_result=vision_result,
        evidence_met=evidence_met,
        evidence_reason=evidence_reason,
        history_risk_flags=history_risk_flags,
    )

    return output_row


def compute_metrics(predicted_rows, expected_rows):
    """Compare predicted vs expected and compute per-field accuracy."""
    fields_to_compare = [
        "claim_status",
        "issue_type",
        "object_part",
        "severity",
        "evidence_standard_met",
        "valid_image",
    ]

    results = {field: {"correct": 0, "total": 0, "mismatches": []} for field in fields_to_compare}

    for i, (pred, expected) in enumerate(zip(predicted_rows, expected_rows)):
        for field in fields_to_compare:
            pred_val = str(pred.get(field, "")).strip().lower()
            exp_val = str(expected.get(field, "")).strip().lower()
            results[field]["total"] += 1
            if pred_val == exp_val:
                results[field]["correct"] += 1
            else:
                results[field]["mismatches"].append({
                    "row": i,
                    "user_id": expected.get("user_id", "?"),
                    "predicted": pred_val,
                    "expected": exp_val,
                })

    # Risk flags overlap (Jaccard similarity)
    risk_jaccard_sum = 0
    risk_count = 0
    for pred, expected in zip(predicted_rows, expected_rows):
        pred_flags = set(str(pred.get("risk_flags", "none")).split(";"))
        exp_flags = set(str(expected.get("risk_flags", "none")).split(";"))
        union = pred_flags | exp_flags
        intersection = pred_flags & exp_flags
        if union:
            risk_jaccard_sum += len(intersection) / len(union)
        risk_count += 1

    results["risk_flags_jaccard"] = risk_jaccard_sum / risk_count if risk_count else 0

    return results


def print_report(results):
    """Print a formatted evaluation report."""
    print("\n" + "=" * 70)
    print("EVALUATION RESULTS")
    print("=" * 70)

    for field in ["claim_status", "issue_type", "object_part", "severity",
                  "evidence_standard_met", "valid_image"]:
        data = results[field]
        accuracy = data["correct"] / data["total"] * 100 if data["total"] else 0
        print(f"\n{field}:")
        print(f"  Accuracy: {data['correct']}/{data['total']} ({accuracy:.1f}%)")
        if data["mismatches"]:
            print(f"  Mismatches ({len(data['mismatches'])}):")
            for m in data["mismatches"][:5]:  # Show first 5
                print(f"    Row {m['row']} ({m['user_id']}): "
                      f"predicted={m['predicted']}, expected={m['expected']}")
            if len(data["mismatches"]) > 5:
                print(f"    ... and {len(data['mismatches']) - 5} more")

    print(f"\nrisk_flags:")
    print(f"  Avg Jaccard similarity: {results['risk_flags_jaccard']:.3f}")

    # Overall score
    total_correct = sum(
        results[f]["correct"]
        for f in ["claim_status", "issue_type", "object_part",
                  "severity", "evidence_standard_met", "valid_image"]
    )
    total_fields = sum(
        results[f]["total"]
        for f in ["claim_status", "issue_type", "object_part",
                  "severity", "evidence_standard_met", "valid_image"]
    )
    overall = total_correct / total_fields * 100 if total_fields else 0
    print(f"\n{'=' * 70}")
    print(f"OVERALL FIELD ACCURACY: {total_correct}/{total_fields} ({overall:.1f}%)")
    print(f"RISK FLAGS JACCARD:     {results['risk_flags_jaccard']:.3f}")
    print(f"{'=' * 70}")


def main():
    """Run evaluation on sample_claims.csv."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Limit number of rows to evaluate")
    args = parser.parse_args()

    if not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY environment variable is not set.")
        sys.exit(1)

    project_root = Path(CODE_DIR).parent
    sample_path = project_root / "dataset" / "sample_claims.csv"
    history_path = project_root / "dataset" / "user_history.csv"
    evidence_path = project_root / "dataset" / "evidence_requirements.csv"
    eval_output_path = Path(EVAL_DIR) / "eval_output.csv"

    print("=" * 60)
    print("Evaluation: Running pipeline on sample_claims.csv")
    print("=" * 60)

    # Load data
    sample_claims = load_claims(str(sample_path))
    if args.limit is not None:
        print(f"Limiting evaluation to first {args.limit} rows.")
        sample_claims = sample_claims[:args.limit]
    user_history = load_user_history(str(history_path))
    evidence_requirements = load_evidence_requirements(str(evidence_path))

    print(f"Sample claims: {len(sample_claims)} rows")

    # The sample_claims file has both input and expected output columns
    # Extract expected outputs
    expected_rows = []
    input_rows = []
    for row in sample_claims:
        expected = dict(row)
        expected_rows.append(expected)

        # Create input-only row
        input_row = {
            "user_id": row["user_id"],
            "image_paths": row["image_paths"],
            "user_claim": row["user_claim"],
            "claim_object": row["claim_object"],
        }
        input_rows.append(input_row)

    # Process each claim
    predicted_rows = []
    start_time = time.time()

    for i, row in enumerate(input_rows):
        try:
            output_row = process_claim_for_eval(
                row, user_history, evidence_requirements,
                str(project_root), i
            )
            predicted_rows.append(output_row)
            print(f"  [DEBUG] Final verdict row dict:\n{json.dumps(output_row, indent=2)}")
        except Exception as e:
            print(f"  ERROR evaluating row {i}: {e}")
            import traceback
            traceback.print_exc()
            continue

    elapsed = time.time() - start_time
    print(f"\nEvaluation processing complete in {elapsed:.1f}s")

    # Write predicted output
    if predicted_rows:
        write_output(predicted_rows, str(eval_output_path))

    # Compare with expected
    if len(predicted_rows) == len(expected_rows):
        results = compute_metrics(predicted_rows, expected_rows)
        print_report(results)
    else:
        print(f"\nWARNING: Predicted {len(predicted_rows)} rows but "
              f"expected {len(expected_rows)}. Comparing available rows.")
        results = compute_metrics(
            predicted_rows,
            expected_rows[:len(predicted_rows)]
        )
        print_report(results)


if __name__ == "__main__":
    main()
