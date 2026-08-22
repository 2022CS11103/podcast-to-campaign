"""How CreatorOS should watch a source: comedy panel vs insight interview.

Samay Raina / India's Got Latent needs punchlines, speaker energy, and the
audience laugh. Raj Shamani needs a shocking first line, then the context.
"""

from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BRAND_FILE = PROJECT_ROOT / "brand_context.json"
SHOW_FILE = PROJECT_ROOT / "output" / "show_profile.json"

SHOW_TYPES = ("comedy", "interview", "auto")

INTERVIEW_KEYWORDS = (
    "money", "crore", "crores", "lakh", "lakhs", "mistake", "failed",
    "fail", "hack", "secret", "truth", "never", "always", "lost",
    "rich", "poor", "business", "dhanda", "founder", "startup",
    "advice", "lesson", "regret", "first time", "nobody tells",
)

HOOK_PATTERNS = (
    r"\bi (lost|made|failed|quit|left|built)\b",
    r"\b\d+\s*(crore|lakh|percent|%|years?)\b",
    r"\bthe (truth|secret|mistake|problem) is\b",
    r"\bnobody (tells|talks|knows)\b",
    r"\bmost people\b",
)

HINGLISH_FIXES = {
    "ganda": "dhanda",
    "ghanda": "dhanda",
    "danda": "dhanda",
    "crores": "crores",
    "lack": "lakh",
    "lacks": "lakhs",
    "lac": "lakh",
    "lacs": "lakhs",
    "samai": "Samay",
    "samae": "Samay",
    "raina": "Raina",
    "shamani": "Shamani",
    "raj shamani": "Raj Shamani",
}

PROFILES = {
    "comedy": {
        "id": "comedy",
        "label": "Comedy / panel show",
        "pace": "fast",
        "goal": "funny",
        "drop_silences": True,
        "keep_reactions": True,
        "reaction_hold": 1.8,
        "hook_first": False,
        "keyword_boost": False,
        "caption_style": "hormozi",
        "layout": "center",
        "rules": (
            "This is a comedy or panel show. Hunt punchlines and crowd reaction.\n"
            "- Rank audio spikes after a joke (laughter, clapping) as viral.\n"
            "- End 1.5–2s after the punchline so the audience reaction is not cut off.\n"
            "- Do not jump-cut through laughter. A laugh is the payoff, not dead air.\n"
            "- Open on the setup line that makes the punchline land, then the laugh.\n"
            "- Captions are aggressive Hormozi-style: few words, keyword pop."
        ),
    },
    "interview": {
        "id": "interview",
        "label": "Insight interview",
        "pace": "medium",
        "goal": "educational",
        "drop_silences": True,
        "keep_reactions": False,
        "reaction_hold": 0.35,
        "hook_first": True,
        "keyword_boost": True,
        "caption_style": "hormozi",
        "layout": "center",
        "rules": (
            "This is a conversational interview. Hunt bold claims, not laughter.\n"
            "- Open on the most shocking sentence, even if it happens later in the window.\n"
            "- Then rewind into the context of how it happened.\n"
            "- Prefer passionate monologues and high-value advice (money, mistakes, secrets).\n"
            "- Fix Hinglish and Indian numbering (lakhs, crores, dhanda) in captions.\n"
            "- Keep both speakers' meaning; do not chop a revelation mid-thought."
        ),
    },
}


def requested_show_type(brand=None):
    data = brand if isinstance(brand, dict) else _read_json(BRAND_FILE)
    raw = str((data or {}).get("show_type") or "auto").strip().lower()
    if raw in ("comedy", "panel", "latent", "funny"):
        return "comedy"
    if raw in ("interview", "podcast", "insight", "business"):
        return "interview"
    return "auto"


def profile_for(show_id: str) -> dict:
    key = "comedy" if show_id == "comedy" else "interview"
    return dict(PROFILES[key])


def save_resolved(show_id: str, reason: str = ""):
    SHOW_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {**profile_for(show_id), "resolved": show_id, "reason": reason}
    SHOW_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_resolved() -> dict:
    data = _read_json(SHOW_FILE)
    if data and data.get("id") in PROFILES:
        return data
    requested = requested_show_type()
    if requested != "auto":
        return save_resolved(requested, "creator picked this show type")
    return profile_for("interview")


def _read_json(path: Path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}
