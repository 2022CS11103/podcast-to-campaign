"""
Transcribe a wav without loading Whisper into the pipeline process.

A long-lived whisper_worker.py keeps the model in RAM so we do not pay
the load cost on every slice. If that worker dies, fall back to Gemini.
"""
import atexit
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WORKER = PROJECT_ROOT / "scripts" / "pipeline" / "whisper_worker.py"

_use_gemini = False
_worker_proc = None


def _worker_env():
    env = os.environ.copy()
    env["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    env["PYTHONUNBUFFERED"] = "1"
    env.pop("CT2_FORCE_CPU_ISA", None)
    return env


def close_worker():
    global _worker_proc
    proc = _worker_proc
    _worker_proc = None
    if not proc:
        return
    try:
        if proc.stdin:
            proc.stdin.write(json.dumps({"stop": True}) + "\n")
            proc.stdin.flush()
    except Exception:
        pass
    try:
        proc.terminate()
        proc.wait(timeout=4)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


atexit.register(close_worker)


def _ensure_worker():
    global _worker_proc
    if _worker_proc and _worker_proc.poll() is None:
        return _worker_proc
    close_worker()
    print("  starting Whisper (one-time model load)...")
    _worker_proc = subprocess.Popen(
        [sys.executable, "-u", str(WORKER), "--serve"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(PROJECT_ROOT),
        env=_worker_env(),
        bufsize=1,
    )
    return _worker_proc


def _whisper_worker(wav: Path, word_timestamps=False):
    proc = _ensure_worker()
    try:
        proc.stdin.write(json.dumps({"wav": str(wav), "words": bool(word_timestamps)}) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
    except Exception:
        close_worker()
        raise
    if not line:
        close_worker()
        raise RuntimeError("whisper_worker closed unexpectedly")
    data = json.loads(line)
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(data["error"])
    if not isinstance(data, list):
        raise RuntimeError("whisper_worker returned unexpected payload")
    return data


def _gemini_transcribe(wav: Path, duration: float):
    from google.genai import types
    from utils.gemini_clients import generate_multimodal
    from utils.cost_tracker import log_gemini_call

    prompt = (
        "Transcribe this English speech. Return ONLY JSON, no markdown:\n"
        '{"segments":[{"start":0.0,"end":1.2,"text":"..."}]}\n'
        "start and end are seconds from the beginning of this clip."
    )
    audio = wav.read_bytes()
    response = generate_multimodal([
        types.Part.from_bytes(data=audio, mime_type="audio/wav"),
        prompt,
    ])
    log_gemini_call("transcript_audio", response)
    raw = (response.text or "").replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(raw)
        segs = data.get("segments") if isinstance(data, dict) else data
        if not isinstance(segs, list):
            segs = []
    except Exception:
        segs = [{"start": 0.0, "end": duration, "text": raw}]
    cleaned = []
    for seg in segs:
        if not isinstance(seg, dict):
            continue
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        cleaned.append({
            "start": float(seg.get("start") or 0),
            "end": float(seg.get("end") or duration),
            "text": text,
        })
    if not cleaned and raw:
        cleaned = [{"start": 0.0, "end": duration, "text": raw}]
    return cleaned


def transcribe_wav_file(wav: Path, duration: float, word_timestamps=False):
    """Return [{"start","end","text"}] relative to the clip start."""
    global _use_gemini
    if not _use_gemini:
        try:
            return _whisper_worker(wav, word_timestamps=word_timestamps)
        except Exception as exc:
            print(f"  local Whisper failed ({exc}). Switching this job to Gemini audio.")
            _use_gemini = True
            close_worker()
    return _gemini_transcribe(wav, duration)


def fill_words_for_clips(video: Path, clips: list, transcript_file: Path):
    """Word timings only for the ranked cuts, not the whole scan."""
    if not clips or not video or not Path(video).exists():
        return
    try:
        data = json.loads(transcript_file.read_text(encoding="utf-8")) if transcript_file.exists() else {}
    except (OSError, ValueError):
        data = {}
    segments = list(data.get("segments") or [])
    wav = PROJECT_ROOT / "output" / "clip_words.wav"
    for clip in clips:
        try:
            start = float(clip.get("start") or 0)
            end = float(clip.get("end") or 0)
        except (TypeError, ValueError):
            continue
        dur = max(1.0, end - start)
        wav.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", str(start), "-t", str(dur),
                "-i", str(video),
                "-vn", "-ac", "1", "-ar", "16000",
                str(wav),
            ],
            check=False,
            capture_output=True,
        )
        if not wav.exists():
            continue
        raw = transcribe_wav_file(wav, dur, word_timestamps=True)
        for seg in raw:
            a = start + float(seg.get("start") or 0)
            b = start + float(seg.get("end") or 0)
            words = []
            for word in seg.get("words") or []:
                token = (word.get("word") or "").strip()
                if not token:
                    continue
                words.append({
                    "word": token,
                    "start": round(start + float(word.get("start") or 0), 2),
                    "end": round(start + float(word.get("end") or 0), 2),
                })
            if not words:
                continue
            matched = False
            for row in segments:
                if abs(float(row.get("start") or 0) - a) < 0.8:
                    row["words"] = words
                    matched = True
                    break
            if not matched:
                segments.append({
                    "start": round(a, 2),
                    "end": round(b, 2),
                    "text": (seg.get("text") or "").strip(),
                    "words": words,
                })
    segments.sort(key=lambda row: float(row.get("start") or 0))
    data["segments"] = segments
    transcript_file.parent.mkdir(parents=True, exist_ok=True)
    transcript_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        wav.unlink(missing_ok=True)
    except OSError:
        pass

