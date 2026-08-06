import json
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def load_plan():
    plan_file = PROJECT_ROOT / "content_plan.json"
    if plan_file.exists():
        with open(plan_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "instagram_reels": {"count": 2, "interval_days": 3},
        "youtube_shorts": {"count": 2, "interval_days": 3},
        "linkedin": {"count": 1, "interval_days": 7},
        "twitter": {"count": 1, "interval_days": 5},
    }


PLATFORM_SCORE_WEIGHTS = {
    "instagram_reels": {"hook": 0.4, "shareability": 0.35, "curiosity": 0.25},
    "youtube_shorts":  {"hook": 0.35, "shareability": 0.3, "curiosity": 0.2, "emotion": 0.15},
    "linkedin":        {"education": 0.5, "emotion": 0.2, "hook": 0.3},
    "twitter":         {"curiosity": 0.4, "hook": 0.35, "shareability": 0.25},
}


ANGLE_LABELS = {
    "hook": "Attention-Grabbing",
    "education": "Educational",
    "emotion": "Emotional / Story",
    "curiosity": "Curiosity-Driven",
    "shareability": "Highly Shareable",
}


def get_content_angle(clip):
    """Sabse dominant score dimension se ek human-readable content angle nikalta hai."""
    scores = clip.get("scores", {}) or {}
    if not scores:
        return "General"
    top_dimension = max(scores, key=scores.get)
    return ANGLE_LABELS.get(top_dimension, "General")


def platform_fit_score(clip, platform):
    scores = clip.get("scores", {}) or {}
    weights = PLATFORM_SCORE_WEIGHTS.get(platform, {})
    if not weights:
        return clip.get("overall_score", 0)
    return sum(scores.get(dim, 0) * w for dim, w in weights.items())


def main():
    clips_file = PROJECT_ROOT / "output" / "clips.json"
    if not clips_file.exists():
        raise FileNotFoundError(f"Clips file not found: {clips_file}")

    with open(clips_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    shorts_dir = PROJECT_ROOT / "output" / "final_shorts"
    plan = load_plan()

    clips = data["clips"]
    total_requested = sum(p["count"] for p in plan.values())

    if len(clips) < total_requested:
        print(
            f"⚠️  Warning: plan mein total {total_requested} clips maange gaye hain, "
            f"lekin sirf {len(clips)} clips available hain. "
            f"Jitne available hain utne hi allocate honge (jyada demand wale platforms "
            f"ko preference milegi unke fit-score ke hisaab se)."
        )

    used_ids = set()
    items = []
    item_counter = 1
    today = datetime.now()

    for platform, config in plan.items():
        count = config.get("count", 0)
        interval_days = config.get("interval_days", 5)

        candidates = [c for c in clips if c.get("chunk_id") not in used_ids]
        candidates.sort(key=lambda c: platform_fit_score(c, platform), reverse=True)

        selected = candidates[:count]

        for i, clip in enumerate(selected):
            duration = round(clip.get("end", 0) - clip.get("start", 0), 2)
            video_filename = f"chunk_{clip.get('chunk_id')}.mp4"
            scheduled_date = today + timedelta(days=interval_days * i)

            items.append({
                "id": f"clip_{item_counter}",
                "chunk_id": clip.get("chunk_id"),
                "video_file": str(shorts_dir / video_filename),
                "hook": clip.get("hook", ""),
                "summary": clip.get("summary", ""),
                "content_angle": get_content_angle(clip),
                "overall_score": clip.get("overall_score", 0),
                "platform_fit_score": round(platform_fit_score(clip, platform), 2),
                "duration_seconds": duration,
                "assigned_platform": platform,
                "posting_interval_days": interval_days,
                "scheduled_date": scheduled_date.strftime("%Y-%m-%d"),
                "status": "pending",
            })
            
            used_ids.add(clip.get("chunk_id"))
            item_counter += 1

        if len(selected) < count:
            print(
                f"⚠️  {platform}: {count} maange gaye the, sirf {len(selected)} "
                f"allocate ho paye (clips khatam ho gaye)."
            )

    content_bank = {
        "generated_at": today.strftime("%Y-%m-%d %H:%M:%S"),
        "requested_plan": plan,
        "total_requested": total_requested,
        "total_allocated": len(items),
        "items": sorted(items, key=lambda x: x["scheduled_date"]),
    }

    output_file = PROJECT_ROOT / "output" / "content_bank.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(content_bank, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Content bank created: {output_file}")
    for platform, config in plan.items():
        print(f"   {platform}: {config['count']} items, every {config['interval_days']} days")


if __name__ == "__main__":
    main()