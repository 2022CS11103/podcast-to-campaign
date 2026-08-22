import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from utils.content_plan import load_plan
from utils.sentences import apply_to_clip
from utils.show_detect import keyword_hits
from config.show_style import load_resolved
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


def remove_time_overlap(results, iou_threshold=0.55):
    """Keep the higher-scoring clip when two windows cover the same moment."""
    unique = []
    for clip in results:
        if any(overlap_ratio(clip, kept) > iou_threshold for kept in unique):
            continue
        unique.append(clip)
    return unique


def ranking_score(clip):
    """
    Blend Gemini overall_score with platform fit, then bias toward the
    show type: laughs for comedy, insight keywords for interviews.
    """
    base = float(clip.get("overall_score", 0))
    duration = float(clip.get("duration_seconds") or (clip.get("end", 0) - clip.get("start", 0)))
    best_fit = max((duration_fit(duration, p) for p in VIDEO_PLATFORMS), default=0.5)
    completeness = (clip.get("scores") or {}).get("completeness", 7)
    score = base * (0.65 + 0.25 * best_fit + 0.10 * (completeness / 10))
    show = load_resolved()
    signals = clip.get("visual_signals") or {}
    if show.get("id") == "comedy":
        if signals.get("laughter") or float(signals.get("reaction_seconds") or 0) >= 0.8:
            score *= 1.22
        if clip.get("highlight_reason") == "audience reaction":
            score *= 1.08
    else:
        hits = keyword_hits(clip.get("text") or "")
        if hits:
            score *= 1.0 + min(0.25, hits * 0.05)
        if (clip.get("hook") or "").strip():
            score *= 1.04
    return score


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


def _energy(clip):
    a = clip.get("audio_energy")
    v = clip.get("visual_score")
    if a is None and v is None:
        return 0.0
    a = 50.0 if a is None else float(a)
    v = 50.0 if v is None else float(v)
    return 0.55 * a + 0.45 * v


def pick_clips(ranked, needed):
    """Take the best unique moments. Never return empty if anything was scored."""
    if not ranked:
        return []
    usable = [
        c for c in ranked
        if float(c.get("overall_score") or 0) >= USABLE_SCORE_FLOOR
        or _energy(c) >= 72
    ]
    pool = usable or ranked
    chosen = []
    seen = set()
    for clip in pool + ranked:
        key = (clip.get("chunk_id"), round(float(clip.get("start") or 0), 1))
        if key in seen:
            continue
        seen.add(key)
        chosen.append(clip)
        if len(chosen) >= max(1, needed):
            break
    print(
        f"Ranker: {len(usable)} usable / {len(ranked)} scored, "
        f"rendering {len(chosen)} unique (asked {needed})."
    )
    return chosen


def main():

    top_k = get_top_k()
    print(f"Selecting top {top_k} unique clips for video render...")

    input_file = PROJECT_ROOT / "output" / "analysis.json"

    if not input_file.exists():
        raise FileNotFoundError(f"Analysis file not found: {input_file}")

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    transcript_file = PROJECT_ROOT / "output" / "transcript.json"
    segments = []
    if transcript_file.exists():
        with open(transcript_file, "r", encoding="utf-8") as f:
            segments = (json.load(f) or {}).get("segments") or []

    ranked = sorted(
        data["results"],
        key=ranking_score,
        reverse=True
    )
    for clip in ranked:
        apply_to_clip(clip, segments)

    ranked = remove_time_overlap(ranked)
    complete = [
        c for c in ranked
        if not c.get("starts_mid_thought")
    ]
    if complete:
        ranked = complete + [c for c in ranked if c.get("starts_mid_thought")]
    strong = [c for c in ranked if float(c.get("overall_score") or 0) >= MIN_OVERALL_SCORE]
    print(f"Scan quality: {len(strong)} clips >= {MIN_OVERALL_SCORE} (early-stop bar).")
    top_clips = pick_clips(ranked, top_k)

    if not top_clips:
        raise RuntimeError(
            "No scored moments to cut. Try another source, or a later section of the talk."
        )

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
Score: {clip.get('overall_score')}  rank={ranking_score(clip):.1f}  words={clip.get('word_score')}  visual={clip.get('visual_score')}  audio={clip.get('audio_energy')}
Why: {clip.get('highlight_reason')}
Time: {clip['start']}s -> {clip['end']}s  ({duration}s)
Hook: {clip.get('hook')}
"""
        )

    print(f"Saved to {output_file}")


if __name__ == "__main__":
    main()
