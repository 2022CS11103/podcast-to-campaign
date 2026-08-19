"""
Walk the talk in time slices. As soon as enough clips clear the
quality threshold, stop — do not transcribe or score the rest.

That is what makes a 1-hour lecture cheap: we only "watch" until
we have usable Shorts/Reels, then cut those and quit.
"""

import gc
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from concurrent.futures import ThreadPoolExecutor, as_completed

from config.platform_specs import (
    MIN_OVERALL_SCORE,
    USABLE_SCORE_FLOOR,
    SCAN_WINDOW_SECONDS,
    WHISPER_SLICE_SECONDS,
    CANDIDATES_PER_WINDOW,
    MAX_SCAN_SECONDS,
    VIDEO_ANALYSIS_ENABLED,
    video_clip_demand,
    largest_video_count,
)
from utils.content_plan import load_plan, plan_is_usable
from utils.cost_tracker import log_whisper_time
from scripts.pipeline.transcribe_backend import transcribe_wav_file
from scripts.pipeline.chunk_transcript import build_candidates, nms_windows
from scripts.pipeline.clean_transcript import clean_text
from scripts.pipeline.visual_energy import (
    scan_video_window,
    wav_rms_series,
    merge_audio,
    score_span,
    heuristic_boost,
)
from scripts.ai.clip_intelligence import score_chunk
from scripts.ai.clip_ranker import ranking_score, remove_time_overlap

OUTPUT = PROJECT_ROOT / "output"


def video_duration_seconds():
    meta_file = OUTPUT / "metadata.json"
    if meta_file.exists():
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
        try:
            return float((meta.get("format") or {}).get("duration") or 0)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def source_video():
    state_file = PROJECT_ROOT / "memory" / "state.json"
    if state_file.exists():
        with open(state_file, "r", encoding="utf-8") as f:
            path = json.load(f).get("video_path")
        if path:
            p = Path(path)
            if not p.is_absolute():
                p = PROJECT_ROOT / p
            if p.exists():
                return p
    fallback = PROJECT_ROOT / "input" / "video.mp4"
    return fallback if fallback.exists() else None


def clips_needed():
    plan = load_plan(required=False)
    if plan_is_usable(plan):
        n = video_clip_demand(plan)
        largest = largest_video_count(plan)
        if n > 0:
            return n, largest
    return 3, 3


def collect_segments(wav, window_start, duration):
    raw = transcribe_wav_file(wav, duration)
    new_segments = []
    for seg in raw:
        text = clean_text((seg.get("text") or "").strip())
        if not text:
            continue
        new_segments.append({
            "start": round(window_start + float(seg.get("start") or 0), 2),
            "end": round(window_start + float(seg.get("end") or duration), 2),
            "text": text,
        })
    return new_segments


def extract_window(video: Path, start: float, duration: float, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", str(start),
            "-t", str(duration),
            "-i", str(video),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(dest),
        ],
        check=True,
    )


def transcribe_slice(video, start, duration, wav):
    extract_window(video, start, duration, wav)
    rms = wav_rms_series(wav, start, hop=0.5) if VIDEO_ANALYSIS_ENABLED else []
    return collect_segments(wav, start, duration), rms


def transcribe_window(video, start, duration, wav):
    """Whisper/Gemini never sees more than WHISPER_SLICE_SECONDS of audio."""
    segments = []
    rms = []
    offset = 0.0
    while offset < duration - 0.05:
        slice_dur = min(WHISPER_SLICE_SECONDS, duration - offset)
        print(f"  transcribe {start + offset:.0f}s -> {start + offset + slice_dur:.0f}s")
        segs, slice_rms = transcribe_slice(video, start + offset, slice_dur, wav)
        segments.extend(segs)
        rms.extend(slice_rms)
        gc.collect()
        offset += slice_dur
    return segments, rms


def watch_window(video, start, duration):
    if not VIDEO_ANALYSIS_ENABLED:
        return []
    try:
        print(f"  watching picture {start:.0f}s -> {start + duration:.0f}s")
        return scan_video_window(video, start, duration)
    except Exception as exc:
        print(f"  visual scan skipped: {exc}")
        return []


def good_clips(results):
    ranked = sorted(results, key=ranking_score, reverse=True)
    ranked = remove_time_overlap(ranked)
    strong = [c for c in ranked if float(c.get("overall_score") or 0) >= MIN_OVERALL_SCORE]
    usable = [c for c in ranked if float(c.get("overall_score") or 0) >= USABLE_SCORE_FLOOR]
    return strong, usable, ranked


def score_window(to_score):
    """Score candidates in parallel across Gemini keys."""
    if not to_score:
        return []
    scored = [None] * len(to_score)
    workers = min(3, len(to_score))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(score_chunk, cand): i for i, cand in enumerate(to_score)}
        for future in as_completed(future_map):
            i = future_map[future]
            scored[i] = future.result()
            cand = to_score[i]
            print(
                f"  scored clip @ {cand['start']}s "
                f"(heuristic {cand.get('heuristic_score')}, "
                f"visual {cand.get('visual_score')}, audio {cand.get('audio_energy')}) "
                f"-> {scored[i].get('overall_score')} ({scored[i].get('highlight_reason')})"
            )
    return scored


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    video = source_video()
    if video is None:
        raise FileNotFoundError("No source video found for highlight scan.")

    duration = video_duration_seconds()
    if duration <= 0:
        duration = 24 * 3600

    needed, largest = clips_needed()
    print(
        f"Scan-until-good: need {needed} distinct clips >= {MIN_OVERALL_SCORE} "
        f"(stop after {MAX_SCAN_SECONDS}s if {largest}+ highlights exist). "
        f"Video {duration:.0f}s, window {SCAN_WINDOW_SECONDS}s, "
        f"mode={'audio+visual' if VIDEO_ANALYSIS_ENABLED else 'audio'}."
    )

    engine = "whisper-isolated"
    all_segments = []
    all_analysis = []
    chunk_id = 1
    scanned = 0.0
    stopped_early = False
    t0 = time.time()

    start = 0.0
    while start < duration - 2:
        window = min(SCAN_WINDOW_SECONDS, duration - start)
        wav = OUTPUT / "scan_window.wav"
        print(f"\nScanning {start:.0f}s -> {start + window:.0f}s ...")
        w0 = time.time()
        if VIDEO_ANALYSIS_ENABLED:
            with ThreadPoolExecutor(max_workers=2) as pool:
                talk = pool.submit(transcribe_window, video, start, window, wav)
                watch = pool.submit(watch_window, video, start, window)
                new_segments, rms_series = talk.result()
                visual_samples = watch.result()
        else:
            new_segments, rms_series = transcribe_window(video, start, window, wav)
            visual_samples = []
        log_whisper_time(time.time() - w0)
        gc.collect()

        all_segments.extend(new_segments)
        scanned = start + window

        energy_map = merge_audio(visual_samples, rms_series)
        raw = build_candidates(new_segments)
        for cand in raw:
            energy = score_span(energy_map, cand["start"], cand["end"])
            cand["visual_score"] = energy["visual_score"]
            cand["audio_energy"] = energy["audio_energy"]
            cand["visual_signals"] = energy["visual_signals"]
            cand["highlight_reason"] = energy["highlight_reason"]
            cand["heuristic_score"] = round(
                float(cand.get("heuristic_score") or 0) + heuristic_boost(energy),
                2,
            )
        window_chunks = nms_windows(raw)
        window_chunks = sorted(
            window_chunks,
            key=lambda c: c.get("heuristic_score", 0),
            reverse=True,
        )[:CANDIDATES_PER_WINDOW]

        to_score = []
        for cand in window_chunks:
            cand = dict(cand)
            cand["chunk_id"] = chunk_id
            chunk_id += 1
            to_score.append(cand)

        all_analysis.extend(score_window(to_score))

        strong, usable, _ranked = good_clips(all_analysis)
        print(
            f"  so far: {len(strong)} strong (>= {MIN_OVERALL_SCORE}), "
            f"{len(usable)} usable (>= {USABLE_SCORE_FLOOR}) "
            f"(scanned {scanned:.0f}s / {duration:.0f}s)"
        )
        if len(strong) >= needed:
            stopped_early = True
            print("  enough distinct highlights — rest of video skipped.")
            break
        if scanned >= MAX_SCAN_SECONDS and len(strong) >= max(1, largest):
            stopped_early = True
            print(
                f"  first {MAX_SCAN_SECONDS}s already has {len(strong)} strong clip(s) "
                f"(plan peak {largest}) — stopping like an editor who found the package."
            )
            break

        start += window

    elapsed = time.time() - t0
    transcript = " ".join(s["text"] for s in all_segments)
    payload = {
        "language": "en",
        "duration": scanned,
        "source_duration": duration,
        "transcript": transcript,
        "segments": all_segments,
        "whisper_model": engine,
        "analysis_mode": "audio_visual" if VIDEO_ANALYSIS_ENABLED else "audio_first",
        "scan": {
            "stopped_early": stopped_early,
            "scanned_seconds": round(scanned, 1),
            "source_seconds": round(duration, 1),
            "min_score": MIN_OVERALL_SCORE,
            "usable_floor": USABLE_SCORE_FLOOR,
            "needed": needed,
            "visual_analysis": VIDEO_ANALYSIS_ENABLED,
        },
    }
    write_json(OUTPUT / "transcript.json", payload)
    write_json(OUTPUT / "clean_transcript.json", payload)

    chunks = []
    for i, item in enumerate(all_analysis, start=1):
        chunks.append({
            "chunk_id": item.get("chunk_id") or i,
            "start": item["start"],
            "end": item["end"],
            "text": item.get("text", ""),
            "duration_seconds": item.get("duration_seconds"),
            "word_count": item.get("word_count"),
        })
    write_json(OUTPUT / "chunks.json", {**payload, "chunk_count": len(chunks), "chunks": chunks})
    write_json(OUTPUT / "analysis.json", {
        "results": all_analysis,
        "scan_complete": True,
        "stopped_early": stopped_early,
        "analysis_mode": "audio_visual" if VIDEO_ANALYSIS_ENABLED else "audio_first",
    })

    print(
        f"\nScan done in {elapsed:.1f}s. "
        f"Covered {scanned:.0f}s of {duration:.0f}s. "
        f"Early stop={stopped_early}."
    )


if __name__ == "__main__":
    main()
