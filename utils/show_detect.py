"""Detect comedy vs interview, laughter tails, and hook-worthy sentences."""

from __future__ import annotations

import re
import statistics

from config.show_style import (
    HOOK_PATTERNS,
    INTERVIEW_KEYWORDS,
    HINGLISH_FIXES,
    load_resolved,
    profile_for,
    requested_show_type,
    save_resolved,
)
from utils.sentences import flatten_words, ends_sentence

_HOOK_RE = [re.compile(p, re.I) for p in HOOK_PATTERNS]
_KEYWORD_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in INTERVIEW_KEYWORDS) + r")\b",
    re.I,
)


def keyword_hits(text: str) -> int:
    return len(_KEYWORD_RE.findall(text or ""))


def is_hook_line(text: str) -> bool:
    token = text or ""
    if any(pat.search(token) for pat in _HOOK_RE):
        return True
    if keyword_hits(token) >= 2:
        return True
    if "?" in token and len(token.split()) <= 18:
        return True
    return False


def hook_sentence(rows):
    """The strongest sentence in a timed transcript window."""
    best = None
    best_score = -1
    for row in rows or []:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        score = keyword_hits(text) * 3
        if is_hook_line(text):
            score += 6
        if ends_sentence(text):
            score += 1
        if score > best_score:
            best_score = score
            best = row
    return best if best_score > 0 else None


def reaction_seconds(rms_series, speech_end, window_end, hold=1.8):
    """How long crowd energy continues after the last spoken word."""
    if not rms_series or speech_end is None:
        return 0.0
    speech = [float(r.get("rms") or 0) for r in rms_series if float(r.get("t") or 0) < speech_end]
    after = [
        r for r in rms_series
        if speech_end <= float(r.get("t") or 0) <= min(float(window_end), speech_end + hold + 0.6)
    ]
    if not after:
        return 0.0
    baseline = statistics.median(speech) if speech else 0.0
    if baseline <= 1:
        baseline = statistics.mean(speech) if speech else 800.0
    peak = max(float(r.get("rms") or 0) for r in after)
    if peak < baseline * 1.25:
        return 0.0
    last_hot = speech_end
    for row in after:
        if float(row.get("rms") or 0) >= baseline * 1.15:
            last_hot = float(row["t"])
    return round(min(hold, max(0.6, last_hot - speech_end + 0.35)), 2)


def laughter_in_span(rms_series, start, end, segments=None):
    words = flatten_words(segments or [])
    last_word = start
    for row in words:
        if row["end"] <= end:
            last_word = max(last_word, row["end"])
    tail = reaction_seconds(rms_series, last_word, end)
    return tail >= 0.6, tail


def gap_is_reaction(rms_series, t0, t1):
    """True when a pause is actually a laugh, not dead air."""
    if t1 <= t0 or not rms_series:
        return False
    span = [float(r.get("rms") or 0) for r in rms_series if t0 - 0.05 <= float(r.get("t") or 0) < t1 + 0.05]
    if not span:
        return False
    around = [float(r.get("rms") or 0) for r in rms_series if abs(float(r.get("t") or 0) - t0) < 4]
    baseline = statistics.median(around) if around else 0.0
    return max(span) >= max(baseline * 1.2, 1.0)


def detect_show(analysis, rms_hints=None):
    requested = requested_show_type()
    if requested != "auto":
        return save_resolved(requested, "creator picked this show type")

    laughs = 0
    hooks = 0
    for clip in analysis or []:
        signals = clip.get("visual_signals") or {}
        if signals.get("laughter") or float(signals.get("reaction_seconds") or 0) >= 0.8:
            laughs += 1
        if is_hook_line(clip.get("text") or "") or keyword_hits(clip.get("text") or "") >= 2:
            hooks += 1
    if rms_hints and rms_hints.get("laughs", 0) > laughs:
        laughs = rms_hints["laughs"]
    if laughs >= 2 and laughs >= hooks:
        return save_resolved("comedy", f"{laughs} laugh spikes vs {hooks} insight hooks")
    return save_resolved("interview", f"{hooks} insight hooks vs {laughs} laugh spikes")


def fix_hinglish(text: str) -> str:
    out = text or ""
    for bad, good in HINGLISH_FIXES.items():
        out = re.sub(rf"\b{re.escape(bad)}\b", good, out, flags=re.I)
    return out


def caption_words(words, show=None):
    show = show or load_resolved()
    if show.get("id") != "interview":
        return list(words)
    return [fix_hinglish(w) for w in words]
