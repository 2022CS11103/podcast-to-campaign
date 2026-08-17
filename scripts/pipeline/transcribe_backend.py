"""
Transcribe a short wav without loading Whisper into the pipeline process.

1) Spawn an isolated whisper_worker.py (fresh MKL heap)
2) If that fails (mkl_malloc / RAM), use Gemini audio
"""
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WORKER = PROJECT_ROOT / "scripts" / "pipeline" / "whisper_worker.py"

_use_gemini = False


def _worker_env():
    env = os.environ.copy()
    env["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    env["OMP_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    env["MKL_DISABLE_FAST_MM"] = "1"
    env["CT2_USE_EXPERIMENTAL_PACKED_GEMM"] = "0"
    env["CT2_FORCE_CPU_ISA"] = "GENERIC"
    return env


def _whisper_worker(wav: Path):
    result = subprocess.run(
        [sys.executable, "-u", str(WORKER), str(wav)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(PROJECT_ROOT),
        env=_worker_env(),
        timeout=120,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(err[-1500:] or f"whisper_worker exit {result.returncode}")
    return json.loads(result.stdout)


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


def transcribe_wav_file(wav: Path, duration: float):
    """Return [{"start","end","text"}] relative to the clip start."""
    global _use_gemini
    if not _use_gemini:
        try:
            return _whisper_worker(wav)
        except Exception as exc:
            print(f"  local Whisper failed ({exc}). Switching this job to Gemini audio.")
            _use_gemini = True
    return _gemini_transcribe(wav, duration)
