"""Kinetic title cards — local stand-in for AI B-roll on abstract claims."""

from __future__ import annotations

import subprocess
from pathlib import Path

import cv2
import numpy as np


def _wrap(text: str, limit: int = 14) -> list[str]:
    words = [w for w in (text or "").split() if w]
    lines, bucket = [], []
    for word in words:
        trial = (" ".join(bucket + [word])).strip()
        if len(trial) > limit and bucket:
            lines.append(" ".join(bucket))
            bucket = [word]
        else:
            bucket.append(word)
    if bucket:
        lines.append(" ".join(bucket))
    return lines[:3] or [""]


def render_card(title: str, subtitle: str, dest: Path, duration: float = 1.05) -> Path:
    """Write a 1080x1920 mp4 of a bouncing claim card."""
    canvas = np.zeros((1920, 1080, 3), dtype=np.uint8)
    canvas[:] = (18, 12, 10)
    cv2.rectangle(canvas, (0, 820), (1080, 1100), (0, 180, 255), thickness=-1)
    cv2.rectangle(canvas, (0, 820), (1080, 1100), (255, 255, 255), thickness=8)

    font = cv2.FONT_HERSHEY_DUPLEX
    lines = _wrap((title or "WATCH THIS").upper(), 16)
    y = 920 - 40 * (len(lines) - 1)
    for line in lines:
        scale = 2.3 if len(line) < 12 else 1.7
        size, _ = cv2.getTextSize(line, font, scale, 5)
        x = max(40, (1080 - size[0]) // 2)
        cv2.putText(canvas, line, (x, y), font, scale, (10, 10, 10), 5, cv2.LINE_AA)
        y += 90

    if subtitle:
        sub = " ".join(_wrap(subtitle, 28)[:2])
        size, _ = cv2.getTextSize(sub, font, 1.05, 2)
        cv2.putText(
            canvas, sub, (max(40, (1080 - size[0]) // 2), 1180),
            font, 1.05, (230, 230, 230), 2, cv2.LINE_AA,
        )

    png = dest.with_suffix(".png")
    dest.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(png), canvas)
    dur = max(0.7, float(duration))
    try:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-loop", "1", "-t", f"{dur:.2f}", "-i", str(png),
                "-f", "lavfi", "-t", f"{dur:.2f}", "-i", "anullsrc=r=44100:cl=stereo",
                "-vf", "scale=1080:1920,format=yuv420p",
                "-shortest",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", "-crf", "26",
                "-c:a", "aac", "-ar", "44100", "-ac", "2",
                str(dest),
            ],
            check=True,
            capture_output=True,
        )
    finally:
        png.unlink(missing_ok=True)
    return dest
