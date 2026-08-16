"""Wall-clock timing for one campaign job. Survives across subprocesses via JSON."""

import json
import time
from pathlib import Path
from threading import Lock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_FILE = PROJECT_ROOT / "output" / "timing_report.json"

_lock = Lock()


def format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _empty():
    return {
        "started_at": None,
        "finished_at": None,
        "total_seconds": 0,
        "total_human": "0s",
        "steps": [],
    }


def _load():
    if REPORT_FILE.exists():
        with open(REPORT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return _empty()


def _save(data):
    REPORT_FILE.parent.mkdir(exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def reset():
    data = _empty()
    data["started_at"] = time.time()
    with _lock:
        _save(data)
    return data


def log_step(name: str, seconds: float, ok: bool = True):
    with _lock:
        data = _load()
        started = data.get("started_at") or time.time()
        elapsed = time.time() - started
        data["steps"].append({
            "step": name,
            "seconds": round(seconds, 2),
            "human": format_duration(seconds),
            "ok": ok,
        })
        data["total_seconds"] = round(elapsed, 2)
        data["total_human"] = format_duration(elapsed)
        _save(data)
        return snapshot_unlocked(data)


def finish(ok: bool = True):
    with _lock:
        data = _load()
        started = data.get("started_at") or time.time()
        elapsed = time.time() - started
        data["finished_at"] = time.time()
        data["ok"] = ok
        data["total_seconds"] = round(elapsed, 2)
        data["total_human"] = format_duration(elapsed)
        _save(data)
        return snapshot_unlocked(data)


def snapshot():
    with _lock:
        return snapshot_unlocked(_load())


def snapshot_unlocked(data):
    started = data.get("started_at")
    elapsed = (time.time() - started) if started else 0
    return {
        "started_at": started,
        "finished_at": data.get("finished_at"),
        "ok": data.get("ok"),
        "total_seconds": round(elapsed if not data.get("finished_at") else data.get("total_seconds", elapsed), 2),
        "total_human": format_duration(elapsed if not data.get("finished_at") else data.get("total_seconds", elapsed)),
        "steps": data.get("steps") or [],
    }
