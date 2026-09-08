"""Standalone clip desk: URL + optional timespan → download and/or transcript.

Keeps files under output/clip_desk/ so campaign input/video.mp4 is untouched.
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLIP_DIR = PROJECT_ROOT / "output" / "clip_desk"

from scripts.pipeline.download_video import (
    download_video_to,
    format_timecode,
    parse_timecode,
)


def _probe_duration(path: Path) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout or "{}")
        return float((data.get("format") or {}).get("duration") or 0) or None
    except Exception:
        return None


def _extract_wav(video: Path, wav: Path) -> Path:
    wav.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(video),
            "-vn", "-ac", "1", "-ar", "16000",
            str(wav),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0 or not wav.exists():
        detail = (result.stderr or result.stdout or "ffmpeg failed").strip()
        raise RuntimeError(f"Could not extract audio: {detail[-500:]}")
    return wav


def new_job_id() -> str:
    return uuid.uuid4().hex[:12]


def fetch_clip(url: str, start=None, end=None, job_id: str | None = None) -> dict[str, Any]:
    """Download full URL or only [start, end] into clip_desk."""
    if not (url or "").strip():
        raise ValueError("Paste a video URL first.")
    start_s = parse_timecode(start)
    end_s = parse_timecode(end)
    if start_s is not None and end_s is not None and end_s <= start_s:
        raise ValueError("End time must be after start time.")

    job = job_id or new_job_id()
    CLIP_DIR.mkdir(parents=True, exist_ok=True)
    video_path = CLIP_DIR / f"clip_{job}.mp4"
    download_video_to(url.strip(), video_path, start=start_s, end=end_s)
    duration = _probe_duration(video_path)
    meta = {
        "job_id": job,
        "url": url.strip(),
        "start": start_s,
        "end": end_s,
        "video_path": str(video_path),
        "video_file": video_path.name,
        "duration_seconds": duration,
        "play_url": f"/media/clip_desk/{video_path.name}",
        "download_url": f"/media/clip_desk/{video_path.name}",
        "timespan_label": (
            f"{format_timecode(start_s or 0)} → {format_timecode(end_s)}"
            if (start_s is not None or end_s is not None)
            else "full video"
        ),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (CLIP_DIR / f"clip_{job}.meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    return meta


def transcribe_clip(
    url: str | None = None,
    start=None,
    end=None,
    mode: str = "range",
    job_id: str | None = None,
) -> dict[str, Any]:
    """
    mode=range → download only the timespan (or reuse job) then transcribe it
    mode=full  → download the whole video then transcribe everything
    """
    mode = (mode or "range").strip().lower()
    if mode not in {"range", "full"}:
        raise ValueError("mode must be 'range' or 'full'")

    meta = None
    if job_id:
        meta_path = CLIP_DIR / f"clip_{job_id}.meta.json"
        video_path = CLIP_DIR / f"clip_{job_id}.mp4"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not video_path.exists():
            if not url:
                raise ValueError("Clip file missing — paste the URL again.")
            meta = fetch_clip(
                url,
                start=None if mode == "full" else start,
                end=None if mode == "full" else end,
                job_id=job_id,
            )
            video_path = Path(meta["video_path"])
    else:
        if not url:
            raise ValueError("Paste a video URL first.")
        if mode == "full":
            meta = fetch_clip(url, start=None, end=None)
        else:
            meta = fetch_clip(url, start=start, end=end)
        video_path = Path(meta["video_path"])
        job_id = meta["job_id"]

    wav_path = CLIP_DIR / f"clip_{job_id}.wav"
    _extract_wav(video_path, wav_path)
    duration = _probe_duration(video_path) or 0.0

    from scripts.pipeline.transcribe_backend import transcribe_wav_file

    raw = transcribe_wav_file(wav_path, duration, word_timestamps=False)
    if isinstance(raw, dict):
        rows = raw.get("segments") or []
        language = raw.get("language")
        text_from_raw = str(raw.get("transcript") or "").strip()
    else:
        rows = raw or []
        language = None
        text_from_raw = ""

    segments = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        segments.append({
            "start": float(row.get("start") or 0),
            "end": float(row.get("end") or 0),
            "text": text,
        })
    text = text_from_raw or " ".join(s["text"] for s in segments)

    # Map clip-relative times back to source times when a range was used
    offset = float(meta.get("start") or 0) if meta and mode == "range" else 0.0
    display_segments = [
        {
            "start": round(s["start"] + offset, 2),
            "end": round(s["end"] + offset, 2),
            "text": s["text"],
            "clip_start": s["start"],
            "clip_end": s["end"],
        }
        for s in segments
    ]

    payload = {
        "job_id": job_id,
        "mode": mode,
        "source": "clip_desk",
        "url": (meta or {}).get("url") or url,
        "start": (meta or {}).get("start"),
        "end": (meta or {}).get("end"),
        "timespan_label": (meta or {}).get("timespan_label") or mode,
        "language": language,
        "duration_seconds": duration,
        "segment_count": len(display_segments),
        "transcript": text,
        "segments": display_segments,
        "play_url": (meta or {}).get("play_url") or f"/media/clip_desk/{video_path.name}",
        "download_url": (meta or {}).get("download_url") or f"/media/clip_desk/{video_path.name}",
        "video_file": video_path.name,
    }
    out = CLIP_DIR / f"clip_{job_id}.transcript.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        wav_path.unlink(missing_ok=True)
    except OSError:
        pass
    return payload


def latest_clip_transcript() -> dict[str, Any] | None:
    if not CLIP_DIR.exists():
        return None
    files = sorted(CLIP_DIR.glob("clip_*.transcript.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    return json.loads(files[0].read_text(encoding="utf-8"))
