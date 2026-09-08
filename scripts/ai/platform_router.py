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


def campaign_start():
    """Day one of the calendar: the creator's chosen date, else today."""
    brand_file = PROJECT_ROOT / "brand_context.json"
    if brand_file.exists():
        try:
            with open(brand_file, "r", encoding="utf-8") as f:
                brand = json.load(f) or {}
            raw = (brand.get("campaign_start_date") or "").strip()
            if raw:
                chosen = datetime.strptime(raw[:10], "%Y-%m-%d")
                today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                return max(chosen, today)
        except (OSError, ValueError, TypeError):
            pass
    return datetime.now()


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
    Fill requested count. Prefer unused unique moments first,
    then reuse only if this platform still has empty slots.
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


def overlap_ratio(a, b):
    inter = max(0.0, min(float(a["end"]), float(b["end"])) - max(float(a["start"]), float(b["start"])))
    union = max(float(a["end"]), float(b["end"])) - min(float(a["start"]), float(b["start"]))
    return inter / union if union else 0.0


def assign_distinct_video_slots(clips, plan):
    """
    Round-robin Shorts / Reels / TikTok onto distinct cuts only.

    Never assign the exact same chunk/file twice. Overlapping windows
    from the ranker are fine; byte-identical copies are not.
    """
    platforms = [
        p for p in VIDEO_PLATFORMS
        if p in plan and int(plan[p].get("count", 0)) > 0
    ]
    remaining = {p: int(plan[p]["count"]) for p in platforms}
    used_on = {p: set() for p in platforms}
    assigned_ids = set()
    assigned_clips = []
    picks = {p: [] for p in platforms}

    def _rank(pool, platform):
        return sorted(pool, key=lambda c: platform_fit_score(c, platform), reverse=True)

    def best_for(platform):
        unused_global = [c for c in clips if c.get("chunk_id") not in assigned_ids]
        distinct = [
            c for c in unused_global
            if not any(overlap_ratio(c, picked) > 0.35 for picked in assigned_clips)
        ]
        pool = distinct or unused_global
        if pool:
            return _rank(pool, platform)[0], False
        return None, False

    while any(remaining[p] > 0 for p in platforms):
        progressed = False
        for platform in platforms:
            if remaining[platform] <= 0:
                continue
            clip, _looped = best_for(platform)
            if clip is None:
                continue
            picks[platform].append((clip, False))
            used_on[platform].add(clip.get("chunk_id"))
            assigned_ids.add(clip.get("chunk_id"))
            assigned_clips.append(clip)
            remaining[platform] -= 1
            progressed = True
        if not progressed:
            break

    for platform, left in remaining.items():
        if left > 0:
            print(
                f"   ⚠️  {platform}: {left} slot(s) unfilled — not enough distinct cuts "
                "(refusing to duplicate the exact same Short/Reel)."
            )
    for platform, chosen in picks.items():
        unique_n = len({c.get("chunk_id") for c, _ in chosen})
        print(f"   {platform}: {len(chosen)} slots from {unique_n} distinct moments")
    ids = {p: {c.get("chunk_id") for c, _ in chosen} for p, chosen in picks.items()}
    if "youtube_shorts" in ids and "instagram_reels" in ids:
        overlap = ids["youtube_shorts"] & ids["instagram_reels"]
        if overlap:
            print(
                f"   ⚠️  Shorts and Reels share moment(s) {sorted(overlap)} "
                "because there were not enough unique cuts in the talk."
            )
        else:
            print("   Shorts and Reels use different moments of the source video.")
    return picks


def editor_note(clip, platform, reused):
    spec = PLATFORM_SPECS.get(platform, {})
    label = spec.get("label", platform.replace("_", " ").title())
    hook = clip.get("hook") or "this beat"
    if reused:
        return (
            f"Later {label} slot: same talk, new calendar date. "
            f"We already posted \"{hook}\" once here, so this is a scheduled remix — "
            f"not a copy-paste of the other platform's first drop."
        )
    return (
        f"Editor pick for {label}: \"{hook}\" "
        f"({clip.get('duration_seconds')}s, score {clip.get('overall_score')}) "
        f"— {spec.get('why', 'best fit for this platform.')}"
    )


def review_reasons(clip: dict) -> list:
    """Short human-readable why-this-clip tags for the HITL review board."""
    tags = []
    scores = clip.get("scores") or {}
    if isinstance(scores, dict):
        ranked = sorted(
            ((k, float(v or 0)) for k, v in scores.items() if isinstance(v, (int, float))),
            key=lambda pair: pair[1],
            reverse=True,
        )
        dim_map = {
            "hook": "hook in first seconds",
            "education": "standalone teaching moment",
            "emotion": "emotional peak",
            "curiosity": "curiosity gap",
            "shareability": "highly shareable line",
        }
        for key, value in ranked[:2]:
            if value >= 6 and key in dim_map:
                tags.append(dim_map[key])

    highlight = (clip.get("highlight_reason") or "").strip()
    if highlight and highlight.lower() not in {t.lower() for t in tags}:
        tags.append(highlight[:80])

    text = (clip.get("text") or "").strip()
    if "?" in text[:280] and "conversation / Q&A beat" not in tags:
        tags.append("conversation / Q&A beat")

    overall = float(clip.get("overall_score") or 0)
    if overall >= 75:
        tags.append("top-scored moment")
    elif overall >= 60:
        tags.append("strong overall score")

    angle = get_content_angle(clip)
    if angle and angle.lower() not in " ".join(tags).lower():
        tags.append(angle)

    deduped = []
    seen = set()
    for tag in tags:
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(tag)
        if len(deduped) >= 5:
            break
    return deduped or ["AI-selected highlight"]


def transcript_excerpt(clip: dict, limit: int = 280) -> str:
    text = (clip.get("text") or clip.get("summary") or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return f"{cut}…"


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
    today = campaign_start()

    video_picks = assign_distinct_video_slots(clips, plan)
    ordered_platforms = [p for p in plan.keys() if p in VIDEO_PLATFORMS]
    ordered_platforms += [p for p in plan.keys() if p not in VIDEO_PLATFORMS]

    for platform, config in ((p, plan[p]) for p in ordered_platforms):
        count = int(config.get("count", 0))
        interval_days = int(config.get("interval_days", PLATFORM_SPECS.get(platform, {}).get("posting_cadence_days", 5)))
        is_video = platform in VIDEO_PLATFORMS

        if is_video:
            selected_pairs = video_picks.get(platform) or []
            selected = [c for c, _ in selected_pairs]
            reuse_flags = [r for _, r in selected_pairs]
        else:
            selected = fill_platform_slots(clips, count, platform, set())
            reuse_flags = [False] * len(selected)

        for i, clip in enumerate(selected):
            duration = round(
                float(clip.get("duration_seconds") or (clip.get("end", 0) - clip.get("start", 0))),
                2,
            )
            video_filename = clip_video_filename(clips, clip.get("chunk_id"))
            source_video = shorts_dir / video_filename if video_filename else shorts_dir / "missing.mp4"
            scheduled_date = today + timedelta(days=interval_days * i)
            reused = reuse_flags[i] if i < len(reuse_flags) else False

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
                "status": "ai_generated",
                "active_variant": "A",
                "variants": [],
                "performance": empty_performance(),
                "repost_count": 0,
                "parent_id": None,
                "reused_render": reused,
                "editor_note": editor_note(clip, platform, reused),
                "word_score": clip.get("word_score"),
                "visual_score": clip.get("visual_score"),
                "audio_energy": clip.get("audio_energy"),
                "highlight_reason": clip.get("highlight_reason"),
                "review_reasons": review_reasons(clip),
                "transcript_excerpt": transcript_excerpt(clip),
                "detected_topic": get_content_angle(clip),
            })

            if is_video and clip.get("chunk_id") not in used_ids:
                used_ids.add(clip.get("chunk_id"))
            item_counter += 1

        if len(selected) < count:
            print(
                f"⚠️  {platform}: {count} requested, {len(selected)} allocated."
            )

    content_bank = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "campaign_start_date": today.strftime("%Y-%m-%d"),
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
