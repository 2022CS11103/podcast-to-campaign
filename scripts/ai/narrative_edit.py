"""Pack a Short like an editor: hook, context, payoff — not one continuous take.

A good clip is a story. This layer scores sentences inside a ranked window,
keeps the ones that carry the arc, and drops the ramble in the middle. The
executor then stitches those beats, even when they are not contiguous.
"""

from __future__ import annotations

import re

from config.editing_style import TRIM

CLAIM = re.compile(
    r"\b(\d+|crore|lakh|percent|%|never|always|secret|truth|mistake|"
    r"nobody|everyone|failed|quit|built|lost|won|crazy|insane)\b",
    re.I,
)
QUESTION = re.compile(r"\?")
HOOKY = re.compile(
    r"\b(wait|actually|the thing is|here's|here is|nobody|listen|"
    r"the truth|most people|stop)\b",
    re.I,
)


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[A-Za-z0-9']+", text or "") if w]


def score_sentence(row: dict, hook_line: str = "") -> float:
    text = (row.get("text") or "").strip()
    if not text:
        return 0.0
    n = len(_words(text))
    score = min(n, 22) / 22.0 * 4.0
    hook = (hook_line or "").strip().lower()
    body = text.lower()
    if hook and (hook[:18] in body or body[:18] in hook):
        score += 7.0
    if CLAIM.search(text):
        score += 2.6
    if QUESTION.search(text):
        score += 1.4
    if HOOKY.search(text):
        score += 1.8
    if n < 4:
        score -= 1.5
    if n > 42:
        score -= 1.2
    return score


def _span(row: dict) -> tuple[float, float]:
    return float(row["start"]), float(row["end"])


def _overlap(a: dict, b: dict) -> bool:
    a0, a1 = _span(a)
    b0, b1 = _span(b)
    return min(a1, b1) - max(a0, b0) > 0.2


def pack_beats(rows, hook_line="", payoff_at=None, hook_first=False, min_keep=None):
    """Return a shot_order of 2–4 beats, or [] to keep a continuous trim.

    [] means the window is already tight — stitching would only add jumpiness.
    """
    sentences = [
        row for row in (rows or [])
        if (row.get("text") or "").strip()
        and float(row.get("end") or 0) > float(row.get("start") or 0)
    ]
    if len(sentences) < 3:
        return []

    floor = float(min_keep if min_keep is not None else TRIM["min_seconds"])
    ranked = sorted(sentences, key=lambda row: score_sentence(row, hook_line), reverse=True)
    hook = ranked[0]
    payoff = sentences[-1]
    if payoff_at is not None:
        try:
            t = float(payoff_at)
            payoff = min(sentences, key=lambda row: abs(float(row["end"]) - t))
        except (TypeError, ValueError):
            pass

    keep = []
    for row in (hook, payoff):
        if not any(_overlap(row, kept) for kept in keep):
            keep.append(row)

    for row in ranked[1:]:
        if len(keep) >= 4:
            break
        if any(_overlap(row, kept) for kept in keep):
            continue
        if score_sentence(row, hook_line) < 2.4 and len(keep) >= 3:
            continue
        keep.append(row)

    keep_sorted = sorted(keep, key=lambda row: float(row["start"]))
    covered = sum(float(r["end"]) - float(r["start"]) for r in keep_sorted)
    full = float(sentences[-1]["end"]) - float(sentences[0]["start"])
    dropped = full - covered
    if dropped < 1.6 and not hook_first:
        return []
    if covered < min(floor, full) * 0.72:
        return []

    rest = [row for row in keep_sorted if row is not hook]
    if hook_first and float(hook["start"]) > float(sentences[0]["start"]) + 1.4:
        ordered = [hook, *rest]
    else:
        ordered = keep_sorted

    beats = []
    roles = ["hook", "context", "statement", "payoff"]
    for i, row in enumerate(ordered):
        role = roles[min(i, len(roles) - 1)]
        if row is hook:
            role = "hook"
        elif row is payoff:
            role = "payoff"
        beats.append({
            "role": role,
            "src_start": round(float(row["start"]), 2),
            "src_end": round(float(row["end"]), 2),
            "why": role,
        })
    return beats


def suggest_broll(plan: dict, rows=None, max_cards=2):
    """Kinetic title cards on the claim / payoff — not stock footage."""
    emphasize = [str(w).strip() for w in (plan.get("emphasize") or []) if str(w).strip()]
    hook = (plan.get("hook_line") or "").strip()
    payoff_at = plan.get("payoff_at")
    trim = plan.get("trim") if isinstance(plan.get("trim"), dict) else {}
    try:
        start = float(trim.get("start") or 0)
        end = float(trim.get("end") or start + 20)
    except (TypeError, ValueError):
        start, end = 0.0, 20.0

    title = " ".join(emphasize[:3]).upper()
    if not title:
        title = " ".join(_words(hook)[:4]).upper()
    if not title:
        return []

    at = end - 2.4
    try:
        if payoff_at is not None:
            at = float(payoff_at)
    except (TypeError, ValueError):
        pass
    at = min(max(at, start + 1.6), end - 0.9)

    cards = [{
        "at_src": round(at, 2),
        "duration": 1.05,
        "title": title[:28],
        "subtitle": " ".join(_words(hook)[4:10])[:42],
    }]

    claim_row = None
    for row in rows or []:
        text = row.get("text") or ""
        if CLAIM.search(text) and abs(float(row.get("start") or 0) - at) > 1.8:
            claim_row = row
            break
    if claim_row and len(cards) < max_cards:
        claim_title = " ".join(_words(claim_row.get("text") or "")[:4]).upper()
        if claim_title and claim_title != title:
            cards.append({
                "at_src": round(float(claim_row["start"]), 2),
                "duration": 0.95,
                "title": claim_title[:28],
                "subtitle": "",
            })
    return cards[:max_cards]
