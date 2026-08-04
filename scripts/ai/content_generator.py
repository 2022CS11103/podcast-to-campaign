import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from utils.gemini_clients import get_client
from utils.prompt_loader import load_prompt
from utils.cost_tracker import log_gemini_call

PLATFORMS = [
    "linkedin",
    "twitter",
    "blog",
    "newsletter",
    "youtube",
    "instagram"
]


def load_brand_context():
    brand_file = PROJECT_ROOT / "brand_context.json"
    if brand_file.exists():
        with open(brand_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def build_brand_prefix(brand):
    if not brand:
        return ""
    parts = []
    if brand.get("brand_name"):
        parts.append(f"Brand: {brand['brand_name']}")
    if brand.get("goal"):
        parts.append(f"Campaign Goal: {brand['goal']}")
    if brand.get("audience"):
        parts.append(f"Target Audience: {brand['audience']}")
    if brand.get("tone"):
        parts.append(f"Tone of Voice: {brand['tone']}")
    if not parts:
        return ""
    return "Context for this content:\n" + "\n".join(parts) + "\n\n"


def generate_content(text, platform, brand_prefix):
    """Generate content for a specific platform."""

    prompt = load_prompt(platform)
    client = get_client()

    full_prompt = f"{brand_prefix}{prompt}\n\nTranscript:\n{text}"

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=full_prompt,
    )

    log_gemini_call(f"marketing_{platform}", response)

    return response.text


def main():

    input_file = PROJECT_ROOT / "output" / "clips.json"

    if not input_file.exists():
        raise FileNotFoundError(f"Clips file not found: {input_file}")

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    transcript = ""

    for clip in data["clips"]:
        transcript += (
            f"Summary: {clip.get('summary', '')}\n"
            f"Hook: {clip.get('hook', '')}\n"
            f"Reason: {clip.get('reason', '')}\n"
            f"Score: {clip.get('overall_score', 0)}\n\n"
        )

    brand = load_brand_context()
    brand_prefix = build_brand_prefix(brand)

    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(exist_ok=True)

    for platform in PLATFORMS:

        print(f"Generating {platform} content...")

        content = generate_content(
            transcript,
            platform,
            brand_prefix
        )

        output_file = output_dir / f"{platform}.md"

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"✅ Saved {platform} -> {output_file}")


if __name__ == "__main__":
    main()