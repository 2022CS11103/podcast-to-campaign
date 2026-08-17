import json
import shutil
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
import sys
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from utils.content_plan import load_plan
from config.platform_specs import (
    VIDEO_PLATFORMS,
    PLATFORM_SPECS,
    duration_fit,
    video_clip_demand,
    video_slot_demand,
)

VIDEO_PLATFORM_FOLDERS = {
    "youtube_shorts": "youtube_shorts",
    "instagram_reels": "instagram_reels",
    "tiktok": "tiktok",
}


PLATFORM_SCORE_WEIGHTS = {
    "instagram_reels": {"hook": 0.4, "shareability": 0.35, "curiosity": 0.25},
    "youtube_shorts":  {"hook": 0.35, "shareability": 0.3, "curiosity": 0.2, "emotion": 0.15},
    "tiktok":          {"hook": 0.45, "curiosity": 0.3, "shareability": 0.25},
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
    scores = clip.get("scores", {}) or {}
    if not scores:
        return "General"
    top_dimension = max(scores, key=scores.get)
    return ANGLE_LABELS.get(top_dimension, "General")


def platform_fit_score(clip, platform):
    scores = clip.get("scores", {}) or {}
    weights = PLATFORM_SCORE_WEIGHTS.get(platform, {})
    duration = float(clip.get("duration_seconds") or (clip.get("end", 0) - clip.get("start", 0)))
    length_fit = duration_fit(duration, platform)
    if not weights:
        return float(clip.get("overall_score", 0)) * (0.7 + 0.3 * length_fit)
    weighted = sum(scores.get(dim, 0) * w for dim, w in weights.items())
    # Length mismatch should almost veto video platforms.
    if platform in VIDEO_PLATFORMS and length_fit == 0:
        return weighted * 0.15
    return weighted * (0.6 + 0.4 * length_fit)


def clip_video_filename(clips, chunk_id):
    """video_cutter.py names files short_1.mp4 in clips.json order."""
    for i, clip in enumerate(clips, start=1):
        if clip.get("chunk_id") == chunk_id:
            return f"short_{i}.mp4"
    return None


def copy_to_platform_folder(source_video: Path, platform: str, dest_name: str):
    folder_name = VIDEO_PLATFORM_FOLDERS.get(platform)
    if not folder_name:
        return None
    if not source_video.exists():
        print(f"⚠️  Source video not found, skipping copy: {source_video}")
        return None
    dest_dir = PROJECT_ROOT / "output" / folder_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / dest_name
    shutil.copy2(str(source_video), str(dest_path))
    return str(dest_path)


def fill_platform_slots(clips, count, platform, used_ids):
    """
    Fill the requested count. Prefer unused unique moments first,
    then reuse (same render, different scheduled post / caption).
    """
    if count <= 0 or not clips:
        return []
    unused = [c for c in clips if c.get("chunk_id") not in used_ids]
    reused = [c for c in clips if c.get("chunk_id") in used_ids]
    unused.sort(key=lambda c: platform_fit_score(c, platform), reverse=True)
    reused.sort(key=lambda c: platform_fit_score(c, platform), reverse=True)
    pool = unused + reused
    selected = [pool[i % len(pool)] for i in range(count)]
    fresh = min(count, len(unused))
    copies = count - fresh
    if copies:
        print(f"   {platform}: {fresh} unique + {copies} reused copy to fill {count}")
    else:
        print(f"   {platform}: {count} unique clip(s)")
    return selected


def empty_performance():
    return {
        "impressions": 0,
        "views": 0,
        "likes": 0,
        "comments": 0,
        "shares": 0,
        "ctr": 0.0,
        "engagement_rate": 0.0,
    }


def main():
    clips_file = PROJECT_ROOT / "output" / "clips.json"
    if not clips_file.exists():
        raise FileNotFoundError(f"Clips file not found: {clips_file}")

    with open(clips_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    shorts_dir = PROJECT_ROOT / "output" / "final_shorts"
    plan = load_plan(required=True)
    clips = data["clips"]
    unique_renders = video_clip_demand(plan)
    video_needed = video_slot_demand(plan)

    used_ids = set()
    items = []
    item_counter = 1
    today = datetime.now()

    # Video platforms share the same unique renders (copy, don't re-encode).
    ordered_platforms = [p for p in plan.keys() if p in VIDEO_PLATFORMS]
    ordered_platforms += [p for p in plan.keys() if p not in VIDEO_PLATFORMS]

    for platform, config in ((p, plan[p]) for p in ordered_platforms):
        count = int(config.get("count", 0))
        interval_days = int(config.get("interval_days", PLATFORM_SPECS.get(platform, {}).get("posting_cadence_days", 5)))
        is_video = platform in VIDEO_PLATFORMS

        if is_video:
            selected = fill_platform_slots(clips, count, platform, used_ids)
        else:
            # Text posts reuse the same insights on a calendar — fill the
            # requested count even if we only found one strong moment.
            selected = fill_platform_slots(clips, count, platform, set())

        for i, clip in enumerate(selected):
            duration = round(
                float(clip.get("duration_seconds") or (clip.get("end", 0) - clip.get("start", 0))),
                2,
            )
            video_filename = clip_video_filename(clips, clip.get("chunk_id"))
            source_video = shorts_dir / video_filename if video_filename else shorts_dir / "missing.mp4"
            scheduled_date = today + timedelta(days=interval_days * i)

            platform_video_path = None
            if is_video and video_filename:
                dest_name = f"{VIDEO_PLATFORM_FOLDERS[platform]}_{i + 1}.mp4"
                platform_video_path = copy_to_platform_folder(
                    source_video, platform, dest_name
                )

            spec = PLATFORM_SPECS.get(platform, {})
            items.append({
                "id": f"clip_{item_counter}",
                "chunk_id": clip.get("chunk_id"),
                "video_file": str(source_video) if is_video else None,
                "platform_video_file": platform_video_path,
                "hook": clip.get("hook", ""),
                "summary": clip.get("summary", ""),
                "content_angle": get_content_angle(clip),
                "overall_score": clip.get("overall_score", 0),
                "platform_fit_score": round(platform_fit_score(clip, platform), 2),
                "duration_seconds": duration,
                "duration_spec": {
                    "min_seconds": spec.get("min_seconds"),
                    "ideal_seconds": spec.get("ideal_seconds"),
                    "max_seconds": spec.get("max_seconds"),
                    "why": spec.get("why"),
                },
                "assigned_platform": platform,
                "posting_interval_days": interval_days,
                "scheduled_date": scheduled_date.strftime("%Y-%m-%d"),
                "status": "pending",
                "active_variant": "A",
                "variants": [],
                "performance": empty_performance(),
                "repost_count": 0,
                "parent_id": None,
            })

            if is_video and clip.get("chunk_id") not in used_ids:
                used_ids.add(clip.get("chunk_id"))
            item_counter += 1

        if len(selected) < count:
            print(
                f"⚠️  {platform}: {count} requested, {len(selected)} allocated."
            )

    content_bank = {
        "generated_at": today.strftime("%Y-%m-%d %H:%M:%S"),
        "requested_plan": plan,
        "total_requested": sum(int(p.get("count", 0)) for p in plan.values()),
        "video_renders": unique_renders,
        "video_slots": video_needed,
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
