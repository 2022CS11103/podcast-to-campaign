import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from utils.gemini_clients import get_client
from utils.cost_tracker import log_gemini_call
from utils.content_plan import load_plan, plan_is_usable, save_plan

STRATEGY_PROMPT = """You are a marketing strategist planning a content calendar from a single podcast/video, spread over a specific campaign duration.

Given the brand context, the number of highlight-worthy clips available, and the campaign duration in days, decide:
1. How many Instagram Reels, YouTube Shorts, LinkedIn posts, and Twitter threads to create (must not exceed available_clips total across reels+shorts combined; linkedin/twitter can reuse clip insights so are not limited by clip count)
2. What posting interval (in days) makes sense per platform to spread the content evenly across the FULL campaign duration given (e.g. if duration is 7 days, do not plan a month's worth of low-frequency posting -- fit it into 7 days. If duration is 30 days, spread appropriately across the full month)
3. A short reasoning (max 100 words) explaining the mix and why it fits the given duration

Rules:
- Total (reels + shorts) must be <= available_clips
- Do NOT simply use all available_clips just because they exist. Choose a realistic, high-quality-over-quantity number based on campaign_duration_days: for a 7-day campaign, total short-form pieces (reels+shorts combined) should be 2-4. For 14 days, 4-6. For 30 days, 6-10. Never exceed these ranges even if more clips are available -- quality and spacing matter more than using everything.
- LinkedIn posts should be 1-4 for a 30-day campaign (roughly weekly), fewer for shorter durations. Do not generate 8+ LinkedIn posts.
- Twitter threads should be 3-6 for a 30-day campaign, fewer for shorter durations. Do not generate 10+ threads.
- All scheduled posts (count * interval_days per platform, roughly) must fit within the given campaign_duration_days
- If goal is "Course Sales" or "LinkedIn Authority", weight more toward LinkedIn. If "Brand Awareness", weight more toward Reels/Shorts.
- Shorter durations (e.g. 7 days) should have fewer total pieces and tighter intervals. Longer durations (e.g. 30 days) should have more pieces spread further apart.

Return ONLY valid JSON in this exact format, no markdown, no preamble:
{
  "content_plan": {
    "instagram_reels": {"count": <int>, "interval_days": <int>},
    "youtube_shorts": {"count": <int>, "interval_days": <int>},
    "linkedin": {"count": <int>, "interval_days": <int>},
    "twitter": {"count": <int>, "interval_days": <int>}
  },
  "reasoning": "<short explanation>"
}

Brand context, available clips, and campaign duration:
"""


def default_plan(campaign_duration_days, available_clips):
    reel_count = max(1, min(campaign_duration_days // 7, available_clips))
    return {
        "content_plan": {
            "instagram_reels": {
                "count": reel_count,
                "interval_days": max(1, campaign_duration_days // max(reel_count, 1)),
            },
            "youtube_shorts": {
                "count": max(1, reel_count - 1),
                "interval_days": max(1, campaign_duration_days // max(reel_count, 1)),
            },
            "linkedin": {
                "count": max(1, campaign_duration_days // 7),
                "interval_days": 7,
            },
            "twitter": {
                "count": max(1, campaign_duration_days // 6),
                "interval_days": 6,
            },
        },
        "reasoning": (
            f"Default balanced mix scaled for a {campaign_duration_days}-day "
            "campaign (AI response could not be parsed)."
        ),
    }


def write_brief(reasoning, plan):
    output_file = PROJECT_ROOT / "output" / "strategy_brief.txt"
    output_file.parent.mkdir(exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(reasoning + "\n\n" + json.dumps(plan, indent=2))


def main():
    existing = load_plan(required=False)
    if plan_is_usable(existing):
        write_brief(
            "Using the content plan supplied by the creator. "
            "Strategy agent did not override it.",
            existing,
        )
        print("✅ Existing content_plan.json kept (user/frontend plan).")
        print(json.dumps(existing, indent=2))
        return

    brand_file = PROJECT_ROOT / "brand_context.json"
    chunks_file = PROJECT_ROOT / "output" / "chunks.json"

    brand = {}
    if brand_file.exists():
        with open(brand_file, "r", encoding="utf-8") as f:
            brand = json.load(f)

    campaign_duration_days = brand.get("campaign_duration_days", 30)

    available_clips = 8
    if chunks_file.exists():
        with open(chunks_file, "r", encoding="utf-8") as f:
            chunk_data = json.load(f)
        available_clips = chunk_data.get("chunk_count", 8)

    context_text = json.dumps({
        "brand": brand,
        "available_clips": available_clips,
        "campaign_duration_days": campaign_duration_days
    }, indent=2)

    client = get_client()
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=STRATEGY_PROMPT + context_text,
    )
    log_gemini_call("strategy_decision", response)

    raw = response.text.replace("```json", "").replace("```", "").strip()

    try:
        decision = json.loads(raw)
    except Exception:
        decision = default_plan(campaign_duration_days, available_clips)

    save_plan(decision["content_plan"])
    write_brief(decision["reasoning"], decision["content_plan"])

    print(f"✅ Campaign duration: {campaign_duration_days} days")
    print(f"✅ AI decided content plan: {json.dumps(decision['content_plan'], indent=2)}")
    print(f"✅ Reasoning: {decision['reasoning']}")


if __name__ == "__main__":
    main()
