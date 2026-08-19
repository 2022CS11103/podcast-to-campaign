"""
Cheap picture + sound energy for highlight scan.

This is not YOLO on every frame. We sample ~2 fps at 160x90, optionally
look for a face at 1 fps, and read RMS from the 16 kHz wav Whisper already
uses. The goal is "something happened on screen / in the room" so a dull
sentence with applause or a gesture can still become a Short.
"""

from __future__ import annotations

import array
import math
import subprocess
import wave
from pathlib import Path

import cv2
import numpy as np

SAMPLE_FPS = 1
MOTION_SIZE = (160, 90)
WORD_WEIGHT = 0.50
AUDIO_WEIGHT = 0.28
VISUAL_WEIGHT = 0.22
ENERGY_RESCUE_AT = 72.0


def _percentile_rank(values, x):
    if not values:
        return 50.0
    below = sum(1 for v in values if v <= x)
    return 100.0 * below / len(values)


def _mean(values):
    return sum(values) / len(values) if values else 0.0


def wav_rms_series(wav_path, abs_start, hop=0.5):
    path = Path(wav_path)
    if not path.exists():
        return []
    try:
        with wave.open(str(path), "rb") as wf:
            sr = wf.getframerate() or 16000
            nchan = max(1, wf.getnchannels())
            width = wf.getsampwidth()
            nframes = wf.getnframes()
            raw = wf.readframes(nframes)
    except Exception:
        return []
    if width != 2 or not raw:
        return []
    samples = array.array("h")
    samples.frombytes(raw)
    if nchan > 1:
        samples = array.array("h", (samples[i] for i in range(0, len(samples), nchan)))
    hop_n = max(1, int(sr * hop))
    out = []
    for i in range(0, len(samples) - hop_n + 1, hop_n):
        chunk = samples[i:i + hop_n]
        acc = sum(s * s for s in chunk) / len(chunk)
        out.append({"t": round(abs_start + i / sr, 2), "rms": math.sqrt(acc)})
    return out


def scan_video_window(video_path, start, duration):
    """
    Motion + scene-change at 1 fps, 160x90, via ffmpeg.
    Haar/YOLO stay off — they added minutes and never found faces on talks.
    """
    width, height = MOTION_SIZE
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-ss", str(max(0.0, start)),
        "-t", str(max(0.1, duration)),
        "-i", str(video_path),
        "-an",
        "-vf", f"fps={SAMPLE_FPS},scale={width}:{height}",
        "-pix_fmt", "rgb24",
        "-f", "rawvideo",
        "pipe:1",
    ]
    try:
        proc = subprocess.run(command, capture_output=True, check=False)
    except Exception:
        return []
    raw = proc.stdout or b""
    frame_bytes = width * height * 3
    if frame_bytes <= 0 or len(raw) < frame_bytes:
        return []

    samples = []
    prev_gray = None
    prev_hist = None
    n = len(raw) // frame_bytes
    for i in range(n):
        buf = np.frombuffer(raw, dtype=np.uint8, count=frame_bytes, offset=i * frame_bytes)
        rgb = buf.reshape((height, width, 3))
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        motion = 0.0
        if prev_gray is not None:
            motion = float(np.mean(cv2.absdiff(gray, prev_gray)))
        prev_gray = gray
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        hist = cv2.calcHist([hsv], [0], None, [16], [0, 180])
        cv2.normalize(hist, hist)
        scene = 0.0
        if prev_hist is not None:
            corr = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL))
            scene = max(0.0, 1.0 - corr)
        prev_hist = hist
        samples.append({
            "t": round(start + i / float(SAMPLE_FPS), 2),
            "motion": round(motion, 3),
            "scene": round(scene, 4),
            "face": 0.0,
        })
    return samples


def merge_audio(samples, rms_series):
    if not samples:
        return [{"t": r["t"], "motion": 0, "scene": 0, "face": 0, "rms": r["rms"]} for r in rms_series]
    if not rms_series:
        for s in samples:
            s["rms"] = 0.0
        return samples
    rms_ts = [r["t"] for r in rms_series]
    rms_vs = [r["rms"] for r in rms_series]
    for s in samples:
        nearest = min(range(len(rms_ts)), key=lambda i: abs(rms_ts[i] - s["t"]))
        s["rms"] = rms_vs[nearest]
    return samples


def score_span(samples, start, end):
    """0–100 visual / audio energy for a candidate window, plus why."""
    empty = {
        "visual_score": 50.0,
        "audio_energy": 50.0,
        "visual_signals": {},
        "highlight_reason": "words",
    }
    if not samples:
        return empty
    span = [s for s in samples if start - 0.05 <= s["t"] < end + 0.05]
    if not span:
        span = samples
    motions = [s.get("motion", 0) or 0 for s in samples]
    scenes = [s.get("scene", 0) or 0 for s in samples]
    faces = [s.get("face", 0) or 0 for s in samples]
    rmses = [s.get("rms", 0) or 0 for s in samples]

    motion_mean = _mean([s.get("motion", 0) or 0 for s in span])
    scene_mean = _mean([s.get("scene", 0) or 0 for s in span])
    face_mean = _mean([s.get("face", 0) or 0 for s in span])
    rms_mean = _mean([s.get("rms", 0) or 0 for s in span])
    rms_peak = max((s.get("rms", 0) or 0) for s in span)

    hook_end = start + 2.0
    hook = [s for s in span if s["t"] < hook_end]
    hook_motion = _mean([s.get("motion", 0) or 0 for s in hook]) if hook else motion_mean
    hook_rms = _mean([s.get("rms", 0) or 0 for s in hook]) if hook else rms_mean

    visual = (
        0.40 * _percentile_rank(motions, motion_mean)
        + 0.25 * _percentile_rank(scenes, scene_mean)
        + 0.20 * _percentile_rank(faces, face_mean)
        + 0.15 * _percentile_rank(motions, hook_motion)
    )
    audio = (
        0.55 * _percentile_rank(rmses, rms_mean)
        + 0.25 * _percentile_rank(rmses, rms_peak)
        + 0.20 * _percentile_rank(rmses, hook_rms)
    )

    scene_cuts = scene_mean > (np.percentile(scenes, 75) if scenes else 0.15)
    loud = rms_peak > (np.percentile(rmses, 80) if rmses else 0)
    moving = motion_mean > (np.percentile(motions, 70) if motions else 0)
    faced = face_mean > 0.02

    signals = {
        "scene_cuts": bool(scene_cuts),
        "loud": bool(loud),
        "motion": bool(moving),
        "face": bool(faced),
        "motion_mean": round(motion_mean, 3),
        "rms_peak": round(rms_peak, 1),
        "face_mean": round(face_mean, 4),
    }
    reason = highlight_reason(None, audio, visual, signals)
    return {
        "visual_score": round(float(visual), 1),
        "audio_energy": round(float(audio), 1),
        "visual_signals": signals,
        "highlight_reason": reason,
    }


def highlight_reason(word_score, audio_energy, visual_score, signals=None):
    signals = signals or {}
    w = float(word_score or 0)
    a = float(audio_energy or 0)
    v = float(visual_score or 0)
    if w >= 60:
        top = "words"
    else:
        top = max(
            (("words", w), ("audio spike", a), ("on-screen energy", v)),
            key=lambda x: x[1],
        )[0]
    tags = []
    if signals.get("loud"):
        tags.append("loud beat")
    if signals.get("motion"):
        tags.append("movement")
    if signals.get("scene_cuts"):
        tags.append("scene change")
    if signals.get("face"):
        tags.append("face in frame")
    if tags:
        return f"{top}: " + ", ".join(tags[:2])
    return top


def fuse_editor_score(word_score, audio_energy=None, visual_score=None, enabled=True):
    """
    Blend Gemini words with local picture/sound.

    A TED bit can look like nonsense on paper (word_score 0) while the
    room is reacting. If energy is hot, do not let Gemini veto the cut.
    """
    w = float(word_score or 0)
    if not enabled or (audio_energy is None and visual_score is None):
        return round(w, 1)
    a = 50.0 if audio_energy is None else float(audio_energy)
    v = 50.0 if visual_score is None else float(visual_score)
    mixed = WORD_WEIGHT * w + AUDIO_WEIGHT * a + VISUAL_WEIGHT * v
    energy = 0.55 * a + 0.45 * v
    if energy >= ENERGY_RESCUE_AT and w < 50:
        rescued = 0.30 * max(w, 35.0) + 0.70 * energy
        mixed = max(mixed, rescued)
    return round(mixed, 1)


def heuristic_boost(energy):
    """Lift text-heuristic so visually hot windows still reach Gemini."""
    visual = float((energy or {}).get("visual_score") or 50)
    audio = float((energy or {}).get("audio_energy") or 50)
    return round((visual + audio) / 40.0, 2)
