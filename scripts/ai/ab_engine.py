"""A/B testing + winner repost logic for the content bank."""

import json
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
import sys
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from config.platform_specs import (
    REPOST_AFTER_DAYS,
    WINNER_MIN_VIEWS,
    WINNER_MIN_ENGAGEMENT_RATE,
    VIDEO_PLATFORMS,
)

BANK_FILE = PROJECT_ROOT / "output" / "content_bank.json"


def load_bank():
    if not BANK_FILE.exists():
        raise FileNotFoundError("content_bank.json not found")
    with open(BANK_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_bank(data):
    with open(BANK_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def find_item(data, item_id):
    for item in data.get("items", []):
        if item.get("id") == item_id:
            return item
    return None


def _engagement_rate(perf):
    views = max(int(perf.get("views") or 0), 0)
    if views <= 0:
        return 0.0
    engaged = int(perf.get("likes") or 0) + int(perf.get("comments") or 0) + int(perf.get("shares") or 0)
    return round(engaged / views, 4)


def record_performance(item_id: str, metrics: dict, variant_id: str = None):
    """
    Ingest platform analytics for a posted item.
    If variant_id is set, the metrics also accrue on that A/B variant.
    """
    data = load_bank()
    item = find_item(data, item_id)
    if item is None:
        raise KeyError(f"Unknown item {item_id}")

    perf = item.setdefault("performance", {})
    for key in ("impressions", "views", "likes", "comments", "shares"):
        if key in metrics and metrics[key] is not None:
            perf[key] = int(metrics[key])
    if metrics.get("ctr") is not None:
        perf["ctr"] = float(metrics["ctr"])
    perf["engagement_rate"] = _engagement_rate(perf)
    perf["updated_at"] = datetime.utcnow().isoformat()

    vid = variant_id or item.get("active_variant")
    for variant in item.get("variants") or []:
        if variant.get("id") == vid:
            for key in ("impressions", "views", "likes", "comments"):
                if key in metrics and metrics[key] is not None:
                    variant[key] = int(metrics[key])
            variant["status"] = "tested"
            break

    # Promote the best-tested variant to active if we have enough signal.
    tested = [v for v in (item.get("variants") or []) if v.get("status") == "tested" and v.get("views", 0) >= 50]
    if tested:
        winner = max(tested, key=lambda v: (v.get("likes", 0) + 2 * v.get("comments", 0)) / max(v.get("views", 1), 1))
        item["active_variant"] = winner["id"]
        item["hook"] = winner.get("hook") or item.get("hook")

    if is_winner(item):
        item["status"] = "winner" if item.get("status") != "reposted" else item["status"]

    save_bank(data)
    return item


def is_winner(item) -> bool:
    perf = item.get("performance") or {}
    views = int(perf.get("views") or 0)
    rate = float(perf.get("engagement_rate") or 0)
    return views >= WINNER_MIN_VIEWS and rate >= WINNER_MIN_ENGAGEMENT_RATE


def list_winners():
    data = load_bank()
    winners = [i for i in data.get("items", []) if is_winner(i)]
    winners.sort(key=lambda i: (i.get("performance") or {}).get("engagement_rate", 0), reverse=True)
    return winners


def schedule_repost(item_id: str, platform: str = None, days: int = None):
    """
    Clone a winning item onto the calendar with the winning variant.
    Default: 14 days later, on a different video platform if one exists.
    """
    data = load_bank()
    item = find_item(data, item_id)
    if item is None:
        raise KeyError(f"Unknown item {item_id}")

    delay = days if days is not None else REPOST_AFTER_DAYS
    original_date = datetime.strptime(item["scheduled_date"], "%Y-%m-%d")
    new_date = original_date + timedelta(days=delay)

    alt_platform = platform
    if not alt_platform:
        current = item.get("assigned_platform")
        alts = [p for p in VIDEO_PLATFORMS if p != current]
        alt_platform = alts[0] if alts else current

    existing_ids = [i["id"] for i in data["items"]]
    n = 1
    new_id = f"{item_id}_repost_{n}"
    while new_id in existing_ids:
        n += 1
        new_id = f"{item_id}_repost_{n}"

    clone = json.loads(json.dumps(item))
    clone.update({
        "id": new_id,
        "parent_id": item_id,
        "assigned_platform": alt_platform,
        "scheduled_date": new_date.strftime("%Y-%m-%d"),
        "status": "scheduled_repost",
        "repost_count": item.get("repost_count", 0) + 1,
        "performance": {
            "impressions": 0, "views": 0, "likes": 0,
            "comments": 0, "shares": 0, "ctr": 0.0, "engagement_rate": 0.0,
        },
    })
    item["repost_count"] = item.get("repost_count", 0) + 1
    item["status"] = "reposted" if is_winner(item) else item.get("status")
    data["items"].append(clone)
    data["items"] = sorted(data["items"], key=lambda x: x["scheduled_date"])
    data["total_allocated"] = len(data["items"])
    save_bank(data)
    return clone
