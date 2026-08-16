import json
import time
from pathlib import Path
from threading import Lock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = PROJECT_ROOT / "output" / "cost_log.json"

# Gemini 2.5 Flash pricing (USD per 1M tokens) — verify current rates at
# https://ai.google.dev/gemini-api/docs/pricing before using for real billing
PRICE_INPUT_PER_M = 0.30
PRICE_OUTPUT_PER_M = 2.50

_lock = Lock()


def _load():
    if LOG_FILE.exists():
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"calls": [], "whisper_seconds": 0.0}


def _save(data):
    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def log_gemini_call(step: str, response):
    """Call this right after every client.models.generate_content(...) call."""
    try:
        usage = response.usage_metadata
        input_tokens = usage.prompt_token_count or 0
        output_tokens = usage.candidates_token_count or 0
    except Exception:
        input_tokens = 0
        output_tokens = 0

    with _lock:
        data = _load()
        data["calls"].append({
            "step": step,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "timestamp": time.time(),
        })
        _save(data)


def log_whisper_time(seconds: float):
    with _lock:
        data = _load()
        data["whisper_seconds"] += seconds
        _save(data)


def generate_report():
    data = _load()
    total_input = sum(c["input_tokens"] for c in data["calls"])
    total_output = sum(c["output_tokens"] for c in data["calls"])

    cost_input = (total_input / 1_000_000) * PRICE_INPUT_PER_M
    cost_output = (total_output / 1_000_000) * PRICE_OUTPUT_PER_M
    total_cost_usd = cost_input + cost_output

    economics = estimate_unit_economics(data)

    report = {
        "total_gemini_calls": len(data["calls"]),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "estimated_cost_usd": round(total_cost_usd, 5),
        "estimated_cost_inr": round(total_cost_usd * 87, 3),  # approx rate, update as needed
        "whisper_processing_seconds": round(data["whisper_seconds"], 2),
        "unit_economics": economics,
        "calls_by_step": data["calls"],
    }

    report_file = PROJECT_ROOT / "output" / "cost_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report


def estimate_unit_economics(log_data=None):
    """
    Rough per-job cost so we can price a paid API.

    Gemini is cheap. Whisper on CPU is time, not dollars. The real bill
    for a hosted product is GPU/CPU minutes for YOLO + ffmpeg.

    Suggested SaaS price is ~8–12x API+compute so a 60-minute talk
    can sell as a $9–19 campaign package.
    """
    duration = 0.0
    meta_file = PROJECT_ROOT / "output" / "metadata.json"
    if meta_file.exists():
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
            duration = float((meta.get("format") or {}).get("duration") or 0)
        except Exception:
            duration = 0.0

    clips_file = PROJECT_ROOT / "output" / "clips.json"
    num_clips = 0
    if clips_file.exists():
        try:
            with open(clips_file, "r", encoding="utf-8") as f:
                num_clips = len(json.load(f).get("clips", []))
        except Exception:
            num_clips = 0

    chunks_file = PROJECT_ROOT / "output" / "chunks.json"
    num_analyzed = 0
    if chunks_file.exists():
        try:
            with open(chunks_file, "r", encoding="utf-8") as f:
                num_analyzed = json.load(f).get("chunk_count", 0)
        except Exception:
            num_analyzed = 0

    # $0.08 / vCPU-hour as a conservative cloud CPU proxy.
    whisper_hours = (log_data or {}).get("whisper_seconds", 0) / 3600.0
    # Face track + crop + burn: ~0.4 CPU-min per rendered second of clip.
    avg_clip_sec = 32
    render_hours = (num_clips * avg_clip_sec * 0.4) / 3600.0
    compute_usd = (whisper_hours + render_hours) * 0.08

    gemini_in = sum(c["input_tokens"] for c in (log_data or {}).get("calls", []))
    gemini_out = sum(c["output_tokens"] for c in (log_data or {}).get("calls", []))
    gemini_usd = (gemini_in / 1_000_000) * PRICE_INPUT_PER_M + (gemini_out / 1_000_000) * PRICE_OUTPUT_PER_M

    true_cost = gemini_usd + compute_usd
    suggested_price = max(9.0, round(true_cost * 10 + 4.0, 2))

    return {
        "source_duration_seconds": round(duration, 1),
        "candidates_analyzed": num_analyzed,
        "clips_rendered": num_clips,
        "gemini_usd": round(gemini_usd, 5),
        "compute_usd_proxy": round(compute_usd, 5),
        "true_cost_usd": round(true_cost, 5),
        "suggested_api_price_usd": suggested_price,
        "notes": (
            "Gemini is usually a few cents. Wall-clock cost is Whisper + YOLO/ffmpeg. "
            "Cap analyzed candidates at 24 to keep API cost flat as talks get longer."
        ),
    }


def reset_log():
    """Call this at the start of each new video's pipeline run."""
    _save({"calls": [], "whisper_seconds": 0.0})