# CreatorOS editing rules

The rule book the edit director follows when it turns a raw talk into a short.
It is injected into the director prompt and mirrored as numbers in
`config/editing_style.py`, so the renderer and the quality check enforce the
same limits the director planned against.

## 1. Editorial intent

Every cut answers one question: why should someone stop scrolling here?

- Choose one `goal` per clip: `funny`, `emotional`, `educational`, `hype`, or `story`.
- Choose the `pace` that serves the goal, never the other way round.
  - `funny` and `hype` are `fast`.
  - `educational` is `medium`.
  - `emotional` and `story` are `medium` or `hold`.
- `reason` states the intent in one sentence an editor would say out loud.

## 2. Cold open, no runway

- The clip opens on the strongest line, not on setup, not on a greeting.
- Trim any lead-in silence or half sentence before that line.
- The first spoken word lands within 0.6s of frame one.
- `hook_line` is the exact sentence that must open the cut.

## 3. Dead air and jump cuts

- Remove every silence longer than the pace threshold, keeping a short breath
  so speech never sounds clipped.
  - `fast`: cut silences over 0.22s
  - `medium`: cut silences over 0.40s
  - `hold`: cut silences over 0.85s
- Never cut inside a word. Jump cuts only between sentences, never mid-clause.
- A pause inside a sentence is a breath, not a cut.
- Keep the cut rhythm inside the pace band. Too few cuts feels like a raw
  export; too many feels like a glitch.
  - `fast`: 14–34 cuts per minute
  - `medium`: 7–20 cuts per minute
  - `hold`: 2–10 cuts per minute
- A shot shorter than 0.35s is a flicker. Merge it into its neighbour.

## 4. Punch-in zooms

Zooms mark meaning. They are not decoration and they are not constant motion.

- 1–3 punch-ins per clip. `hold` pace takes at most 2.
- The first punch-in lands on the opening hook.
- The last punch-in lands on the payoff, the line the clip exists for.
- Zoom range by pace: `fast` 1.14–1.28, `medium` 1.12–1.24, `hold` 1.10–1.18.
- Duration 0.5–1.0s. Consecutive punch-ins stay at least 1.5s apart.
- No punch-in in the first 0.3s or across the final 0.4s of the clip.

## 5. Captions

- Read-in-one-glance cues: at most 4 words, at most 2 lines.
- A cue holds 0.45–2.1s. Cues never overlap.
- Word-level timings drive cue timing when the transcript has them; otherwise
  spread words evenly across the sentence.
- `emphasize` carries 1–4 punchy words from the hook or payoff. Those words pop.
- Filler words alone never earn a cue: the, a, and, uh, um, like, so, just.
- Captions live in the lower safe area, clear of platform UI.
- The hook title holds for the first 1.45s only, then gets out of the way.

## 6. Retention shape

- The payoff arrives before 70% of the clip has played.
- The clip ends on a complete thought. Never mid sentence, never on a filler word.
- The clip opens on a complete sentence, not a continuation like "and then" or "but".
- Cut trailing silence: no more than 0.35s of tail after the last word, unless
  this is a comedy/panel show — then hold 1.5–2s of audience laughter.
- `retention_risk` names the one reason a viewer would drop off, in a sentence.

## 6b. Show type

Comedy / panel (India's Got Latent, roast, live audience):
- Rank laughter and clapping after a punchline as the viral signal.
- Never jump-cut through a laugh. The reaction is the payoff.
- Open on the setup, land the joke, hold the room.

Insight interview (Raj Shamani, business podcast):
- Rank bold claims, numbers, mistakes, and secrets — not crowd noise.
- If the strongest sentence is later in the window, play it first, then rewind
  into the context.
- Fix Hinglish and Indian numbering in captions (lakhs, crores, dhanda).

## 7. Duration by platform

Duration comes from `config/platform_specs.py` and is not negotiable.

| Platform | min | ideal | max |
|---|---|---|---|
| YouTube Shorts | 30s | 45s | 60s |
| Instagram Reels | 15s | 30s | 45s |
| TikTok | 12s | 25s | 45s |

Tighten a window by at most 20% to honour rules 2 and 6, and never below 12s.

## 8. Picture and sound

- Vertical 1080x1920, subject framed in the middle third.
- Dialogue is loud, level, and never clipped.
- Grade is a light lift in contrast and saturation, not a filter.

## 9. Quality gate

A render ships only if it passes `config/editing_style.py QUALITY_RUBRIC`:
correct resolution, duration inside the platform range, an audio track present,
enough caption cues for the length, more than one shot when the plan asked for
jump cuts, and no long silent lead-in. A failed render is re-cut with a safer
plan rather than shipped.
