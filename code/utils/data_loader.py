"""
Data loading utilities: CSV readers and image path resolver.
"""
import csv
import os
from pathlib import Path
from typing import Any
import base64


def load_claims(path: str) -> list[dict[str, str]]:
    """Load claims.csv or sample_claims.csv and return list of row dicts."""
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))
    return rows


def load_user_history(path: str) -> dict[str, dict[str, Any]]:
    """
    Load user_history.csv and return dict keyed by user_id.
    Numeric columns are cast to int.
    """
    history = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            uid = row["user_id"]
            history[uid] = {
                "user_id": uid,
                "past_claim_count": int(row["past_claim_count"]),
                "accept_claim": int(row["accept_claim"]),
                "manual_review_claim": int(row["manual_review_claim"]),
                "rejected_claim": int(row["rejected_claim"]),
                "last_90_days_claim_count": int(row["last_90_days_claim_count"]),
                "history_flags": row["history_flags"].strip(),
                "history_summary": row["history_summary"].strip(),
            }
    return history


def load_evidence_requirements(path: str) -> list[dict[str, str]]:
    """Load evidence_requirements.csv and return list of row dicts."""
    reqs = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            reqs.append(dict(row))
    return reqs


def find_evidence_requirement(
    requirements: list[dict[str, str]],
    claim_object: str,
    issue_family: str,
) -> str:
    """
    Find the best matching evidence requirement for a claim.
    Returns the minimum_image_evidence text.
    Falls back to the general requirement if no specific match.
    """
    # Normalise for matching
    issue_lower = issue_family.lower().strip()

    # Try object-specific match first
    best_match = None
    general_match = None

    for req in requirements:
        req_object = req["claim_object"].strip().lower()
        applies_to = req["applies_to"].strip().lower()

        # Check if the issue family keywords overlap
        if req_object == claim_object.lower() or req_object == "all":
            # Check if the applies_to text contains keywords from the issue family
            if _issue_matches(issue_lower, applies_to):
                if req_object == claim_object.lower():
                    best_match = req["minimum_image_evidence"]
                elif req_object == "all" and general_match is None:
                    general_match = req["minimum_image_evidence"]

    if best_match:
        return best_match
    if general_match:
        return general_match

    # Final fallback: general claim review
    for req in requirements:
        if req["applies_to"].strip().lower() == "general claim review":
            return req["minimum_image_evidence"]

    return "The claimed object and relevant part should be visible clearly enough to inspect the claimed condition."


def _issue_matches(issue_family: str, applies_to: str) -> bool:
    """Check if an issue family matches an applies_to description."""
    # Map issue families to keywords to match against applies_to
    keyword_map = {
        "dent or scratch": ["dent", "scratch", "body", "panel"],
        "crack or shatter": ["crack", "broken", "missing", "glass", "shatter"],
        "broken or missing": ["crack", "broken", "missing"],
        "packaging damage": ["crushed", "torn", "seal", "exterior"],
        "water or stain": ["water", "stain", "label"],
        "contents or item": ["contents", "inner", "item", "missing"],
    }

    # Check each keyword set
    for family_key, keywords in keyword_map.items():
        if any(kw in issue_family for kw in family_key.split()):
            if any(kw in applies_to for kw in keywords):
                return True

    # Also check for general/reviewability matches
    if "general" in applies_to or "reviewability" in applies_to:
        return True

    # Direct keyword overlap
    issue_words = set(issue_family.replace(" or ", " ").split())
    applies_words = set(applies_to.replace(",", " ").replace(" or ", " ").split())
    if issue_words & applies_words:
        return True

    return False


def load_images(
    image_paths_str: str,
    base_dir: str,
) -> list[tuple[str, str]]:
    """
    Resolve image paths for PIL.Image loading.

    Args:
        image_paths_str: semicolon-separated image paths from CSV
            (e.g. "images/test/case_001/img_1.jpg")
        base_dir: project root directory

    Returns:
        List of (image_id, absolute_path) tuples.
    """
    results = []
    paths = [p.strip() for p in image_paths_str.split(";") if p.strip()]

    for rel_path in paths:
        # CSV paths are like "images/test/case_001/img_1.jpg"
        # but actual files are under "dataset/images/..."
        abs_path = os.path.join(base_dir, "dataset", rel_path)
        image_id = Path(rel_path).stem  # e.g. "img_1"

        if not os.path.exists(abs_path):
            print(f"  WARNING: Image not found: {abs_path}")
            continue

        results.append((image_id, abs_path))

    return results


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

def encode_image_to_base64(image_path: str) -> dict:
    """
    Encodes a single image file to a GPT-4o compatible image_url content block.
    Returns a dict ready to insert into the messages content list.
    """
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported image format: {ext}")
    
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp"
    }
    mime_type = mime_map[ext]
    
    with open(path, "rb") as f:
        b64_data = base64.b64encode(f.read()).decode("utf-8")
    
    return {
        "type": "image_url",
        "image_url": {
            "url": f"data:{mime_type};base64,{b64_data}",
            "detail": "high"
        }
    }

def encode_all_images(image_paths: list[str]) -> list[dict]:
    """
    Encodes multiple images for a single claim.
    Skips images that fail to load with a warning.
    Returns list of GPT-4o image_url content blocks.
    """
    encoded = []
    for path in image_paths:
        try:
            block = encode_image_to_base64(path)
            encoded.append(block)
        except Exception as e:
            print(f"WARNING: Skipping image {path}: {e}")
    return encoded

