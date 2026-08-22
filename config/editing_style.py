"""Numeric side of config/editing_rules.md.

The director plans against these numbers, the executor renders against them,
and the quality gate scores the finished file against them, so the three
layers cannot drift apart.
"""

from pathlib import Path

RULES_FILE = Path(__file__).resolve().parent / "editing_rules.md"

# Pace decides jump-cut aggression, zoom range, and how many shots a cut carries.
PACE_PROFILES = {
    "fast": {
        "silence_gap": 0.22,
        "breath": 0.06,
        "cuts_per_minute": (14, 34),
        "max_shots": 10,
        "zoom": (1.14, 1.28),
        "punch_ins": (2, 3),
        "punch_duration": (0.5, 1.0),
    },
    "medium": {
        "silence_gap": 0.40,
        "breath": 0.08,
        "cuts_per_minute": (7, 20),
        "max_shots": 8,
        "zoom": (1.12, 1.24),
        "punch_ins": (1, 3),
        "punch_duration": (0.5, 1.0),
    },
    "hold": {
        "silence_gap": 0.85,
        "breath": 0.12,
        "cuts_per_minute": (2, 10),
        "max_shots": 5,
        "zoom": (1.10, 1.18),
        "punch_ins": (1, 2),
        "punch_duration": (0.55, 1.0),
    },
}

DEFAULT_PACE = "medium"

GOAL_PACE = {
    "funny": "fast",
    "hype": "fast",
    "educational": "medium",
    "emotional": "medium",
    "story": "hold",
}

# Shot and zoom mechanics shared by every pace.
MIN_SHOT_SECONDS = 0.35
PUNCH_MIN_SPACING = 1.5
PUNCH_HEAD_GUARD = 0.30
PUNCH_TAIL_GUARD = 0.40

# Caption shape.
CAPTION = {
    "max_words_per_cue": 4,
    "max_lines": 2,
    "min_cue_seconds": 0.45,
    "max_cue_seconds": 2.1,
    "hook_hold_seconds": 1.45,
    "emphasize_max": 4,
}

# How far the director may tighten a ranked window to honour the rule book.
TRIM = {
    "max_fraction": 0.20,
    "min_seconds": 12.0,
    "max_lead_silence": 0.60,
    "max_tail_silence": 0.35,
}

# The gate a rendered file has to clear before it can be published.
QUALITY_RUBRIC = {
    "width": 1080,
    "height": 1920,
    "min_seconds": 8.0,
    "max_seconds": 62.0,
    "require_audio": True,
    "min_cues_per_10s": 1.5,
    "min_shots_when_cutting": 2,
    "max_lead_silence": 1.20,
    "pass_score": 80,
}


def profile_for(pace: str) -> dict:
    """Pace profile, falling back to the default rather than raising."""
    return PACE_PROFILES.get(pace) or PACE_PROFILES[DEFAULT_PACE]


def normalize_pace(pace, goal=None) -> str:
    if pace in PACE_PROFILES:
        return pace
    return GOAL_PACE.get((goal or "").lower(), DEFAULT_PACE)


def rules_text(max_chars: int = 6000) -> str:
    """The rule book as prompt context. Missing file is not fatal."""
    try:
        return RULES_FILE.read_text(encoding="utf-8")[:max_chars]
    except OSError:
        return ""
