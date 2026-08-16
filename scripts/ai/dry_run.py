"""
Fast local try of the new content-factory files.

Skips YouTube download, Whisper, YOLO, and ffmpeg. Uses a short sample
lecture transcript + heuristic scores so you can inspect chunks, ranking,
the calendar, and the A/B/repost loop before running a real /process job.
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.pipeline.chunk_transcript import build_candidates, nms_windows
from config.platform_specs import MAX_ANALYZED_CANDIDATES, CANDIDATE_TARGET_SECONDS
from scripts.ai.ab_engine import record_performance, list_winners, schedule_repost
from utils.content_plan import save_plan


SAMPLE_SENTENCES = [
    ("Most people get this wrong when they launch a course.", 4.2),
    ("They teach everything in module one and the student never comes back.", 5.1),
    ("Here is the framework I use with founders.", 3.8),
    ("First you need a tight promise in one sentence.", 4.0),
    ("Second you need proof that the method actually works.", 4.4),
    ("Third you need one simple call to action, not five.", 4.6),
    ("If you do not do this your ads will waste money.", 3.9),
    ("Let me show you a real example from last week.", 3.5),
    ("The biggest mistake is confusing information with transformation.", 5.0),
    ("Write this down: one outcome per lesson.", 3.6),
    ("When you nail that, completion rates jump.", 3.2),
    ("So the question is, what is the single outcome of lesson one?", 4.1),
    ("Stop dumping slides. Start designing a win in the first twenty minutes.", 5.3),
    ("That win is what they screenshot and send to a friend.", 4.0),
    ("And that screenshot is how your course actually sells.", 3.7),
]


def sample_segments():
    t = 0.0
    segs = []
    for text, dur in SAMPLE_SENTENCES * 4:
        segs.append({"start": round(t, 2), "end": round(t + dur, 2), "text": text})
        t += dur
    return segs


def heuristic_to_analysis(chunk):
    h = float(chunk.get("heuristic_score") or 0)
    overall = min(95, int(50 + h * 8))
    return {
        "chunk_id": chunk["chunk_id"],
        "start": chunk["start"],
        "end": chunk["end"],
        "duration_seconds": chunk["duration_seconds"],
        "target_duration": chunk.get("target_duration"),
        "fits_platforms": chunk.get("fits_platforms", []),
        "word_count": chunk["word_count"],
        "text": chunk["text"],
        "summary": chunk["text"][:140],
        "hook": " ".join(chunk["text"].split()[:8]),
        "reason": "Dry-run heuristic stand-in for Gemini scoring.",
        "best_platform": "YouTube Shorts",
        "overall_score": overall,
        "starts_mid_thought": False,
        "payoff_arrives": True,
        "scores": {
            "hook": min(10, 5 + h),
            "education": 8,
            "emotion": 6,
            "curiosity": min(10, 4 + h),
            "shareability": 7,
            "completeness": 8,
        },
    }


def main():
    output = PROJECT_ROOT / "output"
    output.mkdir(exist_ok=True)

    segments = sample_segments()
    raw = build_candidates(segments)
    suppressed = nms_windows(raw)
    selected = sorted(suppressed, key=lambda c: c["heuristic_score"], reverse=True)
    selected = selected[:MAX_ANALYZED_CANDIDATES]
    selected.sort(key=lambda c: c["start"])
    chunks = [{"chunk_id": i, **c} for i, c in enumerate(selected, start=1)]

    clean = {
        "language": "en",
        "duration": segments[-1]["end"],
        "transcript": " ".join(s["text"] for s in segments),
        "segments": segments,
        "chunk_count": len(chunks),
        "chunks": chunks,
    }
    (output / "clean_transcript.json").write_text(json.dumps(clean, indent=2), encoding="utf-8")
    (output / "chunks.json").write_text(json.dumps(clean, indent=2), encoding="utf-8")
    (output / "analysis.json").write_text(
        json.dumps({"results": [heuristic_to_analysis(c) for c in chunks]}, indent=2),
        encoding="utf-8",
    )

    save_plan({
        "instagram_reels": {"count": 2, "interval_days": 3},
        "youtube_shorts": {"count": 2, "interval_days": 3},
        "linkedin": {"count": 2, "interval_days": 7},
        "twitter": {"count": 2, "interval_days": 4},
    })

    from scripts.ai.clip_ranker import main as rank
    from scripts.ai.platform_router import main as route
    from scripts.ai.campaign_planner import main as calendar
    from scripts.ai.package_manifest import main as manifest

    rank()
    route()
    calendar()
    manifest()

    # Fake a winner so /winners and /repost can be tried next.
    record_performance("clip_1", {"views": 1200, "likes": 80, "comments": 12, "shares": 9}, variant_id="A")
    winners = list_winners()
    repost = schedule_repost("clip_1") if winners else None

    print("\n=== DRY RUN OK ===")
    print(f"Candidates analyzed: {len(chunks)}  (targets {CANDIDATE_TARGET_SECONDS})")
    print(f"Look in: {output}")
    print("  chunks.json, clips.json, content_bank.json,")
    print("  campaign_calendar.md, package_manifest.json")
    print(f"Winners: {[w['id'] for w in winners]}")
    if repost:
        print(f"Repost queued: {repost['id']} on {repost['scheduled_date']} -> {repost['assigned_platform']}")
    print("\nThis did NOT cut video. When the JSON looks right, run a real job:")
    print("  python run_pipeline.py")
    print("  or POST /process with a YouTube URL / mp4 path")


if __name__ == "__main__":
    main()
