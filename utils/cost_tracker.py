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

    report = {
        "total_gemini_calls": len(data["calls"]),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "estimated_cost_usd": round(total_cost_usd, 5),
        "estimated_cost_inr": round(total_cost_usd * 87, 3),  # approx rate, update as needed
        "whisper_processing_seconds": round(data["whisper_seconds"], 2),
        "calls_by_step": data["calls"],
    }

    report_file = PROJECT_ROOT / "output" / "cost_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report


def reset_log():
    """Call this at the start of each new video's pipeline run."""
    _save({"calls": [], "whisper_seconds": 0.0})