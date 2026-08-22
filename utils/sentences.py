"""Snap clip windows to complete sentences so Reels never start or die mid-thought."""

from __future__ import annotations

import re

SENTENCE_END = re.compile(r'[.!?…]["\'\u201d\u2019)\]]*$')
CONTINUATION = re.compile(
    r"^(and|but|so|or|because|which|that|then|also|just|like)\b",
    re.I,
)
PAUSE_NEW_THOUGHT = 0.55
MAX_EXPAND = 12.0


def ends_sentence(text: str) -> bool:
    token = (text or "").strip()
    if not token:
        return False
    return bool(SENTENCE_END.search(token))


def looks_like_start(text: str, prev_text: str = "", pause: float = 0.0):
    token = (text or "").strip()
    if not token:
        return False
    if pause >= PAUSE_NEW_THOUGHT:
        return True
    if ends_sentence(prev_text):
        return True
    first = next((ch for ch in token if ch.isalnum()), "")
    if first.islower() or CONTINUATION.match(token):
        return False
    return True


def flatten_words(segments):
    rows = []
    for seg in segments or []:
        words = seg.get("words") or []
        if words:
            for word in words:
                token = (word.get("word") or "").strip()
                if not token:
                    continue
                try:
                    rows.append({
                        "word": token,
                        "start": float(word["start"]),
                        "end": float(word["end"]),
                    })
                except (TypeError, ValueError, KeyError):
                    continue
            continue
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        try:
            rows.append({
                "word": text,
                "start": float(seg.get("start") or 0),
                "end": float(seg.get("end") or 0),
            })
        except (TypeError, ValueError):
            continue
    rows.sort(key=lambda row: row["start"])
    return rows


def text_between(segments, start, end):
    parts = [
        row["word"]
        for row in flatten_words(segments)
        if row["end"] > start and row["start"] < end
    ]
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _index_at_or_after(words, t):
    for i, row in enumerate(words):
        if row["end"] > t:
            return i
    return max(0, len(words) - 1)


def _index_at_or_before(words, t):
    last = 0
    for i, row in enumerate(words):
        if row["start"] < t:
            last = i
    return last


def snap_window(start, end, segments, max_expand=MAX_EXPAND):
    """Move start back and end forward until both edges are sentence boundaries."""
    try:
        start = float(start)
        end = float(end)
    except (TypeError, ValueError):
        return start, end
    words = flatten_words(segments)
    if not words:
        return round(start, 2), round(end, 2)

    i0 = _index_at_or_after(words, start)
    while i0 > 0:
        prev = words[i0 - 1]
        gap = words[i0]["start"] - prev["end"]
        if ends_sentence(prev["word"]) or gap >= PAUSE_NEW_THOUGHT:
            break
        if start - prev["start"] > max_expand:
            break
        i0 -= 1
    if i0 > 0 and CONTINUATION.match(words[i0]["word"]):
        i0 -= 1
        while i0 > 0:
            prev = words[i0 - 1]
            gap = words[i0]["start"] - prev["end"]
            if ends_sentence(prev["word"]) or gap >= PAUSE_NEW_THOUGHT:
                break
            if start - prev["start"] > max_expand:
                break
            i0 -= 1

    i1 = _index_at_or_before(words, end)
    while i1 < len(words) - 1 and not ends_sentence(words[i1]["word"]):
        nxt = words[i1 + 1]
        gap = nxt["start"] - words[i1]["end"]
        if gap >= PAUSE_NEW_THOUGHT:
            break
        if nxt["end"] - end > max_expand:
            break
        i1 += 1

    t0 = words[i0]["start"]
    t1 = words[i1]["end"]
    if t1 <= t0:
        return round(start, 2), round(end, 2)
    return round(t0, 2), round(t1, 2)


def apply_to_clip(clip, segments, max_expand=MAX_EXPAND):
    """Rewrite a clip so its window and transcript cover whole sentences."""
    if not clip:
        return clip
    start, end = snap_window(clip.get("start"), clip.get("end"), segments, max_expand)
    clip["start"] = start
    clip["end"] = end
    clip["duration_seconds"] = round(end - start, 2)
    text = text_between(segments, start, end)
    if text:
        clip["text"] = text
        clip["word_count"] = len(text.split())
        clip["starts_mid_thought"] = bool(
            CONTINUATION.match(text) or not looks_like_start(text)
        )
    return clip


def is_cut_point(prev_word, next_word, gap, min_gap):
    """Jump cuts only between sentences, or on a long pause that is a new thought."""
    if gap < min_gap:
        return False
    if ends_sentence(prev_word or ""):
        return True
    if gap >= max(min_gap, 0.70):
        return True
    return False
