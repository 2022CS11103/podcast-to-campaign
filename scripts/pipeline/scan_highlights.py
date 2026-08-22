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
    SCAN_OVERLAP_SECONDS,
    CANDIDATES_PER_WINDOW,
    MAX_SCAN_SECONDS,
    HARD_MAX_SCAN_SECONDS,
    VIDEO_ANALYSIS_ENABLED,
    video_clip_demand,
    largest_video_count,
)
from utils.content_plan import load_plan, plan_is_usable
from utils.cost_tracker import log_whisper_time
from scripts.pipeline.transcribe_backend import close_worker, transcribe_wav_file
from scripts.pipeline.chunk_transcript import build_candidates, nms_windows
from utils.sentences import apply_to_clip
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
from utils.show_detect import detect_show, laughter_in_span

OUTPUT = PROJECT_ROOT / "output"
STOP_FLAG = OUTPUT / "job_stop.json"
PROGRESS_FILE = OUTPUT / "scan_progress.json"


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


def stop_request():
    """Cooperative cancel written by POST /jobs/{id}/stop."""
    if not STOP_FLAG.exists():
        return None
    try:
        data = json.loads(STOP_FLAG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "finish_current"
    return data.get("mode") or "finish_current"


def write_progress(**kwargs):
    payload = {"updated_at": time.time()}
    if PROGRESS_FILE.exists():
        try:
            payload.update(json.loads(PROGRESS_FILE.read_text(encoding="utf-8")) or {})
        except (OSError, ValueError):
            pass
    payload.update(kwargs)
    write_json(PROGRESS_FILE, payload)


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
        words = []
        for word in seg.get("words") or []:
            token = (word.get("word") or "").strip()
            if not token:
                continue
            words.append({
                "word": token,
                "start": round(window_start + float(word.get("start") or 0), 2),
                "end": round(window_start + float(word.get("end") or 0), 2),
            })
        row = {
            "start": round(window_start + float(seg.get("start") or 0), 2),
            "end": round(window_start + float(seg.get("end") or duration), 2),
            "text": text,
        }
        # Word timings drive caption cues and jump-cut gaps when Whisper
        # supplies them; the Gemini audio fallback does not.
        if words:
            row["words"] = words
        new_segments.append(row)
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


def transcribe_window(video, start, duration, wav):
    """One extract + one Whisper call for the whole window.

    The worker process keeps the model loaded, so repeating 15-second
    slices was wasting minutes on model startup rather than speech.
    """
    print(f"  transcribe {start:.0f}s -> {start + duration:.0f}s")
    write_progress(
        stage="transcript",
        label=f"Scoring chunk {int(start)}s–{int(start + duration)}s",
        scanned_seconds=round(start, 1),
        max_scan_seconds=HARD_MAX_SCAN_SECONDS,
    )
    extract_window(video, start, duration, wav)
    rms = wav_rms_series(wav, start, hop=0.4)
    segments = collect_segments(wav, start, duration)
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
        f"Chunk scan: take {int(SCAN_WINDOW_SECONDS)}s, score it, repeat until "
        f"{needed} clips. Weak opening? keep walking (hard cap {int(HARD_MAX_SCAN_SECONDS / 60)} min)."
    )

    engine = "whisper-isolated"
    all_segments = []
    all_analysis = []
    all_rms = []
    chunk_id = 1
    scanned = 0.0
    stopped_early = False
    t0 = time.time()

    start = 0.0
    while start < duration - 2:
        if stop_request():
            stopped_early = True
            print("  stop requested — packaging whatever highlights we already have.")
            break
        needed, largest = clips_needed()
        window = min(SCAN_WINDOW_SECONDS, duration - start)
        wav = OUTPUT / "scan_window.wav"
        print(f"\nScanning {start:.0f}s -> {start + window:.0f}s ...")
        write_progress(
            stage="transcript",
            label=f"Chunk {int(start / SCAN_WINDOW_SECONDS) + 1}: scoring {int(start)}s–{int(start + window)}s, then skip the rest if it is enough",
            scanned_seconds=round(start, 1),
        max_scan_seconds=HARD_MAX_SCAN_SECONDS,
            source_seconds=round(duration, 1),
            needed=needed,
        )
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

        if all_segments and new_segments:
            cutoff = float(all_segments[-1].get("end") or 0) - 0.25
            new_segments = [s for s in new_segments if float(s.get("start") or 0) >= cutoff]
        all_segments.extend(new_segments)
        all_rms.extend(rms_series)
        scanned = start + window

        energy_map = merge_audio(visual_samples, rms_series)
        raw = build_candidates(all_segments)
        raw = [
            cand for cand in raw
            if float(cand.get("start") or 0) >= start - 0.5
        ]
        for cand in raw:
            energy = score_span(energy_map, cand["start"], cand["end"])
            laughed, tail = laughter_in_span(
                rms_series, cand["start"], cand["end"], new_segments,
            )
            signals = dict(energy.get("visual_signals") or {})
            signals["laughter"] = laughed
            signals["reaction_seconds"] = tail
            cand["visual_score"] = energy["visual_score"]
            cand["audio_energy"] = energy["audio_energy"]
            cand["visual_signals"] = signals
            cand["highlight_reason"] = (
                "audience reaction" if laughed else energy["highlight_reason"]
            )
            boost = 2.8 if laughed else 0.0
            cand["heuristic_score"] = round(
                float(cand.get("heuristic_score") or 0) + heuristic_boost(energy) + boost,
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
            apply_to_clip(cand, all_segments)
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
        write_progress(
            stage="transcript",
            label=(
                f"Chunk scored — {len(usable)} usable of {needed} needed "
                f"after {int(scanned)}s (cap {int(MAX_SCAN_SECONDS)}s)"
            ),
            scanned_seconds=round(scanned, 1),
        max_scan_seconds=HARD_MAX_SCAN_SECONDS,
            source_seconds=round(duration, 1),
            strong=len(strong),
            usable=len(usable),
            needed=needed,
        )
        if len(usable) >= needed or len(strong) >= needed:
            stopped_early = True
            print("  enough scored chunks — rest of video skipped.")
            break
        if scanned >= MAX_SCAN_SECONDS:
            stopped_early = True
            print(
                f"  {int(MAX_SCAN_SECONDS / 60)} min cap "
                f"({len(usable)} usable) — ranking the best of what we have."
            )
            break
        if len(usable) == 0:
            print("  opening is weak — next chunk, not the full talk.")

        start += max(8.0, window - SCAN_OVERLAP_SECONDS)

    elapsed = time.time() - t0
    show = detect_show(all_analysis)
    print(f"Show type: {show['id']} — {show.get('reason') or show['label']}")
    write_json(OUTPUT / "rms_series.json", {"samples": all_rms})
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
            "show_type": show.get("id"),
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
        "show_type": show.get("id"),
    })

    print(
        f"\nScan done in {elapsed:.1f}s. "
        f"Covered {scanned:.0f}s of {duration:.0f}s. "
        f"Early stop={stopped_early}."
    )
    close_worker()


if __name__ == "__main__":
    main()
