"""Persistent brand + end-screen settings (brand_context.json)."""

from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BRAND_FILE = PROJECT_ROOT / "brand_context.json"
BRAND_DIR = PROJECT_ROOT / "input" / "brand"

TEMPLATES = (
    "logo_name",
    "logo_name_website",
    "logo_cta",
)

DEFAULTS = {
    "brand_name": "",
    "website": "",
    "tagline": "",
    "goal": "Brand awareness",
    "audience": "",
    "tone": "Professional",
    "show_type": "auto",
    "campaign_duration_days": 30,
    "campaign_start_date": "",
    "logo_path": "",
    "end_screen_enabled": False,
    "end_screen_duration": 3,
    "end_screen_template": "logo_name_website",
    "end_screen_cta": "",
}

BOOLEAN_KEYS = {"end_screen_enabled"}
INT_KEYS = {"end_screen_duration", "campaign_duration_days"}


def _as_bool(value, default=False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value, default: int, lo: int | None = None, hi: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if lo is not None:
        number = max(lo, number)
    if hi is not None:
        number = min(hi, number)
    return number


def display_website(url: str) -> str:
    text = (url or "").strip()
    text = re.sub(r"^https?://", "", text, flags=re.I)
    return text.rstrip("/")


def normalize(raw: dict | None) -> dict:
    data = dict(DEFAULTS)
    incoming = dict(raw or {})
    for key, default in DEFAULTS.items():
        if key not in incoming:
            continue
        value = incoming[key]
        if key in BOOLEAN_KEYS:
            data[key] = _as_bool(value, default)
        elif key == "end_screen_duration":
            data[key] = _as_int(value, default, 2, 5)
        elif key == "campaign_duration_days":
            data[key] = _as_int(value, default, 1, 365)
        elif key == "end_screen_template":
            token = str(value or default).strip()
            data[key] = token if token in TEMPLATES else default
        elif value is None:
            data[key] = default
        else:
            data[key] = value
    for key, value in incoming.items():
        if key not in data and value is not None:
            data[key] = value
    return data


def load_brand() -> dict:
    if not BRAND_FILE.exists():
        return dict(DEFAULTS)
    try:
        with open(BRAND_FILE, "r", encoding="utf-8") as handle:
            return normalize(json.load(handle) or {})
    except (OSError, json.JSONDecodeError, TypeError):
        return dict(DEFAULTS)


def save_brand(payload: dict) -> dict:
    data = normalize(payload)
    BRAND_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(BRAND_FILE, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return data


def merge_and_save(incoming: dict | None) -> dict:
    """Overlay campaign/job fields onto the saved brand without wiping the logo."""
    current = load_brand()
    for key, value in dict(incoming or {}).items():
        if key in BOOLEAN_KEYS:
            if value is not None:
                current[key] = _as_bool(value)
            continue
        if key == "end_screen_duration":
            if value not in (None, ""):
                current[key] = _as_int(value, current.get(key) or 3, 2, 5)
            continue
        if key == "logo_path" and value in (None, ""):
            continue
        if value is None:
            continue
        current[key] = value
    return save_brand(current)


def resolve_logo_path(raw: str | None) -> Path | None:
    text = (raw or "").strip()
    if not text:
        return None
    path = Path(text)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    try:
        path = path.resolve()
        path.relative_to(PROJECT_ROOT.resolve())
    except (OSError, ValueError):
        return None
    if path.is_file():
        return path
    return None


def public_brand(data: dict | None = None) -> dict:
    brand = normalize(data if data is not None else load_brand())
    logo = resolve_logo_path(brand.get("logo_path"))
    return {
        **brand,
        "has_logo": bool(logo),
        "logo_url": "/brand/logo" if logo else "",
    }
