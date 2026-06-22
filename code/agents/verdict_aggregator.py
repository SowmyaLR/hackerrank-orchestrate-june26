"""
Verdict Aggregator: combines outputs from all agents into a final output row.
Handles multi-part claims, risk flag merging, and consistency enforcement.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rules import validate_row, OBJECT_PART, CLAIM_STATUS, ISSUE_TYPE, SEVERITY, RISK_FLAGS


def aggregate(
    input_row: dict,
    claim_parse: dict,
    vision_result: dict,
    evidence_met: str,
    evidence_reason: str,
    history_risk_flags: set[str],
) -> dict:
    """
    Combine all agent outputs into a single validated output row.

    Args:
        input_row: original row from claims.csv (4 input columns)
        claim_parse: output from claim_parser
        vision_result: output from image_analyst
        evidence_met: "true" or "false" from evidence_checker
        evidence_reason: reason string from evidence_checker
        history_risk_flags: set of risk flags from risk_assessor

    Returns:
        Complete row dict ready for output.csv
    """
    claim_object = input_row["claim_object"]

    # --- Multi-part handling ---
    claimed_parts = claim_parse.get("claimed_parts", ["unknown"])
    # Pick primary part: first in the list
    primary_part = claimed_parts[0] if claimed_parts else "unknown"
    if isinstance(primary_part, str):
        primary_part = primary_part.strip().lower().replace(" ", "_")

    # Use vision result's object_part if available and valid
    vision_part = vision_result.get("object_part", "unknown")
    if isinstance(vision_part, str):
        vision_part = vision_part.strip().lower().replace(" ", "_")

    allowed_parts = OBJECT_PART.get(claim_object, set())

    # Prefer vision result if it's a valid part
    if vision_part in allowed_parts and vision_part != "unknown":
        final_part = vision_part
    elif primary_part in allowed_parts:
        final_part = primary_part
    else:
        final_part = "unknown"

    # --- Risk flag merging ---
    # Start with vision flags
    vision_flags = set()
    raw_vision_flags = vision_result.get("risk_flags", [])
    if isinstance(raw_vision_flags, str):
        raw_vision_flags = [f.strip() for f in raw_vision_flags.split(";")]
    elif not isinstance(raw_vision_flags, list):
        raw_vision_flags = []

    for f in raw_vision_flags:
        if isinstance(f, str):
            f_norm = f.strip().lower().replace(" ", "_")
            if f_norm in RISK_FLAGS:
                vision_flags.add(f_norm)

    # Add injection flag if detected
    if claim_parse.get("injection_detected", False):
        vision_flags.add("text_instruction_present")

    # Merge with history flags (additive)
    history_flags_norm = set()
    for f in history_risk_flags:
        if isinstance(f, str):
            f_norm = f.strip().lower().replace(" ", "_")
            if f_norm in RISK_FLAGS:
                history_flags_norm.add(f_norm)

    all_flags = vision_flags | history_flags_norm

    # Remove "none" if there are actual flags
    all_flags.discard("none")

    # Format flags
    if not all_flags:
        flags_str = "none"
    else:
        flags_str = ";".join(sorted(all_flags))

    # --- valid_image handling ---
    valid_image = vision_result.get("valid_image", True)
    if isinstance(valid_image, bool):
        valid_image_str = "true" if valid_image else "false"
    else:
        valid_image_str = str(valid_image).lower()

    # --- Consistency enforcement ---
    claim_status = vision_result.get("claim_status", "not_enough_information")
    if isinstance(claim_status, str):
        claim_status = claim_status.strip().lower().replace(" ", "_")
    if claim_status not in CLAIM_STATUS:
        claim_status = "not_enough_information"

    justification = vision_result.get(
        "claim_status_justification", "No justification provided."
    )

    # If valid_image is false → evidence_standard_met must be false (except if contradicted)
    if valid_image_str == "false" and claim_status != "contradicted":
        evidence_met = "false"

    # If no usable images → claim_status = not_enough_information
    supporting_ids = vision_result.get("supporting_image_ids", [])
    if isinstance(supporting_ids, str):
        supporting_ids = [i.strip() for i in supporting_ids.split(";")]
    elif not isinstance(supporting_ids, list):
        supporting_ids = []

    if valid_image_str == "false" and claim_status != "contradicted":
        # Even with invalid images, if the model can clearly see it's wrong
        # (e.g. wrong object), it can still be contradicted
        if claim_status == "supported":
            claim_status = "not_enough_information"

    # If all images invalid and no supporting evidence
    if valid_image_str == "false" and not supporting_ids:
        supporting_ids_str = "none"
    elif supporting_ids:
        supporting_ids_str = ";".join(supporting_ids)
    else:
        supporting_ids_str = "none"

    # --- Multi-part justification enrichment ---
    if len(claimed_parts) > 1:
        parts_note = f" Both claimed parts ({', '.join(claimed_parts)}) were assessed."
        if not justification.endswith("."):
            justification += "."
        justification += parts_note

    # Normalise issue_type and severity
    issue_type = vision_result.get("issue_type", "unknown")
    if isinstance(issue_type, str):
        issue_type = issue_type.strip().lower().replace(" ", "_")
    if issue_type not in ISSUE_TYPE:
        # Check mapping for common variants or fall back to unknown
        issue_type = "unknown"

    severity = vision_result.get("severity", "unknown")
    if isinstance(severity, str):
        severity = severity.strip().lower().replace(" ", "_")
    if severity not in SEVERITY:
        severity = "unknown"

    # --- Build the final row ---
    row = {
        # Pass-through from input
        "user_id": input_row["user_id"],
        "image_paths": input_row["image_paths"],
        "user_claim": input_row["user_claim"],
        "claim_object": claim_object,
        # Generated fields
        "evidence_standard_met": evidence_met,
        "evidence_standard_met_reason": evidence_reason,
        "risk_flags": flags_str,
        "issue_type": issue_type,
        "object_part": final_part,
        "claim_status": claim_status,
        "claim_status_justification": justification,
        "supporting_image_ids": supporting_ids_str,
        "valid_image": valid_image_str,
        "severity": severity,
    }

    # Validate before returning
    validate_row(row, claim_object)

    return row
