"""
Main entry point: Multi-Modal Evidence Review Pipeline.

Processes dataset/claims.csv and produces output.csv.
Uses OpenAI GPT-4o for claim parsing and image analysis.

Usage:
    OPENAI_API_KEY=your_key python code/main.py
"""
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Load env variables from .env
load_dotenv()

# Ensure code/ is on the path
CODE_DIR = os.path.dirname(os.path.abspath(__file__))
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

# --- Configuration ---
INTER_CALL_SLEEP = 4  # seconds between Gemini API calls (15 RPM free tier)


def process_claim(
    row: dict,
    user_history: dict,
    evidence_requirements: list[dict],
    base_dir: str,
    row_index: int,
) -> dict:
    """Process a single claim row through the full pipeline."""
    user_id = row["user_id"]
    claim_object = row["claim_object"]
    user_claim = row["user_claim"]
    image_paths_str = row["image_paths"]

    print(f"\n[{row_index:03d}] Processing user={user_id} object={claim_object}")

    # --- Step 1: Parse the claim ---
    print(f"  Step 1: Parsing claim...")
    claim_parse = parse_claim(user_claim, claim_object)
    print(f"    Language: {claim_parse.get('language_detected', '?')}")
    print(f"    Claim: {claim_parse.get('extracted_claim', '?')[:80]}")
    print(f"    Parts: {claim_parse.get('claimed_parts', [])}")
    print(f"    Injection: {claim_parse.get('injection_detected', False)}")

    time.sleep(INTER_CALL_SLEEP)

    # --- Step 2: Get evidence requirement ---
    issue_family = claim_parse.get("issue_family", "other")
    requirement_text = get_requirement(
        evidence_requirements, claim_object, issue_family
    )
    print(f"  Step 2: Evidence requirement: {requirement_text[:60]}...")

    # --- Step 3: Load images ---
    images = load_images(image_paths_str, base_dir)
    print(f"  Step 3: Loaded {len(images)} image(s)")

    # --- Step 4: Analyse images with Gemini Vision ---
    claimed_parts = claim_parse.get("claimed_parts", ["unknown"])
    primary_part = claimed_parts[0] if claimed_parts else "unknown"
    extracted_claim = claim_parse.get("extracted_claim", user_claim[:200])

    # If injection was detected, use sanitised claim for vision
    if claim_parse.get("injection_detected", False):
        extracted_claim = claim_parse.get("sanitised_claim", extracted_claim)

    print(f"  Step 4: Analysing images...")
    vision_result = analyze_images(
        claim_object=claim_object,
        extracted_claim=extracted_claim,
        claimed_part=primary_part,
        all_claimed_parts=claimed_parts,
        evidence_requirement=requirement_text,
        image_paths=[img[1] for img in images],
        image_ids=[img[0] for img in images]
    )
    print(f"    Status: {vision_result.get('claim_status', '?')}")
    print(f"    Issue: {vision_result.get('issue_type', '?')}")
    print(f"    Part: {vision_result.get('object_part', '?')}")
    print(f"    Valid: {vision_result.get('valid_image', '?')}")

    time.sleep(1)

    # --- Step 5: Check evidence standard ---
    evidence_met, evidence_reason = check_evidence_met(
        vision_result, claim_object, issue_family, evidence_requirements
    )
    print(f"  Step 5: Evidence met: {evidence_met}")

    # --- Step 6: Assess user risk ---
    user_hist = user_history.get(user_id)
    history_risk_flags = assess_risk(user_hist)
    if history_risk_flags:
        print(f"  Step 6: History flags: {history_risk_flags}")
    else:
        print(f"  Step 6: No history risk flags")

    # --- Step 7: Aggregate verdict ---
    output_row = aggregate(
        input_row=row,
        claim_parse=claim_parse,
        vision_result=vision_result,
        evidence_met=evidence_met,
        evidence_reason=evidence_reason,
        history_risk_flags=history_risk_flags,
    )
    print(f"  RESULT: status={output_row['claim_status']} "
          f"severity={output_row['severity']} "
          f"flags={output_row['risk_flags']}")

    return output_row


def main():
    """Main pipeline execution."""
    # Validate API key
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY environment variable is not set.")
        print("Usage: OPENROUTER_API_KEY=your_key python code/main.py")
        sys.exit(1)

    # Resolve paths
    project_root = Path(CODE_DIR).parent
    claims_path = project_root / "dataset" / "claims.csv"
    history_path = project_root / "dataset" / "user_history.csv"
    evidence_path = project_root / "dataset" / "evidence_requirements.csv"
    output_path = project_root / "output.csv"

    print("=" * 60)
    print("Multi-Modal Evidence Review Pipeline")
    print("=" * 60)
    print(f"Project root: {project_root}")
    print(f"Claims file:  {claims_path}")
    print(f"Output file:  {output_path}")

    # Load data
    print("\nLoading data...")
    claims = load_claims(str(claims_path))
    user_history = load_user_history(str(history_path))
    evidence_requirements = load_evidence_requirements(str(evidence_path))

    print(f"  Claims: {len(claims)} rows")
    print(f"  Users:  {len(user_history)} in history")
    print(f"  Rules:  {len(evidence_requirements)} evidence requirements")

    # Process each claim
    output_rows = []
    start_time = time.time()

    for i, row in enumerate(claims):
        try:
            output_row = process_claim(
                row=row,
                user_history=user_history,
                evidence_requirements=evidence_requirements,
                base_dir=str(project_root),
                row_index=i,
            )
            output_rows.append(output_row)
            time.sleep(2)
        except Exception as e:
            print(f"\n  ERROR processing row {i} (user={row.get('user_id')}): {e}")
            import traceback
            traceback.print_exc()
            # Continue processing remaining rows
            continue

    elapsed = time.time() - start_time

    # Write output
    print(f"\n{'=' * 60}")
    print(f"Pipeline complete in {elapsed:.1f}s")
    print(f"Processed: {len(output_rows)}/{len(claims)} rows")
    write_output(output_rows, str(output_path))

    # Print row count and claim_status distribution
    print(f"\nVerification of output.csv:")
    print(f"  Total row count written: {len(output_rows)}")
    
    distribution = {}
    for row in output_rows:
        status = row.get("claim_status", "unknown")
        distribution[status] = distribution.get(status, 0) + 1
        
    print("  claim_status distribution:")
    for status, count in distribution.items():
        print(f"    - {status}: {count}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
