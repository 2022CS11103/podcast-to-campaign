import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from utils.gemini_clients import get_client

PROMPT = """You are a marketing strategist. A creator wants to plan a content campaign from a podcast, but hasn't uploaded it yet -- estimate a sensible plan based only on their goal, audience, tone, and campaign duration.

Rules:
- For a 7-day campaign, total short-form pieces (instagram_reels+youtube_shorts) should be 2-4.
- For 14 days, 4-6. For 30 days, 6-10. For 60 days, 10-16.
- LinkedIn: roughly weekly for the given duration (e.g. 30 days = 3-4 posts).
- Twitter: roughly every 4-5 days for the given duration.
- If goal is "Course Sales" or "LinkedIn Authority", weight more toward LinkedIn.
- If goal is "Brand Awareness", weight more toward Reels/Shorts.

Return ONLY valid JSON, no markdown, no preamble:
{
  "instagram_reels": {"count": <int>, "interval_days": <int>},
  "youtube_shorts": {"count": <int>, "interval_days": <int>},
  "linkedin": {"count": <int>, "interval_days": <int>},
  "twitter": {"count": <int>, "interval_days": <int>}
}

Input:
"""


def recommend(brand_context: dict) -> dict:
    client = get_client()
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=PROMPT + json.dumps(brand_context, indent=2),
    )
    raw = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


if __name__ == "__main__":
    # standalone testing
    test_input = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {
        "goal": "Brand Awareness", "audience": "Startup Founders",
        "tone": "Professional", "campaign_duration_days": 30
    }
    print(json.dumps(recommend(test_input), indent=2))