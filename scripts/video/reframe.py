"""Follow the speaker into 9:16 instead of center-cropping the frame.

Haar runs on a few 640px stills inside each shot. If that misses, one YOLO
person box on the midpoint frame is enough. Results are cached per source
window so a re-cut does not scan again.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = PROJECT_ROOT / "output" / "tracking"

_haar = None
_yolo = None


def probe_size(video: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0", str(video),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    parts = (result.stdout or "").strip().split(",")
    try:
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return 1920, 1080


def grab_frame(video: Path, t: float) -> np.ndarray | None:
    dest = Path(tempfile.gettempdir()) / f"creatoros_reframe_{abs(hash((str(video), round(t, 2))))}.jpg"
    try:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{max(0.0, t):.3f}",
                "-i", str(video),
                "-frames:v", "1",
                "-q:v", "4",
                str(dest),
            ],
            check=True,
            capture_output=True,
        )
        frame = cv2.imread(str(dest))
        return frame
    except Exception:
        return None
    finally:
        dest.unlink(missing_ok=True)


def _haar_center(frame) -> float | None:
    global _haar
    if _haar is None:
        path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        _haar = cv2.CascadeClassifier(str(path))
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    scale = 640.0 / max(w, 1)
    small = cv2.resize(gray, (int(w * scale), int(h * scale))) if scale < 1 else gray
    faces = _haar.detectMultiScale(small, 1.12, 5, minSize=(36, 36))
    if len(faces) == 0:
        return None
    x, y, fw, fh = max(faces, key=lambda b: b[2] * b[3])
    cx = (x + fw / 2.0) / small.shape[1]
    return float(min(0.92, max(0.08, cx)))


def _yolo_center(frame) -> float | None:
    global _yolo
    try:
        from ultralytics import YOLO
    except Exception:
        return None
    try:
        if _yolo is None:
            _yolo = YOLO("yolov8n.pt")
        results = _yolo.predict(frame, classes=[0], conf=0.28, verbose=False)
        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            return None
        best, area = None, 0.0
        for box in boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            a = (x2 - x1) * (y2 - y1)
            if a > area:
                area = a
                best = (x1, x2)
        if not best:
            return None
        w = frame.shape[1]
        return float(min(0.92, max(0.08, ((best[0] + best[1]) / 2.0) / w)))
    except Exception:
        return None


def speaker_x(video: Path, t0: float, t1: float, samples: int = 4) -> float:
    """Horizontal subject position as a 0–1 fraction of frame width."""
    key = f"{Path(video).stem}_{t0:.1f}_{t1:.1f}"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{key}.json"
    if cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            return float(data["x"])
        except (OSError, ValueError, KeyError, TypeError):
            pass

    span = max(0.4, t1 - t0)
    times = [t0 + span * (i + 0.5) / samples for i in range(samples)]
    xs = []
    mid_frame = None
    for t in times:
        frame = grab_frame(video, t)
        if frame is None:
            continue
        if mid_frame is None:
            mid_frame = frame
        found = _haar_center(frame)
        if found is not None:
            xs.append(found)
    if not xs and mid_frame is not None:
        found = _yolo_center(mid_frame)
        if found is not None:
            xs.append(found)

    x = float(sorted(xs)[len(xs) // 2]) if xs else 0.5
    try:
        cache.write_text(json.dumps({"x": round(x, 4)}), encoding="utf-8")
    except OSError:
        pass
    return x


def crop_origin(x_frac: float, src_w: int, src_h: int, zoom: float = 1.0) -> tuple[int, int, int, int]:
    """Pixel crop box on the scaled 9:16 canvas (1080x1920 after zoom)."""
    zw = int(round(1080 * max(1.0, zoom)))
    zh = int(round(1920 * max(1.0, zoom)))
    # Match FFmpeg force_original_aspect_ratio=increase onto zw x zh.
    scale = max(zw / max(src_w, 1), zh / max(src_h, 1))
    scaled_w = src_w * scale
    scaled_h = src_h * scale
    cx = x_frac * scaled_w
    x = int(round(cx - 1080 / 2))
    y = int(round(max(0.0, scaled_h - 1920) * 0.28))
    x = max(0, min(x, max(0, int(scaled_w) - 1080)))
    y = max(0, min(y, max(0, int(scaled_h) - 1920)))
    return x, y, zw, zh
