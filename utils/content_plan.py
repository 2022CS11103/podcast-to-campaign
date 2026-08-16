"""Load / validate content_plan.json. Shared by ranker, router, strategy."""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLAN_FILE = PROJECT_ROOT / "content_plan.json"


def plan_is_usable(plan) -> bool:
    if not isinstance(plan, dict) or not plan:
        return False
    total = 0
    for config in plan.values():
        if not isinstance(config, dict):
            return False
        try:
            total += int(config.get("count", 0))
        except (TypeError, ValueError):
            return False
    return total > 0


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
    if required and not plan_is_usable(plan):
        raise ValueError(
            "content_plan.json is empty or has no platform counts."
        )
    return plan if isinstance(plan, dict) else {}


def save_plan(plan: dict) -> None:
    with open(PLAN_FILE, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)
