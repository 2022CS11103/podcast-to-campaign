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
QUESTION_START = re.compile(
    r"^\s*(can|could|would|will|do|does|did|are|is|was|were|have|has|had|"
    r"how|what|why|when|where|who|whom|whose|tell me|talk about|"
    r"can you|could you|would you|do you|did you)\b",
    re.I,
)
CLOSURE_PHRASE = re.compile(
    r"\b(that'?s where it started|that was the story|that'?s the story|"
    r"so that'?s (the|my|it)|and that'?s (it|where)|does that make sense|"
    r"hope that (answers|helps)|great question)\b",
    re.I,
)
MIN_ANSWER_SECONDS = 10.0
MIN_ANSWER_SENTENCES = 2


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


def timed_segments(segments):
    rows = []
    for seg in segments or []:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        try:
            rows.append({
                "start": float(seg["start"]),
                "end": float(seg["end"]),
                "text": text,
            })
        except (TypeError, ValueError, KeyError):
            continue
    rows.sort(key=lambda row: row["start"])
    return rows


def _gap_after(rows, idx):
    if idx >= len(rows) - 1:
        return 99.0
    return rows[idx + 1]["start"] - rows[idx]["end"]


def ends_on_question(rows, end, lookback=12.0):
    """True when the window ends on an interview question, not a guest answer."""
    if not rows:
        return False
    tail_parts = []
    for row in rows:
        if row["end"] > end - lookback and row["start"] < end - 0.05:
            tail_parts.append(row["text"])
    tail = " ".join(tail_parts).strip()
    if tail.rstrip().endswith("?"):
        return True
    closing = None
    for row in rows:
        if row["start"] < end + 0.02 and row["end"] >= end - 0.5:
            if "?" in row["text"]:
                closing = row
    if closing:
        return True
    for row in rows:
        if row["start"] < end + 0.02 and row["end"] >= end - 0.5:
            closing = row
    if not closing:
        return False
    return "?" in closing["text"]


def extend_for_answer(start, end, rows, max_seconds, source_end=None):
    """Pull the guest reply in when a clip currently stops on the host's question."""
    if not ends_on_question(rows, end):
        return start, end

    idx0 = 0
    for i, row in enumerate(rows):
        if row["end"] >= end - 0.4:
            idx0 = i
            break

    new_end = end
    answer_start = None
    sentences = 0
    cap = source_end if source_end is not None else (rows[-1]["end"] if rows else end + max_seconds)

    for i in range(idx0, len(rows)):
        row = rows[i]
        if row["start"] < end - 0.1 and "?" in row["text"]:
            continue
        if row["start"] >= end - 0.15 and answer_start is None:
            answer_start = row["start"]
        if answer_start is None:
            continue
        new_end = min(row["end"], cap)
        if ends_sentence(row["text"]):
            sentences += 1
        answered = answer_start is not None and (new_end - answer_start) >= MIN_ANSWER_SECONDS
        if CLOSURE_PHRASE.search(row["text"]) and answered and sentences >= MIN_ANSWER_SENTENCES:
            break
        if answered and sentences >= MIN_ANSWER_SENTENCES and _gap_after(rows, i) >= PAUSE_NEW_THOUGHT:
            break
        if row["end"] >= cap:
            break

    if answer_start is None or new_end <= end + 0.5:
        return start, end
    return start, new_end


def trim_head_for_fit(start, end, rows, max_seconds, min_seconds):
    """Drop host preamble before cutting off the guest's payoff."""
    if end - start <= max_seconds:
        return start, end

    q_idx = None
    for i, row in enumerate(rows):
        if row["start"] < start - 0.1 or row["end"] > end + 0.1:
            continue
        if "?" in row["text"] or QUESTION_START.match(row["text"]):
            q_idx = i

    if q_idx is not None:
        keep_from = q_idx
        for back in range(1, 6):
            j = q_idx - back
            if j < 0 or rows[j]["start"] < start - 0.1:
                break
            if rows[q_idx]["start"] - rows[j]["start"] > 12.0:
                break
            keep_from = j
        candidate_start = max(start, rows[keep_from]["start"])
        if end - candidate_start <= max_seconds and end - candidate_start >= min_seconds:
            return candidate_start, end
        if end - candidate_start > max_seconds:
            target_end = candidate_start + max_seconds
            i1 = 0
            for i, row in enumerate(rows):
                if row["end"] <= target_end + 0.2:
                    i1 = i
            while i1 > keep_from and not ends_sentence(rows[i1]["text"]):
                i1 -= 1
            trimmed_end = rows[i1]["end"]
            if trimmed_end - candidate_start >= min_seconds:
                return candidate_start, trimmed_end

    i0 = 0
    for i, row in enumerate(rows):
        if row["start"] >= start - 0.1:
            i0 = i
            break
    while i0 < len(rows) - 1 and end - rows[i0]["start"] > max_seconds:
        i0 += 1
        if end - rows[i0]["start"] <= max_seconds:
            break
    new_start = max(start, rows[i0]["start"])
    if end - new_start < min_seconds:
        return start, end
    return new_start, end


def conversation_complete(rows, start, end):
    if ends_on_question(rows, end):
        return False

    q_time = None
    for row in rows:
        if start <= row["start"] < end and (
            "?" in row["text"] or QUESTION_START.match(row["text"])
        ):
            q_time = row["end"]
    if q_time is None:
        return True

    answer_sents = 0
    answer_secs = 0.0
    for row in rows:
        if row["start"] < q_time - 0.2:
            continue
        if row["end"] > end + 0.15:
            continue
        if row["start"] >= q_time - 0.2:
            answer_secs = max(answer_secs, min(row["end"], end) - q_time)
        if row["start"] >= q_time - 0.2 and ends_sentence(row["text"]) and row["end"] <= end + 0.1:
            answer_sents += 1
    return (
        answer_sents >= MIN_ANSWER_SENTENCES
        and answer_secs >= MIN_ANSWER_SECONDS * 0.7
    )


def fit_conversation_window(
    start,
    end,
    segments,
    max_seconds=57.0,
    min_seconds=12.0,
    source_end=None,
):
    """Snap edges, include a full Q&A exchange, then fit inside the Shorts cap."""
    try:
        start = float(start)
        end = float(end)
        max_seconds = float(max_seconds)
        min_seconds = float(min_seconds)
    except (TypeError, ValueError):
        return start, end

    rows = timed_segments(segments)
    if not rows:
        start, end = snap_window(start, end, segments)
        return trim_to_max_duration(start, end, segments, max_seconds, min_seconds)

    cap = source_end if source_end is not None else rows[-1]["end"]
    # Extend before snap so we do not lose a question mark on the window edge.
    start, end = extend_for_answer(start, end, rows, max_seconds, source_end=cap)
    start, end = snap_window(start, end, segments)
    rows = timed_segments(segments)
    if ends_on_question(rows, end):
        start, end = extend_for_answer(start, end, rows, max_seconds, source_end=cap)

    if end - start > max_seconds:
        start, end = trim_head_for_fit(start, end, rows, max_seconds, min_seconds)
    if end - start > max_seconds:
        start, end = trim_to_max_duration(start, end, segments, max_seconds, min_seconds)
    return round(start, 2), round(end, 2)


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


def trim_to_max_duration(
    start,
    end,
    segments,
    max_seconds=57.0,
    min_seconds=12.0,
):
    """Snap to full sentences, then shorten from the tail if over the Shorts/Reels cap."""
    try:
        start = float(start)
        end = float(end)
        max_seconds = float(max_seconds)
        min_seconds = float(min_seconds)
    except (TypeError, ValueError):
        return start, end

    start, end = snap_window(start, end, segments)
    if end - start <= max_seconds:
        return round(start, 2), round(end, 2)

    words = flatten_words(segments)
    if not words:
        return round(start, 2), round(start + max_seconds, 2)

    target = start + max_seconds
    i1 = _index_at_or_before(words, target)
    while i1 > 0 and not ends_sentence(words[i1]["word"]):
        i1 -= 1
    while i1 < len(words) - 1 and words[i1]["end"] - start < min_seconds:
        i1 += 1
        while i1 < len(words) - 1 and not ends_sentence(words[i1]["word"]):
            i1 += 1

    t1 = float(words[min(i1, len(words) - 1)]["end"])
    if t1 - start < min_seconds:
        t1 = min(end, start + max_seconds)
        _, t1 = snap_window(start, t1, segments)
    if t1 - start > max_seconds:
        target = start + max_seconds
        i1 = _index_at_or_before(words, target)
        while i1 > 0 and not ends_sentence(words[i1]["word"]):
            i1 -= 1
        t1 = float(words[i1]["end"])
        while i1 > 0 and t1 - start > max_seconds:
            i1 -= 1
            if not ends_sentence(words[i1]["word"]):
                while i1 > 0 and not ends_sentence(words[i1]["word"]):
                    i1 -= 1
            t1 = float(words[i1]["end"])
    if t1 <= start:
        return round(start, 2), round(min(end, start + max_seconds), 2)
    return round(start, 2), round(t1, 2)


def apply_to_clip(clip, segments, max_expand=MAX_EXPAND, max_duration=57.0):
    """Rewrite a clip so its window and transcript cover whole conversational beats."""
    if not clip:
        return clip
    start, end = fit_conversation_window(
        clip.get("start"),
        clip.get("end"),
        segments,
        max_seconds=max_duration,
        min_seconds=12.0,
    )
    clip["start"] = start
    clip["end"] = end
    clip["duration_seconds"] = round(end - start, 2)
    rows = timed_segments(segments)
    clip["ends_on_question"] = ends_on_question(rows, end)
    clip["conversation_complete"] = conversation_complete(rows, start, end)
    if not clip["conversation_complete"]:
        clip["payoff_arrives"] = False
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
