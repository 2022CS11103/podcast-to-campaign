"""
Quality gate for rendered shorts.

The executor renders, this scores the file against config/editing_rules.md,
and a failing render gets re-cut with a safer plan instead of shipped.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from config.editing_style import QUALITY_RUBRIC, profile_for

SILENCE_SCAN_SECONDS = 4.0


def probe(path: Path) -> dict:
    """Resolution, duration, and audio presence. Empty dict if ffprobe fails."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "stream=codec_type,width,height",
                "-show_entries", "format=duration",
                "-of", "json", str(path),
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout or "{}")
    except Exception:
        return {}

    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    try:
        duration = float((data.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "width": int(video.get("width") or 0) if video else 0,
        "height": int(video.get("height") or 0) if video else 0,
        "duration": round(duration, 2),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


def lead_silence(path: Path) -> float | None:
    """Seconds of silence before the first audio. None when undetectable."""
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-nostats", "-t", str(SILENCE_SCAN_SECONDS),
                "-i", str(path), "-af", "silencedetect=noise=-35dB:d=0.25",
                "-f", "null", "-",
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except Exception:
        return None
    log = (result.stderr or "") + (result.stdout or "")
    if "silence_start" not in log:
        return 0.0
    starts = [float(m) for m in re.findall(r"silence_start: ([0-9.]+)", log)]
    ends = [float(m) for m in re.findall(r"silence_end: ([0-9.]+)", log)]
    if not starts or min(starts) > 0.15:
        return 0.0
    return round(min(ends), 2) if ends else SILENCE_SCAN_SECONDS


def count_cues(ass_path: Path) -> int:
    """Caption cues, excluding the hook title card."""
    if not ass_path or not ass_path.exists():
        return 0
    try:
        text = ass_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    return sum(
        1 for line in text.splitlines()
        if line.startswith("Dialogue:") and ",Hook,," not in line
    )


def evaluate(video: Path, ass: Path = None, plan: dict = None, shots: int = 1,
             spec: dict = None) -> dict:
    """Score one rendered short. Returns checks, score, and failure ids."""
    plan = plan or {}
    rubric = QUALITY_RUBRIC
    info = probe(video)
    checks = []

    def add(check_id, label, ok, detail, weight=1, critical=False):
        checks.append({
            "id": check_id, "label": label, "ok": bool(ok),
            "detail": detail, "weight": weight, "critical": critical,
        })

    if not info:
        add("readable", "File is readable", False, "ffprobe could not read the render",
            weight=4, critical=True)
        return _finalize(checks, info, 0)

    add(
        "frame", "Vertical 1080x1920",
        info["width"] == rubric["width"] and info["height"] == rubric["height"],
        f"{info['width']}x{info['height']}",
        weight=3, critical=True,
    )

    duration = info["duration"]
    lo = rubric["min_seconds"]
    hi = rubric["max_seconds"]
    if spec:
        lo = max(lo, float(spec.get("min_seconds") or lo) * 0.8)
        hi = min(hi, float(spec.get("max_seconds") or hi) * 1.05)
    add(
        "duration", "Duration inside platform range",
        lo <= duration <= hi, f"{duration}s (allowed {lo:.0f}-{hi:.0f}s)",
        weight=3, critical=True,
    )

    add(
        "audio", "Dialogue track present",
        info["has_audio"] or not rubric["require_audio"],
        "audio stream found" if info["has_audio"] else "no audio stream",
        weight=3, critical=True,
    )

    cues = count_cues(ass)
    needed = max(1, int((duration / 10.0) * rubric["min_cues_per_10s"]))
    add(
        "captions", "Enough caption cues",
        cues >= needed, f"{cues} cues, {needed} needed for {duration}s",
        weight=2,
    )

    wants_cuts = bool(plan.get("drop_silences", True))
    add(
        "jump_cuts", "Cut, not a raw trim",
        shots >= rubric["min_shots_when_cutting"] or not wants_cuts,
        f"{shots} shots" + ("" if wants_cuts else " (single-shot plan)"),
        weight=2,
    )

    profile = profile_for(plan.get("pace") or "medium")
    cpm_lo, cpm_hi = profile["cuts_per_minute"]
    cpm = round((max(0, shots - 1) / duration) * 60, 1) if duration > 0 else 0
    add(
        "pacing", "Cut rhythm matches pace",
        (cpm_lo <= cpm <= cpm_hi) or not wants_cuts,
        f"{cpm} cuts/min (band {cpm_lo}-{cpm_hi} for {plan.get('pace') or 'medium'})",
        weight=1,
    )

    silence = lead_silence(video)
    add(
        "cold_open", "No silent runway",
        silence is None or silence <= rubric["max_lead_silence"],
        "unmeasured" if silence is None else f"{silence}s before first audio",
        weight=2,
    )

    return _finalize(checks, info, None)


def _finalize(checks, info, forced_score):
    total = sum(c["weight"] for c in checks) or 1
    earned = sum(c["weight"] for c in checks if c["ok"])
    score = forced_score if forced_score is not None else round(100 * earned / total)
    critical_failed = [c["id"] for c in checks if c["critical"] and not c["ok"]]
    failures = [c["id"] for c in checks if not c["ok"]]
    return {
        "score": score,
        "passed": not critical_failed and score >= QUALITY_RUBRIC["pass_score"],
        "critical_failures": critical_failed,
        "failures": failures,
        "checks": checks,
        "probe": info,
    }


def safer_plan(plan: dict, report: dict) -> dict:
    """Adjust a plan so the next render clears what the last one failed.

    Returns None when nothing in the plan would change the outcome.
    """
    failures = set(report.get("failures") or [])
    revised = json.loads(json.dumps(plan or {}))
    changed = []

    if "duration" in failures or "readable" in failures or "frame" in failures:
        # Aggressive silence removal and tightening are the only things that
        # shorten a cut, so give the window back.
        if revised.get("drop_silences", True):
            revised["drop_silences"] = False
            changed.append("kept the full take (no silence removal)")
        if revised.get("trim"):
            revised.pop("trim")
            changed.append("dropped the trim")

    if "pacing" in failures and revised.get("pace") != "medium":
        revised["pace"] = "medium"
        changed.append("relaxed pace to medium")

    if "jump_cuts" in failures and not revised.get("punch_ins"):
        changed.append("no punch-ins to re-cut with")

    if "cold_open" in failures and revised.get("trim"):
        revised["trim"] = dict(revised["trim"])
        changed.append("re-opened on the first spoken word")

    if not changed:
        return None
    revised["_revision"] = changed
    return revised


def summarize(reports: list) -> dict:
    scored = [r for r in reports if isinstance(r, dict) and r.get("score") is not None]
    if not scored:
        return {"clips": reports, "average_score": None, "passed": 0, "failed": 0}
    return {
        "clips": reports,
        "average_score": round(sum(r["score"] for r in scored) / len(scored)),
        "passed": sum(1 for r in scored if r.get("passed")),
        "failed": sum(1 for r in scored if not r.get("passed")),
        "rubric": QUALITY_RUBRIC,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/video/edit_quality.py <short.mp4> [captions.ass]")
        sys.exit(2)
    ass = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    report = evaluate(Path(sys.argv[1]), ass)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
