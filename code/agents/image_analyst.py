"""
image_analyst.py
Sends all images for a claim to GPT-4o Vision in a single API call.
Returns a structured JSON verdict.
"""
import json
import time
from pathlib import Path
from openai import RateLimitError, APIError
from utils.llm_client import client
from utils.data_loader import encode_all_images
from rules import OBJECT_PART

# Load system prompt from file
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "image_analyst_prompt.txt"

def load_system_prompt() -> str:
    with open(PROMPT_PATH, "r") as f:
        return f.read()

def build_user_message(
    claim_object: str,
    extracted_claim: str,
    claimed_part: str,
    all_claimed_parts: list[str],
    evidence_requirement: str,
    image_paths: list[str],
    image_ids: list[str]
) -> list[dict]:
    """
    Builds the full user message content list for GPT-4o.
    Structure: [image1, image2, ..., imageN, text_prompt]
    GPT-4o reads images first, then the instruction text.
    """
    # Encode all images
    encoded_images = encode_all_images(image_paths)
    
    if not encoded_images:
        return None  # No usable images
    
    # Build image ID reference text so GPT-4o knows each image's ID
    image_id_text = "\n".join(
        [f"Image {i+1} ID: {img_id}" for i, img_id in enumerate(image_ids)]
    )
    
    # Text instruction appended AFTER images
    text_block = {
        "type": "text",
        "text": f"""Image reference IDs (use these exact IDs in your response):
{image_id_text}

Claim details:
- Object type: {claim_object}
- User claims: {extracted_claim}
- Primary claimed part: {claimed_part}
- All claimed parts: {', '.join(all_claimed_parts)}
- Minimum evidence required: {evidence_requirement}

Analyze all images above and respond in the required JSON format."""
    }
    
    return encoded_images + [text_block]

def analyze_images(
    claim_object: str,
    extracted_claim: str,
    claimed_part: str,
    all_claimed_parts: list[str],
    evidence_requirement: str,
    image_paths: list[str],
    image_ids: list[str],
    max_retries: int = 3
) -> dict:
    """
    Calls GPT-4o Vision with all claim images in one API call.
    Returns parsed JSON verdict dict.
    On complete failure returns safe default verdict.
    """
    system_prompt = load_system_prompt()
    allowed_parts = OBJECT_PART.get(claim_object, set())
    allowed_parts_list = ", ".join(sorted(allowed_parts))
    system_prompt = system_prompt.format(
        claim_object=claim_object,
        allowed_parts_list=allowed_parts_list
    )
    
    user_content = build_user_message(
        claim_object, extracted_claim, claimed_part,
        all_claimed_parts, evidence_requirement,
        image_paths, image_ids
    )
    
    # No usable images at all
    if user_content is None:
        print("  image_analyst: No usable images found, returning default verdict")
        return _default_verdict()
    
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="openai/gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                max_tokens=1000,
                response_format={"type": "json_object"},
                temperature=0  # Deterministic output for consistency
            )
            
            if not response or not getattr(response, "choices", None) or len(response.choices) == 0:
                raise ValueError("Empty or invalid choices in API response")

            raw = response.choices[0].message.content
            verdict = json.loads(raw)
            print(f"  image_analyst: success on attempt {attempt+1}")
            return verdict
            
        except RateLimitError as e:
            wait = 30 * (attempt + 1)
            print(f"  image_analyst rate limited, waiting {wait}s (attempt {attempt+1}/{max_retries})")
            time.sleep(wait)
            
        except APIError as e:
            print(f"  image_analyst API error: {e} (attempt {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(10)
            
        except json.JSONDecodeError as e:
            print(f"  image_analyst JSON parse error: {e}")
            print(f"  Raw response was: {raw if 'raw' in locals() else 'None'}")
            if attempt < max_retries - 1:
                time.sleep(5)

        except Exception as e:
            print(f"  image_analyst unexpected error: {e} (attempt {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(5)
    
    print("  image_analyst: all retries failed, returning default verdict")
    return _default_verdict()

def _default_verdict() -> dict:
    """Safe default when image analysis completely fails."""
    return {
        "valid_image": False,
        "issue_type": "unknown",
        "object_part": "unknown",
        "severity": "unknown",
        "supporting_image_ids": [],
        "risk_flags": [],
        "claim_status": "not_enough_information",
        "claim_status_justification": "Image analysis failed after all retries."
    }
