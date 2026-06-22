"""
Evidence Checker Agent: rule-based check against evidence_requirements.csv.
No LLM calls — pure logic.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.data_loader import find_evidence_requirement


def get_requirement(
    requirements: list[dict],
    claim_object: str,
    issue_family: str,
) -> str:
    """
    Look up the minimum evidence requirement text for a claim.
    This is called BEFORE the vision call to pass into the prompt.
    """
    return find_evidence_requirement(requirements, claim_object, issue_family)


def check_evidence_met(
    vision_result: dict,
    claim_object: str,
    issue_family: str,
    requirements: list[dict],
) -> tuple[str, str]:
    """
    Determine whether the evidence standard is met based on vision results.

    Returns:
        (evidence_standard_met: "true"|"false", reason: str)
    """
    valid_image = vision_result.get("valid_image", False)
    claim_status = vision_result.get("claim_status", "not_enough_information")
    risk_flags = vision_result.get("risk_flags", [])
    supporting_ids = vision_result.get("supporting_image_ids", [])

    requirement_text = find_evidence_requirement(
        requirements, claim_object, issue_family
    )

    # Rule 1: If valid_image is false and claim_status is not contradicted, evidence standard is NOT met
    if not valid_image and claim_status != "contradicted":
        return "false", (
            "The submitted image(s) are not usable for automated review, "
            "so the evidence standard is not met."
        )

    # Rule 2: If claim_status is supported or contradicted, the evidence standard IS met
    if claim_status in ("supported", "contradicted"):
        reason = vision_result.get(
            "claim_status_justification",
            f"The submitted image(s) are sufficient to evaluate the {claim_object} damage claim."
        )
        return "true", _build_evidence_reason(
            claim_status, claim_object, risk_flags, reason
        )

    # Rule 3: If wrong_object is flagged, the evidence doesn't meet the standard
    if "wrong_object" in risk_flags:
        return "false", (
            "The image shows a different object than the claimed "
            f"{claim_object}, so the evidence standard is not met."
        )

    # Rule 4: If damage is not visible and claim_status is not_enough_information
    if claim_status == "not_enough_information":
        # Check why — is it quality or just not visible?
        quality_flags = {"blurry_image", "low_light_or_glare", "cropped_or_obstructed", "wrong_angle"}
        has_quality_issues = bool(set(risk_flags) & quality_flags)

        if "damage_not_visible" in risk_flags or "wrong_object_part" in risk_flags:
            return "false", (
                "The claimed part or damage is not visible in the submitted images."
            )
        if has_quality_issues:
            return "false", (
                "Image quality issues prevent confident evaluation of the claim."
            )
        return "false", (
            "The submitted images do not provide enough evidence to evaluate the claim."
        )

    # Default fallback
    return "true", (
        f"The submitted image(s) provide enough visual evidence "
        f"to evaluate the {claim_object} claim."
    )


def _build_evidence_reason(
    claim_status: str,
    claim_object: str,
    risk_flags: list,
    justification: str,
) -> str:
    """Build a concise evidence_standard_met_reason."""
    if claim_status == "contradicted":
        return (
            f"The submitted image(s) are clear enough to evaluate "
            f"the {claim_object} claim, though the visible evidence "
            f"does not match the claimed damage."
        )
    # Supported or other
    quality_issues = [
        f for f in risk_flags
        if f in ("blurry_image", "low_light_or_glare", "cropped_or_obstructed")
    ]
    if quality_issues:
        return (
            f"Despite some image quality issues ({', '.join(quality_issues)}), "
            f"at least one submitted image provides sufficient evidence "
            f"for the {claim_object} claim."
        )
    return (
        f"The submitted image(s) provide clear visual evidence "
        f"to evaluate the {claim_object} damage claim."
    )
