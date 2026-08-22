"""Shape content_bank items into a month-grid calendar for the frontend."""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime

PLATFORM_MARKERS = {
    "youtube_shorts": {
        "id": "youtube_shorts",
        "short": "YT",
        "label": "YouTube Shorts",
        "symbol": "▶",
        "tone": "red",
    },
    "instagram_reels": {
        "id": "instagram_reels",
        "short": "IG",
        "label": "Instagram Reels",
        "symbol": "◎",
        "tone": "pink",
    },
    "tiktok": {
        "id": "tiktok",
        "short": "TT",
        "label": "TikTok",
        "symbol": "♪",
        "tone": "mint",
    },
    "linkedin": {
        "id": "linkedin",
        "short": "in",
        "label": "LinkedIn",
        "symbol": "in",
        "tone": "blue",
    },
    "twitter": {
        "id": "twitter",
        "short": "X",
        "label": "Twitter / X",
        "symbol": "X",
        "tone": "slate",
    },
}


def _parse_date(raw):
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def marker_for(platform: str) -> dict:
    return PLATFORM_MARKERS.get(platform) or {
        "id": platform,
        "short": (platform or "?")[:2].upper(),
        "label": (platform or "Post").replace("_", " ").title(),
        "symbol": "•",
        "tone": "slate",
    }


def build_month(items, year: int, month: int, campaign_start=None):
    grouped = defaultdict(list)
    for item in items or []:
        day = _parse_date(item.get("scheduled_date"))
        if not day or day.year != year or day.month != month:
            continue
        grouped[day.isoformat()].append({
            "id": item.get("id"),
            "hook": item.get("display_hook") or item.get("hook") or "",
            "platform": item.get("assigned_platform"),
            "status": item.get("status") or "pending",
            "duration_seconds": item.get("duration_seconds"),
            "marker": marker_for(item.get("assigned_platform")),
        })

    first_weekday, days_in_month = calendar.monthrange(year, month)
    # Monday-first grid, matching a planner wall calendar.
    leading = (first_weekday) % 7
    cells = []
    for _ in range(leading):
        cells.append({"date": None, "in_month": False, "items": [], "blocked": False})
    today = date.today().isoformat()
    for day_n in range(1, days_in_month + 1):
        iso = date(year, month, day_n).isoformat()
        day_items = grouped.get(iso) or []
        cells.append({
            "date": iso,
            "day": day_n,
            "in_month": True,
            "today": iso == today,
            "items": day_items,
            "blocked": bool(day_items),
            "platforms": [row["marker"] for row in day_items],
        })
    while len(cells) % 7:
        cells.append({"date": None, "in_month": False, "items": [], "blocked": False})

    return {
        "year": year,
        "month": month,
        "label": date(year, month, 1).strftime("%B %Y"),
        "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "campaign_start_date": campaign_start,
        "blocked_days": sum(1 for cell in cells if cell.get("blocked")),
        "total_posts": sum(len(cell.get("items") or []) for cell in cells),
        "cells": cells,
        "legend": list(PLATFORM_MARKERS.values()),
    }


def from_bank(bank: dict, year=None, month=None) -> dict:
    items = bank.get("items") or []
    start = _parse_date(bank.get("campaign_start_date"))
    dates = [_parse_date(item.get("scheduled_date")) for item in items]
    dates = [d for d in dates if d]
    if year is None or month is None:
        anchor = start or (dates[0] if dates else date.today())
        year = year or anchor.year
        month = month or anchor.month
    months = sorted({(d.year, d.month) for d in dates}) or [(year, month)]
    return {
        **build_month(items, year, month, campaign_start=start.isoformat() if start else None),
        "available_months": [
            {"year": y, "month": m, "label": date(y, m, 1).strftime("%B %Y")}
            for y, m in months
        ],
    }
