"""
Reasoning layer: turn understanding (transcript, scores, visual energy)
into a sequence of editing operations — Mosaic-style, not "trim and ship".
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

from utils.gemini_clients import generate_content
from utils.cost_tracker import log_gemini_call

DIRECTOR_PROMPT = """You are a short-form video editor (TikTok/Reels/Shorts), not a clip exporter.

Creative goal: make this moment feel edited by a human — punchy, not a raw extract.

Return ONLY JSON:
{{
  "goal": "funny|emotional|educational|hype|story",
  "pace": "fast|medium|hold",
  "reason": "one sentence of editorial intent",
  "drop_silences": true,
  "punch_ins": [
    {{"at_src": 12.4, "duration": 0.7, "zoom": 1.18, "why": "hook"}}
  ],
  "caption_mode": "keyword_pop",
  "emphasize": ["word1", "word2"]
}}

Rules:
- at_src is seconds on the SOURCE timeline (between clip_start and clip_end).
- 1 to 3 punch_ins. First should hit the opening hook. Last should hit the payoff.
- zoom between 1.12 and 1.28. duration 0.55 to 0.95 seconds.
- funny/hype → pace fast, drop_silences true.
- emotional/story → pace medium, fewer zooms.
- emphasize 1-4 punchy words from the hook, not whole sentences.
- Do not invent times outside clip_start..clip_end.

clip_start: {start}
clip_end: {end}
hook: {hook}
angle: {angle}
highlight_reason: {why}
word_score: {words} visual: {visual} audio: {audio}
transcript:
{text}
"""


def _hook_words(hook):
    words = re.findall(r"[A-Za-z']+", hook or "")
    skip = {"the", "a", "an", "to", "of", "and", "i", "i'm", "im", "just", "this", "that", "is"}
    kept = [w for w in words if w.lower() not in skip]
    return kept[:4] or words[:3]


def fallback_plan(clip):
    start = float(clip["start"])
    end = float(clip["end"])
    dur = max(1.0, end - start)
    reason = (clip.get("highlight_reason") or "").lower()
    angle = (clip.get("content_angle") or "").lower()
    funny = any(k in reason + " " + angle for k in ("loud", "funny", "emotion", "hype", "share"))
    pace = "fast" if funny else "medium"
    hook = clip.get("hook") or ""
    punchline_at = min(end - 0.8, start + dur * (0.62 if pace == "fast" else 0.72))
    return {
        "goal": "funny" if funny else "hook",
        "pace": pace,
        "reason": (
            "Fast cuts and a payoff zoom - treat this like a Short, not a raw take."
            if pace == "fast"
            else "Hold the thought, punch in on the hook and the close."
        ),
        "drop_silences": pace == "fast",
        "punch_ins": [
            {"at_src": round(start + 0.35, 2), "duration": 0.8, "zoom": 1.16, "why": "open hook"},
            {"at_src": round(punchline_at, 2), "duration": 0.85, "zoom": 1.22, "why": "payoff"},
        ],
        "caption_mode": "keyword_pop",
        "emphasize": _hook_words(hook),
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


def _clamp_plan(plan, clip):
    start = float(clip["start"])
    end = float(clip["end"])
    punches = []
    for item in (plan.get("punch_ins") or [])[:3]:
        try:
            at = float(item.get("at_src"))
            dur = float(item.get("duration") or 0.7)
            zoom = float(item.get("zoom") or 1.18)
        except (TypeError, ValueError):
            continue
        at = min(max(at, start), end - 0.4)
        punches.append({
            "at_src": round(at, 2),
            "duration": round(min(1.1, max(0.5, dur)), 2),
            "zoom": round(min(1.28, max(1.10, zoom)), 2),
            "why": item.get("why") or "beat",
        })
    if not punches:
        punches = fallback_plan(clip)["punch_ins"]
    emphasize = plan.get("emphasize") or _hook_words(clip.get("hook") or "")
    if isinstance(emphasize, str):
        emphasize = [emphasize]
    pace = plan.get("pace") if plan.get("pace") in ("fast", "medium", "hold") else "medium"
    return {
        "goal": plan.get("goal") or "hook",
        "pace": pace,
        "reason": plan.get("reason") or fallback_plan(clip)["reason"],
        "drop_silences": bool(plan.get("drop_silences", pace == "fast")),
        "punch_ins": punches,
        "caption_mode": plan.get("caption_mode") or "keyword_pop",
        "emphasize": [str(w) for w in emphasize[:4]],
    }


def direct_clip(clip):
    prompt = DIRECTOR_PROMPT.format(
        start=clip.get("start"),
        end=clip.get("end"),
        hook=clip.get("hook") or "",
        angle=clip.get("content_angle") or "",
        why=clip.get("highlight_reason") or "",
        words=clip.get("word_score"),
        visual=clip.get("visual_score"),
        audio=clip.get("audio_energy"),
        text=(clip.get("text") or "")[:1200],
    )
    try:
        response = generate_content(prompt)
        log_gemini_call("edit_director", response)
        parsed = _parse(response.text)
        if parsed:
            return _clamp_plan(parsed, clip)
    except Exception as exc:
        print(f"   director fallback ({exc})")
    return fallback_plan(clip)


def main():
    clips_file = PROJECT_ROOT / "output" / "clips.json"
    if not clips_file.exists():
        raise FileNotFoundError("clips.json missing — rank clips before directing edits.")
    with open(clips_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    clips = data.get("clips") or []
    plans = [None] * len(clips)
    print(f"Edit director: planning {len(clips)} cuts...")
    workers = min(3, max(1, len(clips)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(direct_clip, clip): i for i, clip in enumerate(clips)}
        for future in as_completed(future_map):
            i = future_map[future]
            plans[i] = future.result()
            clip = clips[i]
            plan = plans[i]
            print(
                f"   clip {i + 1} [{plan['pace']} {plan['goal']}] "
                f"{plan['reason']}"
            )
    payload = {
        "version": 1,
        "layer": "reasoning",
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
