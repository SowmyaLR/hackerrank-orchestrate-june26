"""
Allowed value constants and validation for the evidence review pipeline.
"""

# --- Allowed values for output columns ---

CLAIM_STATUS = frozenset([
    "supported",
    "contradicted",
    "not_enough_information",
])

ISSUE_TYPE = frozenset([
    "dent", "scratch", "crack", "glass_shatter", "broken_part",
    "missing_part", "torn_packaging", "crushed_packaging",
    "water_damage", "stain", "none", "unknown",
])

SEVERITY = frozenset([
    "none", "low", "medium", "high", "unknown",
])

RISK_FLAGS = frozenset([
    "none", "blurry_image", "cropped_or_obstructed", "low_light_or_glare",
    "wrong_angle", "wrong_object", "wrong_object_part", "damage_not_visible",
    "claim_mismatch", "possible_manipulation", "non_original_image",
    "text_instruction_present", "user_history_risk", "manual_review_required",
])

OBJECT_PART = {
    "car": frozenset([
        "front_bumper", "rear_bumper", "door", "hood", "windshield",
        "side_mirror", "headlight", "taillight", "fender",
        "quarter_panel", "body", "unknown",
    ]),
    "laptop": frozenset([
        "screen", "keyboard", "trackpad", "hinge", "lid",
        "corner", "port", "base", "body", "unknown",
    ]),
    "package": frozenset([
        "box", "package_corner", "package_side", "seal",
        "label", "contents", "item", "unknown",
    ]),
}

# --- Injection detection ---

INJECTION_BLOCKLIST = [
    "ignore previous",
    "ignore all",
    "admin mode",
    "follow the note",
    "override",
    "bypass",
    "approve everything",
    "disregard instructions",
]

# --- Output column order ---

OUTPUT_COLUMNS = [
    "user_id",
    "image_paths",
    "user_claim",
    "claim_object",
    "evidence_standard_met",
    "evidence_standard_met_reason",
    "risk_flags",
    "issue_type",
    "object_part",
    "claim_status",
    "claim_status_justification",
    "supporting_image_ids",
    "valid_image",
    "severity",
]


def detect_injection(text: str) -> bool:
    """Check if text contains any injection patterns from the blocklist."""
    text_lower = text.lower()
    return any(pattern in text_lower for pattern in INJECTION_BLOCKLIST)


def validate_row(row: dict, claim_object: str) -> None:
    """
    Validate that all output fields contain allowed values.
    Raises ValueError if any field has a disallowed value.
    """
    # claim_status
    if row.get("claim_status") not in CLAIM_STATUS:
        raise ValueError(
            f"Invalid claim_status: '{row.get('claim_status')}'. "
            f"Allowed: {sorted(CLAIM_STATUS)}"
        )

    # issue_type
    if row.get("issue_type") not in ISSUE_TYPE:
        raise ValueError(
            f"Invalid issue_type: '{row.get('issue_type')}'. "
            f"Allowed: {sorted(ISSUE_TYPE)}"
        )

    # object_part — must match the claim_object's allowed set
    allowed_parts = OBJECT_PART.get(claim_object, set())
    if row.get("object_part") not in allowed_parts:
        raise ValueError(
            f"Invalid object_part: '{row.get('object_part')}' for "
            f"claim_object='{claim_object}'. Allowed: {sorted(allowed_parts)}"
        )

    # severity
    if row.get("severity") not in SEVERITY:
        raise ValueError(
            f"Invalid severity: '{row.get('severity')}'. "
            f"Allowed: {sorted(SEVERITY)}"
        )

    # risk_flags — semicolon-separated, each must be in the allowed set
    raw_flags = row.get("risk_flags", "none")
    flags = [f.strip() for f in raw_flags.split(";")]
    for flag in flags:
        if flag not in RISK_FLAGS:
            raise ValueError(
                f"Invalid risk_flag: '{flag}'. Allowed: {sorted(RISK_FLAGS)}"
            )

    # evidence_standard_met — must be "true" or "false"
    if row.get("evidence_standard_met") not in ("true", "false"):
        raise ValueError(
            f"Invalid evidence_standard_met: '{row.get('evidence_standard_met')}'. "
            "Allowed: 'true' or 'false'"
        )

    # valid_image — must be "true" or "false"
    if row.get("valid_image") not in ("true", "false"):
        raise ValueError(
            f"Invalid valid_image: '{row.get('valid_image')}'. "
            "Allowed: 'true' or 'false'"
        )
