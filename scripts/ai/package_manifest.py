"""Write a downloadable-package manifest for the campaign zip / paid API."""

import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

OUTPUT = PROJECT_ROOT / "output"


def exists(name):
    p = OUTPUT / name
    return str(p) if p.exists() else None


def main():
    bank = {}
    bank_file = OUTPUT / "content_bank.json"
    if bank_file.exists():
        with open(bank_file, "r", encoding="utf-8") as f:
            bank = json.load(f)

    cost = {}
    cost_file = OUTPUT / "cost_report.json"
    if cost_file.exists():
        with open(cost_file, "r", encoding="utf-8") as f:
            cost = json.load(f)

    timing = {}
    timing_file = OUTPUT / "timing_report.json"
    if timing_file.exists():
        with open(timing_file, "r", encoding="utf-8") as f:
            timing = json.load(f)

    videos = []
    for folder in ("final_shorts", "youtube_shorts", "instagram_reels", "tiktok"):
        d = OUTPUT / folder
        if d.exists():
            videos.extend(sorted(str(p) for p in d.glob("*.mp4")))

    posts = []
    posts_dir = OUTPUT / "posts"
    if posts_dir.exists():
        posts = sorted(str(p) for p in posts_dir.glob("*.md"))

    manifest = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "package_type": "marketing_ready_campaign",
        "contents": {
            "vertical_videos": videos,
            "per_clip_posts": posts,
            "seo_blog": exists("blog.md"),
            "newsletter": exists("newsletter.md"),
            "calendar": exists("campaign_calendar.md"),
            "strategy_brief": exists("strategy_brief.txt"),
            "edit_plans": exists("edit_plans.json"),
            "content_bank": exists("content_bank.json"),
            "campaign_summary": exists("campaign_summary.json"),
            "cost_report": exists("cost_report.json"),
            "timing_report": exists("timing_report.json"),
        },
        "schedule": [
            {
                "id": item.get("id"),
                "date": item.get("scheduled_date"),
                "platform": item.get("assigned_platform"),
                "hook": item.get("hook"),
                "duration_seconds": item.get("duration_seconds"),
                "active_variant": item.get("active_variant"),
                "status": item.get("status"),
            }
            for item in bank.get("items", [])
        ],
        "totals": {
            "content_pieces": bank.get("total_allocated", 0),
            "video_renders": bank.get("video_renders"),
            "estimated_cost_usd": cost.get("estimated_cost_usd"),
            "estimated_cost_inr": cost.get("estimated_cost_inr"),
            "processing_seconds": timing.get("total_seconds"),
            "processing_human": timing.get("total_human"),
        },
        "how_to_use": [
            "Post the scheduled items in calendar order.",
            "Ship variant A first. Log views/likes via POST /performance/{id}.",
            "When a clip is a winner, call POST /repost/{id} to queue a 14-day remix.",
            "Publish blog.md to your site for SEO; send newsletter.md to your list.",
        ],
    }

    out = OUTPUT / "package_manifest.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"✅ Package manifest saved to {out}")


if __name__ == "__main__":
    main()
