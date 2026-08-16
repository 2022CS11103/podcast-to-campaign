"""Load / validate content_plan.json. Shared by ranker, router, strategy."""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLAN_FILE = PROJECT_ROOT / "content_plan.json"


def normalize_plan(plan) -> dict:
    """
    Frontend may send extra keys (purpose, enabled, suggested_length).
    Disabled platforms and count=0 are dropped so Generate still works
    when the creator toggles a channel off.
    """
    if not isinstance(plan, dict):
        return {}
    cleaned = {}
    for platform, config in plan.items():
        if not isinstance(config, dict):
            continue
        if config.get("enabled") is False:
            continue
        try:
            count = int(config.get("count", 0) or 0)
        except (TypeError, ValueError):
            continue
        if count <= 0:
            continue
        interval = config.get("interval_days", 5)
        try:
            interval = int(interval)
        except (TypeError, ValueError):
            interval = 5
        cleaned[platform] = {
            **config,
            "count": count,
            "interval_days": max(1, interval),
        }
    return cleaned


def plan_is_usable(plan) -> bool:
    return bool(normalize_plan(plan))


def load_plan(required: bool = True) -> dict:
    if not PLAN_FILE.exists():
        if required:
            raise FileNotFoundError(
                "content_plan.json not found. Send a content_plan from the "
                "frontend, or let the strategy agent create one."
            )
        return {}
    with open(PLAN_FILE, "r", encoding="utf-8") as f:
        plan = json.load(f)
    plan = normalize_plan(plan)
    if required and not plan_is_usable(plan):
        raise ValueError(
            "content_plan.json is empty or has no enabled platform counts."
        )
    return plan


def save_plan(plan: dict) -> None:
    with open(PLAN_FILE, "w", encoding="utf-8") as f:
        json.dump(normalize_plan(plan) or plan, f, indent=2)
