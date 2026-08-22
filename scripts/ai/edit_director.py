"""
Reasoning layer: turn understanding (transcript, scores, visual energy)
into a sequence of editing operations — Mosaic-style, not "trim and ship".

The director reads config/editing_rules.md, sees the clip's transcript with
real timecodes, and emits an edit decision list the executor can render
without guessing.
"""

from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from config.editing_style import (
    CAPTION,
    MIN_SHOT_SECONDS,
    PUNCH_HEAD_GUARD,
    PUNCH_MIN_SPACING,
    PUNCH_TAIL_GUARD,
    TRIM,
    normalize_pace,
    profile_for,
    rules_text,
)
from utils.sentences import snap_window
from utils.show_detect import hook_sentence
from config.show_style import load_resolved
from utils.gemini_clients import generate_content
from utils.cost_tracker import log_gemini_call

DIRECTOR_PROMPT = """You are a short-form video editor (TikTok/Reels/Shorts), not a clip exporter.

Creative goal: make this moment feel edited by a human — punchy, not a raw extract.

Follow this rule book exactly. Every number in it is enforced downstream.

--- RULE BOOK ---
{rules}

--- SHOW TYPE ---
{show_rules}
--- END RULE BOOK ---

Return ONLY JSON:
{{
  "goal": "funny|emotional|educational|hype|story",
  "pace": "fast|medium|hold",
  "reason": "one sentence of editorial intent",
  "hook_line": "the exact sentence from the transcript that should open the cut",
  "trim": {{"start": 12.0, "end": 44.5}},
  "drop_silences": true,
  "punch_ins": [
    {{"at_src": 12.4, "duration": 0.7, "zoom": 1.18, "why": "hook"}}
  ],
  "caption_mode": "keyword_pop",
  "emphasize": ["word1", "word2"],
  "payoff_at": 30.2,
  "retention_risk": "one sentence naming the likely drop-off point"
}}

Hard constraints:
- Every time value is seconds on the SOURCE timeline, inside clip_start..clip_end.
- "trim" opens on the first word of a complete sentence and ends on the last
  word of a complete sentence. Never start on a continuation (and/but/so/which).
  Never end mid-clause. Keep at least {min_keep}s and never cut more than
  {max_trim_pct}% of the window. Return the original window if it is already tight.
- Use the timed transcript below to place at_src, payoff_at, and trim on real
  spoken moments. Do not invent timecodes.
- punch_ins: {punch_lo} to {punch_hi} entries for this pace, zoom between
  {zoom_lo} and {zoom_hi}, duration {dur_lo}-{dur_hi}s, at least {spacing}s apart.
- emphasize: 1-{emph_max} punchy words that actually appear in the transcript.

clip_start: {start}
clip_end: {end}
hook: {hook}
angle: {angle}
highlight_reason: {why}
word_score: {words} visual: {visual} audio: {audio}

timed transcript (source seconds):
{timed}
"""


EMPHASIS_STOPWORDS = {
    "the", "a", "an", "to", "of", "and", "i", "i'm", "im", "just", "this",
    "that", "is", "was", "were", "it", "its", "it's", "for", "but", "so",
    "with", "you", "your", "they", "them", "not", "are", "has", "have",
}


def _hook_words(hook):
    words = re.findall(r"[A-Za-z']+", hook or "")
    kept = [w for w in words if w.lower() not in EMPHASIS_STOPWORDS and len(w) >= 3]
    return kept[:4] or words[:3]


def clip_segments(clip, segments):
    """Transcript segments overlapping the clip window."""
    start = float(clip["start"])
    end = float(clip["end"])
    rows = []
    for seg in segments or []:
        try:
            a = float(seg.get("start") or 0)
            b = float(seg.get("end") or 0)
        except (TypeError, ValueError):
            continue
        if b <= start or a >= end:
            continue
        text = (seg.get("text") or "").strip()
        if text:
            rows.append({"start": a, "end": b, "text": text, "words": seg.get("words") or []})
    return rows


def timed_transcript(rows, limit=1800):
    lines = [f"[{row['start']:.1f}-{row['end']:.1f}] {row['text']}" for row in rows]
    out = "\n".join(lines)
    return out[:limit] if out else "(no transcript for this window)"


def fallback_plan(clip, rows=None):
    start = float(clip["start"])
    end = float(clip["end"])
    dur = max(1.0, end - start)
    reason = (clip.get("highlight_reason") or "").lower()
    angle = (clip.get("content_angle") or "").lower()
    funny = any(k in reason + " " + angle for k in ("loud", "funny", "emotion", "hype", "share"))
    pace = "fast" if funny else "medium"
    hook = clip.get("hook") or ""
    punchline_at = min(end - 0.8, start + dur * (0.62 if pace == "fast" else 0.72))
    # Cold-open on the first spoken word rather than on whatever silence the
    # ranker's window happened to start with.
    trim_start = start
    if rows:
        first = float(rows[0]["start"])
        if 0 < first - start <= TRIM["max_fraction"] * dur:
            trim_start = max(start, first - 0.15)
    trim_start, trim_end = snap_window(trim_start, end, rows)
    return {
        "goal": "funny" if funny else "hook",
        "pace": pace,
        "reason": (
            "Fast cuts and a payoff zoom - treat this like a Short, not a raw take."
            if pace == "fast"
            else "Hold the thought, punch in on the hook and the close."
        ),
        "hook_line": (rows[0]["text"] if rows else hook)[:180],
        "trim": {"start": round(trim_start, 2), "end": round(trim_end, 2)},
        "drop_silences": pace == "fast",
        "punch_ins": [
            {"at_src": round(trim_start + 0.35, 2), "duration": 0.8, "zoom": 1.16, "why": "open hook"},
            {"at_src": round(punchline_at, 2), "duration": 0.85, "zoom": 1.22, "why": "payoff"},
        ],
        "caption_mode": "keyword_pop",
        "emphasize": _hook_words(hook),
        "payoff_at": round(punchline_at, 2),
        "retention_risk": "Opening line has to land in the first two seconds.",
    }


def _parse(raw):
    cleaned = (raw or "").replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(cleaned)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _clamp_trim(plan, clip, rows, segments=None):
    """Keep the director's tightening inside the rule book's limits."""
    start = float(clip["start"])
    end = float(clip["end"])
    span = end - start
    trim = plan.get("trim") if isinstance(plan.get("trim"), dict) else {}
    try:
        t0 = float(trim.get("start", start))
        t1 = float(trim.get("end", end))
    except (TypeError, ValueError):
        t0, t1 = snap_window(start, end, segments or rows)
        return {"start": round(t0, 2), "end": round(t1, 2)}

    t0 = min(max(t0, start - 12.0), end)
    t1 = min(max(t1, start), end + 12.0)
    if t1 - t0 < MIN_SHOT_SECONDS:
        t0, t1 = start, end

    budget = TRIM["max_fraction"] * span
    if (t0 - start) + (end - t1) > budget and t1 <= end and t0 >= start:
        # Spend the trim budget on the head first: a cold open buys more
        # retention than a tidy ending.
        head = min(max(0.0, t0 - start), budget)
        t0 = start + head
        t1 = end - max(0.0, budget - head)
    floor = min(TRIM["min_seconds"], span)
    if t1 - t0 < floor:
        t1 = min(end + 12.0, t0 + floor)
        if t1 - t0 < floor:
            t0 = max(start - 12.0, t1 - floor)

    pool = segments or rows
    t0, t1 = snap_window(t0, t1, pool)
    show = load_resolved()
    if show.get("keep_reactions"):
        extra = float((clip.get("visual_signals") or {}).get("reaction_seconds") or 0)
        hold = float(show.get("reaction_hold") or 1.8)
        if extra >= 0.6:
            t1 = round(t1 + min(hold, extra), 2)
        else:
            t1 = round(t1 + 1.5, 2)
    return {"start": round(t0, 2), "end": round(t1, 2)}


def _clamp_punches(plan, pace, window):
    start, end = window
    profile = profile_for(pace)
    zoom_lo, zoom_hi = profile["zoom"]
    dur_lo, dur_hi = profile["punch_duration"]
    punch_lo, punch_hi = profile["punch_ins"]

    candidates = []
    for item in plan.get("punch_ins") or []:
        try:
            at = float(item.get("at_src"))
            dur = float(item.get("duration") or dur_lo)
            zoom = float(item.get("zoom") or zoom_lo)
        except (TypeError, ValueError):
            continue
        dur = min(dur_hi, max(dur_lo, dur))
        at = min(max(at, start + PUNCH_HEAD_GUARD), end - PUNCH_TAIL_GUARD - dur)
        if at < start:
            continue
        candidates.append({
            "at_src": round(at, 2),
            "duration": round(dur, 2),
            "zoom": round(min(zoom_hi, max(zoom_lo, zoom)), 2),
            "why": str(item.get("why") or "beat")[:60],
        })

    candidates.sort(key=lambda p: p["at_src"])
    spaced = []
    for punch in candidates:
        if spaced and punch["at_src"] - spaced[-1]["at_src"] < PUNCH_MIN_SPACING:
            continue
        spaced.append(punch)
        if len(spaced) >= punch_hi:
            break
    if len(spaced) < punch_lo:
        hook_at = start + PUNCH_HEAD_GUARD
        payoff_at = max(hook_at + PUNCH_MIN_SPACING, end - PUNCH_TAIL_GUARD - dur_hi)
        for at, why in ((hook_at, "open hook"), (payoff_at, "payoff")):
            if len(spaced) >= punch_lo:
                break
            if at <= start or at >= end - PUNCH_TAIL_GUARD:
                continue
            if any(abs(at - p["at_src"]) < PUNCH_MIN_SPACING for p in spaced):
                continue
            spaced.append({
                "at_src": round(at, 2),
                "duration": round(dur_hi, 2),
                "zoom": round(zoom_lo + (zoom_hi - zoom_lo) / 2, 2),
                "why": why,
            })
        spaced.sort(key=lambda p: p["at_src"])
    return spaced


def _clamp_plan(plan, clip, rows, segments=None):
    pace = normalize_pace(plan.get("pace"), plan.get("goal"))
    trim = _clamp_trim(plan, clip, rows, segments)
    window = (trim["start"], trim["end"])

    emphasize = plan.get("emphasize") or _hook_words(clip.get("hook") or "")
    if isinstance(emphasize, str):
        emphasize = [emphasize]
    emphasize = [
        str(w).strip() for w in emphasize
        if len(str(w).strip().strip(".,!?'\"")) >= 3
        and str(w).strip().lower().strip(".,!?'\"") not in EMPHASIS_STOPWORDS
    ]

    # A payoff outside the window is a hallucinated timecode, not a late payoff.
    default_payoff = window[0] + (window[1] - window[0]) * 0.68
    try:
        payoff = float(plan.get("payoff_at"))
        if not window[0] <= payoff <= window[1]:
            payoff = default_payoff
    except (TypeError, ValueError):
        payoff = default_payoff
    payoff = round(payoff, 2)
    show = load_resolved()
    shot_order = []
    if show.get("hook_first"):
        hook_row = hook_sentence(rows)
        hs = float(hook_row["start"]) if hook_row else window[0]
        he = float(hook_row["end"]) if hook_row else window[0]
        if hook_row and hs > window[0] + 1.6 and he <= window[1] + 0.2:
            shot_order = [
                {"src_start": round(hs, 2), "src_end": round(min(he, window[1]), 2), "why": "hook first"},
                {"src_start": round(window[0], 2), "src_end": round(hs, 2), "why": "context rewind"},
            ]
            if he < window[1] - 0.8:
                shot_order.append({
                    "src_start": round(he, 2),
                    "src_end": round(window[1], 2),
                    "why": "rest of the thought",
                })
            hook_line = str(plan.get("hook_line") or hook_row.get("text") or "")[:180]
        else:
            hook_line = str(plan.get("hook_line") or (rows[0]["text"] if rows else ""))[:180]
    else:
        hook_line = str(plan.get("hook_line") or (rows[0]["text"] if rows else ""))[:180]

    reaction_hold = 0.0
    if show.get("keep_reactions"):
        reaction_hold = float((clip.get("visual_signals") or {}).get("reaction_seconds") or 0)
        if reaction_hold < 0.6:
            reaction_hold = float(show.get("reaction_hold") or 1.8)

    return {
        "goal": plan.get("goal") or show.get("goal") or "hook",
        "pace": pace if plan.get("pace") else show.get("pace") or pace,
        "reason": plan.get("reason") or fallback_plan(clip, rows)["reason"],
        "hook_line": hook_line,
        "trim": trim,
        "drop_silences": bool(plan.get("drop_silences", show.get("drop_silences", pace != "hold"))),
        "punch_ins": _clamp_punches(plan, pace, window),
        "caption_mode": plan.get("caption_mode") or "keyword_pop",
        "emphasize": emphasize[: CAPTION["emphasize_max"]],
        "payoff_at": payoff,
        "retention_risk": str(plan.get("retention_risk") or "")[:200],
        "shot_order": shot_order,
        "reaction_hold": round(reaction_hold, 2) if show.get("keep_reactions") else 0.0,
        "show_type": show.get("id"),
        "caption_style": show.get("caption_style") or "hormozi",
    }


def direct_clip(clip, segments=None):
    rows = clip_segments(clip, segments)
    show = load_resolved()
    pace_hint = profile_for(show.get("pace") or "medium")
    prompt = DIRECTOR_PROMPT.format(
        rules=rules_text(),
        show_rules=show.get("rules") or "",
        min_keep=int(TRIM["min_seconds"]),
        max_trim_pct=int(TRIM["max_fraction"] * 100),
        punch_lo=pace_hint["punch_ins"][0],
        punch_hi=pace_hint["punch_ins"][1],
        zoom_lo=pace_hint["zoom"][0],
        zoom_hi=pace_hint["zoom"][1],
        dur_lo=pace_hint["punch_duration"][0],
        dur_hi=pace_hint["punch_duration"][1],
        spacing=PUNCH_MIN_SPACING,
        emph_max=CAPTION["emphasize_max"],
        start=clip.get("start"),
        end=clip.get("end"),
        hook=clip.get("hook") or "",
        angle=clip.get("content_angle") or "",
        why=clip.get("highlight_reason") or "",
        words=clip.get("word_score"),
        visual=clip.get("visual_score"),
        audio=clip.get("audio_energy"),
        timed=timed_transcript(rows),
    )
    try:
        response = generate_content(prompt)
        log_gemini_call("edit_director", response)
        parsed = _parse(response.text)
        if parsed:
            return _clamp_plan(parsed, clip, rows, segments)
    except Exception as exc:
        print(f"   director fallback ({exc})")
    return _clamp_plan(fallback_plan(clip, rows), clip, rows, segments)


def main():
    clips_file = PROJECT_ROOT / "output" / "clips.json"
    if not clips_file.exists():
        raise FileNotFoundError("clips.json missing — rank clips before directing edits.")
    with open(clips_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    clips = data.get("clips") or []

    transcript_file = PROJECT_ROOT / "output" / "transcript.json"
    video = None
    state_file = PROJECT_ROOT / "memory" / "state.json"
    if state_file.exists():
        try:
            video = (json.loads(state_file.read_text(encoding="utf-8")) or {}).get("video_path")
        except (OSError, ValueError):
            video = None
    if video:
        video = Path(video)
        if not video.is_absolute():
            video = PROJECT_ROOT / video
        if video.exists() and clips:
            from scripts.pipeline.transcribe_backend import fill_words_for_clips
            print("   word timings for ranked cuts only...")
            fill_words_for_clips(video, clips, transcript_file)

    segments = []
    if transcript_file.exists():
        with open(transcript_file, "r", encoding="utf-8") as f:
            segments = (json.load(f) or {}).get("segments") or []
    has_words = any(seg.get("words") for seg in segments)

    plans = [None] * len(clips)
    print(f"Edit director: planning {len(clips)} cuts...")
    print(f"   rule book: {'loaded' if rules_text() else 'missing'} · "
          f"word timings: {'yes' if has_words else 'segment-level only'}")
    workers = min(3, max(1, len(clips)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(direct_clip, clip, segments): i for i, clip in enumerate(clips)}
        for future in as_completed(future_map):
            i = future_map[future]
            plans[i] = future.result()
            plan = plans[i]
            trimmed = plan["trim"]["end"] - plan["trim"]["start"]
            print(
                f"   clip {i + 1} [{plan['pace']} {plan['goal']}] "
                f"{trimmed:.1f}s · {len(plan['punch_ins'])} zooms · {plan['reason']}"
            )
    payload = {
        "version": 2,
        "layer": "reasoning",
        "rule_book": "config/editing_rules.md",
        "word_timings": has_words,
        "clips": [
            {
                "index": i + 1,
                "chunk_id": clip.get("chunk_id"),
                "start": clip.get("start"),
                "end": clip.get("end"),
                **plan,
            }
            for i, (clip, plan) in enumerate(zip(clips, plans))
        ],
    }
    out = PROJECT_ROOT / "output" / "edit_plans.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"✅ Edit plans saved to {out}")


if __name__ == "__main__":
    main()
