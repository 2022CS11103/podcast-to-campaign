import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from utils.content_plan import load_plan
from utils.sentences import apply_to_clip, trim_to_max_duration
from utils.show_detect import keyword_hits
from config.show_style import load_resolved
from config.platform_specs import (
    video_clip_demand,
    duration_fit,
    VIDEO_PLATFORMS,
    MIN_OVERALL_SCORE,
    USABLE_SCORE_FLOOR,
    MASTER_CLIP_MAX_SECONDS,
)


def overlap_ratio(a, b):
    inter = max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
    union = max(a["end"], b["end"]) - min(a["start"], b["start"])
    return inter / union if union else 0.0


def _too_similar(clip, others, iou_threshold=0.35):
    return any(overlap_ratio(clip, other) > iou_threshold for other in others)


def remove_time_overlap(results, iou_threshold=0.45):
    """Keep the higher-scoring clip when two windows cover the same moment."""
    unique = []
    for clip in results:
        if any(overlap_ratio(clip, kept) > iou_threshold for kept in unique):
            continue
        unique.append(clip)
    return unique


def virality_breakdown(clip):
    """Hook / emotion / info / completeness / picture / sound — 0 to 1, then a total."""
    scores = clip.get("scores") or {}

    def _ten(key, default=5):
        try:
            return min(1.0, max(0.0, float(scores.get(key, default)) / 10.0))
        except (TypeError, ValueError):
            return default / 10.0

    try:
        overall = min(1.0, max(0.0, float(clip.get("overall_score") or 0) / 100.0))
    except (TypeError, ValueError):
        overall = 0.0
    duration = float(clip.get("duration_seconds") or (clip.get("end", 0) - clip.get("start", 0)))
    fit = max((duration_fit(duration, p) for p in VIDEO_PLATFORMS), default=0.5)
    visual = min(1.0, max(0.0, float(clip.get("visual_score") or 50) / 100.0))
    audio = min(1.0, max(0.0, float(clip.get("audio_energy") or 50) / 100.0))
    hook = _ten("hook")
    emotion = _ten("emotion")
    info = max(_ten("education"), _ten("curiosity"))
    complete = _ten("completeness")
    social = _ten("shareability")
    total = (
        100.0 * overall * (0.55 + 0.20 * fit + 0.10 * complete)
        + 8.0 * hook
        + 5.0 * emotion
        + 4.0 * info
        + 3.0 * social
        + 2.0 * visual
        + 2.0 * audio
    )
    return {
        "hook": round(hook, 3),
        "emotion": round(emotion, 3),
        "info": round(info, 3),
        "completeness": round(complete, 3),
        "visual": round(visual, 3),
        "audio": round(audio, 3),
        "social": round(social, 3),
        "total": round(total, 2),
    }


def ranking_score(clip):
    """
    Blend Gemini overall_score with platform fit, then bias toward the
    show type: laughs for comedy, insight keywords for interviews.
    """
    breakdown = virality_breakdown(clip)
    clip["virality"] = breakdown
    score = breakdown["total"]
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
    """Take the best moments with distinct start times. Overlap OK; exact dupes not."""
    if not ranked:
        return []
    usable = [
        c for c in ranked
        if float(c.get("overall_score") or 0) >= USABLE_SCORE_FLOOR
        or _energy(c) >= 72
    ]
    chosen = []
    seen = set()
    for clip in (usable or ranked) + ranked:
        key = (clip.get("chunk_id"), round(float(clip.get("start") or 0), 1))
        if key in seen:
            continue
        seen.add(key)
        chosen.append(clip)
        if len(chosen) >= max(1, needed):
            break
    print(
        f"Ranker: {len(usable)} usable / {len(ranked)} scored, "
        f"picked {len(chosen)} distinct windows (asked {needed})."
    )
    return chosen


def _source_duration_seconds():
    meta = PROJECT_ROOT / "output" / "metadata.json"
    if not meta.exists():
        return None
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        return float((data.get("format") or {}).get("duration") or 0) or None
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def clip_is_complete(c):
    if c.get("conversation_complete") is True:
        return True
    if c.get("ends_on_question"):
        return False
    if c.get("conversation_complete") is False:
        return False
    if c.get("payoff_arrives") is False:
        return False
    completeness = (c.get("scores") or {}).get("completeness")
    if completeness is not None and completeness < 5:
        return False
    return True


def clip_sort_key(c):
    complete = clip_is_complete(c)
    mid = bool(c.get("starts_mid_thought"))
    score = float(c.get("overall_score") or 0)
    return (complete, not mid, score)


def fill_clip_slots(clips, needed):
    """Prefer complete conversational clips, but always fill the render quota."""
    ordered = sorted(clips, key=clip_sort_key, reverse=True)
    out = []
    seen = set()
    for clip in ordered:
        key = clip.get("chunk_id")
        if key in seen:
            continue
        seen.add(key)
        out.append(clip)
        if len(out) >= max(1, needed):
            break
    return out


def expand_with_alternate_windows(clips, needed, source_duration=None, segments=None):
    """Fill remaining demand with shifted windows snapped to sentence edges."""
    if not clips or len(clips) >= needed:
        return list(clips[:needed]) if clips else []

    out = [dict(c) for c in clips]
    seen_starts = {round(float(c.get("start") or 0), 1) for c in out}
    try:
        next_id = max(int(c.get("chunk_id") or 0) for c in out) + 1000
    except (TypeError, ValueError):
        next_id = 1000

    offsets = (5.0, -5.0, 9.0, -9.0, 14.0, -14.0, 20.0, -20.0, 7.0, -7.0, 11.0, -11.0)
    guard = 0
    while len(out) < needed and guard < needed * len(offsets) * max(1, len(clips)):
        guard += 1
        base = clips[(guard - 1) % len(clips)]
        shift = offsets[(guard - 1) % len(offsets)]
        start = float(base.get("start") or 0) + shift
        end = float(base.get("end") or 0) + shift
        if start < 0:
            end -= start
            start = 0.0
        if source_duration and end > source_duration:
            delta = end - source_duration
            start = max(0.0, start - delta)
            end = source_duration
        variant = dict(base)
        variant["chunk_id"] = next_id
        next_id += 1
        variant["start"] = round(start, 2)
        variant["end"] = round(end, 2)
        if segments:
            apply_to_clip(variant, segments, max_duration=MASTER_CLIP_MAX_SECONDS)
            start = float(variant.get("start") or 0)
            end = float(variant.get("end") or 0)
        duration = end - start
        if duration < 12:
            continue
        if variant.get("starts_mid_thought"):
            continue
        key = round(start, 1)
        if key in seen_starts:
            continue
        if any(abs(key - s) < 2.0 for s in seen_starts):
            continue
        if _too_similar(variant, out):
            continue
        seen_starts.add(key)
        variant["duration_seconds"] = round(duration, 2)
        variant["alternate_window"] = True
        variant["variant_of"] = base.get("chunk_id")
        reason = (base.get("highlight_reason") or "highlight").strip()
        variant["highlight_reason"] = f"{reason} (alternate window)"
        out.append(variant)

    if len(out) < needed:
        print(
            f"⚠️  Only {len(out)} distinct windows available for {needed} slots "
            "(source too short to shift further)."
        )
    else:
        print(f"Expanded to {len(out)} distinct windows (overlap allowed, no exact copies).")
    return out


def main():

    top_k = get_top_k()
    print(f"Selecting top {top_k} distinct clips for video render...")

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

    ranked_all = sorted(
        data["results"],
        key=ranking_score,
        reverse=True
    )
    for clip in ranked_all:
        apply_to_clip(clip, segments, max_duration=MASTER_CLIP_MAX_SECONDS)

    diverse = remove_time_overlap(ranked_all)
    complete = [
        c for c in diverse
        if not c.get("starts_mid_thought") and clip_is_complete(c)
    ]
    if complete:
        diverse = complete + [
            c for c in diverse
            if c.get("starts_mid_thought") or not clip_is_complete(c)
        ]
    strong = [c for c in diverse if float(c.get("overall_score") or 0) >= MIN_OVERALL_SCORE]
    print(f"Scan quality: {len(strong)} clips >= {MIN_OVERALL_SCORE} (early-stop bar).")

    # Prefer diverse moments first, then overlapping analysis hits, then
    # synthesize shifted windows so we never ship identical Shorts.
    top_clips = pick_clips(diverse, top_k)
    if len(top_clips) < top_k:
        top_clips = pick_clips(ranked_all, top_k)
    for clip in top_clips:
        apply_to_clip(clip, segments, max_duration=MASTER_CLIP_MAX_SECONDS)
    top_clips = fill_clip_slots(top_clips, top_k)
    if len(top_clips) < top_k:
        top_clips = expand_with_alternate_windows(
            top_clips, top_k, source_duration=_source_duration_seconds(), segments=segments
        )
        for clip in top_clips:
            apply_to_clip(clip, segments, max_duration=MASTER_CLIP_MAX_SECONDS)
        top_clips = fill_clip_slots(top_clips, top_k)
    complete_n = sum(1 for c in top_clips if clip_is_complete(c))
    print(f"Selected {len(top_clips)} render(s) ({complete_n} conversation-complete).")

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
Score: {clip.get('overall_score')}  rank={ranking_score(clip):.1f}  virality={clip.get('virality', {}).get('total')}  words={clip.get('word_score')}  visual={clip.get('visual_score')}  audio={clip.get('audio_energy')}
Why: {clip.get('highlight_reason')}
Time: {clip['start']}s -> {clip['end']}s  ({duration}s)
Hook: {clip.get('hook')}
"""
        )

    print(f"Saved to {output_file}")


if __name__ == "__main__":
    main()
