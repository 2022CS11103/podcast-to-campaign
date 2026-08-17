import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from utils.content_plan import load_plan
from config.platform_specs import (
    video_clip_demand,
    duration_fit,
    VIDEO_PLATFORMS,
    MIN_OVERALL_SCORE,
    USABLE_SCORE_FLOOR,
)


def overlap_ratio(a, b):
    inter = max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
    union = max(a["end"], b["end"]) - min(a["start"], b["start"])
    return inter / union if union else 0.0


def remove_time_overlap(results, iou_threshold=0.45):
    """Keep the higher-scoring clip when two windows cover the same moment."""
    unique = []
    for clip in results:
        if any(overlap_ratio(clip, kept) > iou_threshold for kept in unique):
            continue
        unique.append(clip)
    return unique


def ranking_score(clip):
    """
    Blend Gemini overall_score with whether the length actually fits
    a short-form platform. A brilliant 90s monologue is a blog, not a Reel.
    """
    base = float(clip.get("overall_score", 0))
    duration = float(clip.get("duration_seconds") or (clip.get("end", 0) - clip.get("start", 0)))
    best_fit = max((duration_fit(duration, p) for p in VIDEO_PLATFORMS), default=0.5)
    completeness = (clip.get("scores") or {}).get("completeness", 7)
    return base * (0.65 + 0.25 * best_fit + 0.10 * (completeness / 10))


def get_top_k():
    """
    Unique renders = Shorts + Reels + TikTok slots, capped.
    Router then assigns distinct moments round-robin so platforms
    do not all open with the same file.
    """
    plan = load_plan(required=True)
    video_needed = video_clip_demand(plan)
    if video_needed <= 0:
        total = 0
        for config in plan.values():
            if isinstance(config, dict):
                try:
                    total += int(config.get("count", 0))
                except (TypeError, ValueError):
                    pass
        return max(1, min(total, 3))
    return video_needed


def pick_clips(ranked, needed):
    """Take the best unique moments. Soft floor, not a hard 72 veto."""
    usable = [
        c for c in ranked
        if float(c.get("overall_score") or 0) >= USABLE_SCORE_FLOOR
    ]
    if usable:
        chosen = usable[:needed]
        print(
            f"Ranker: {len(usable)} clips >= {USABLE_SCORE_FLOOR}, "
            f"rendering top {len(chosen)} unique (asked {needed})."
        )
        return chosen
    if ranked:
        print(
            f"Ranker: none reached {USABLE_SCORE_FLOOR}. "
            f"Keeping the single best (score {ranked[0].get('overall_score')})."
        )
        return ranked[:1]
    print("Ranker: no scored clips at all.")
    return []


def main():

    top_k = get_top_k()
    print(f"Selecting top {top_k} unique clips for video render...")

    input_file = PROJECT_ROOT / "output" / "analysis.json"

    if not input_file.exists():
        raise FileNotFoundError(f"Analysis file not found: {input_file}")

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    ranked = sorted(
        data["results"],
        key=ranking_score,
        reverse=True
    )

    ranked = remove_time_overlap(ranked)
    strong = [c for c in ranked if float(c.get("overall_score") or 0) >= MIN_OVERALL_SCORE]
    print(f"Scan quality: {len(strong)} clips >= {MIN_OVERALL_SCORE} (early-stop bar).")
    top_clips = pick_clips(ranked, top_k)

    output = {
        "total_selected": len(top_clips),
        "clips": top_clips
    }

    output_file = PROJECT_ROOT / "output" / "clips.json"
    output_file.parent.mkdir(exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4, ensure_ascii=False)

    print("\n========== TOP CLIPS ==========")

    for clip in top_clips:
        duration = clip.get("duration_seconds", round(clip["end"] - clip["start"], 1))
        print(
            f"""
Chunk: {clip['chunk_id']}
Score: {clip.get('overall_score')}  rank={ranking_score(clip):.1f}
Time: {clip['start']}s -> {clip['end']}s  ({duration}s)
Hook: {clip.get('hook')}
"""
        )

    print(f"\n✅ Saved to {output_file}")


if __name__ == "__main__":
    main()
