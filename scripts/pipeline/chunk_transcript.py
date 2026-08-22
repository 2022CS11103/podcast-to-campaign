"""
Turn a cleaned transcript into clip *candidates*, not arbitrary word buckets.

Approach:
1. Treat Whisper segments as sentences (they usually are).
2. Grow windows from each sentence start toward 20s / 35s / 50s targets.
3. Snap to sentence boundaries so clips don't start/end mid-thought.
4. Cheap heuristic pre-rank (questions, claims, frameworks) so we only
   send the top N windows to Gemini — that's the main API cost lever.
"""

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from config.platform_specs import (
    CANDIDATE_TARGET_SECONDS,
    CANDIDATE_MIN_SECONDS,
    CANDIDATE_MAX_SECONDS,
    MAX_ANALYZED_CANDIDATES,
    platforms_for_duration,
)
from utils.sentences import ends_sentence, looks_like_start
from utils.show_detect import keyword_hits, is_hook_line

# Patterns that usually open a clip-worthy moment in lectures/podcasts.
HOOK_PATTERNS = [
    re.compile(r"\b(here'?s|here is) (the|why|how|what|a)\b", re.I),
    re.compile(r"\bthe (biggest|real|only|actual) (mistake|secret|reason|problem|difference)\b", re.I),
    re.compile(r"\b(most people|nobody|everyone) (thinks?|gets?|does|gets this wrong)\b", re.I),
    re.compile(r"\b(if you|when you) (don'?t|aren'?t|can'?t|never|always)\b", re.I),
    re.compile(r"\b(the )?(truth|secret|key|trick|framework) is\b", re.I),
    re.compile(r"\b(three|3|five|5|four|4) (ways|things|steps|reasons|rules|mistakes)\b", re.I),
    re.compile(r"\b(let me show you|i want you to|write this down|this is important)\b", re.I),
    re.compile(r"\b(stop|never|always|don'?t) (doing|using|buying|thinking)\b", re.I),
]

FILLER_OPENERS = re.compile(
    r"^(um+|uh+|so yeah|you know|like,? |anyway|alright so|okay so)\b",
    re.I,
)


def heuristic_score(text: str) -> float:
    score = 0.0
    if "?" in text:
        score += 2.5
    for pat in HOOK_PATTERNS:
        if pat.search(text):
            score += 3.0
            break
    # Short punchy first sentence is a better hook than a long preamble.
    first = re.split(r"[.!?]", text, maxsplit=1)[0]
    if 8 <= len(first.split()) <= 18:
        score += 1.5
    if FILLER_OPENERS.search(text.strip()):
        score -= 2.0
    # Density: prefer a complete thought, not a ramble.
    words = len(text.split())
    if 40 <= words <= 140:
        score += 1.0
    score += min(4.0, keyword_hits(text) * 1.2)
    if is_hook_line(text.split(".")[0] if "." in text else text[:120]):
        score += 2.0
    return score


def build_candidates(segments):
    n = len(segments)
    raw = []

    for i in range(n):
        prev_text = segments[i - 1].get("text") or "" if i else ""
        opener = (segments[i].get("text") or "").strip()
        pause = 0.0
        if i:
            try:
                pause = float(segments[i]["start"]) - float(segments[i - 1]["end"])
            except (TypeError, ValueError, KeyError):
                pause = 0.0
        if not looks_like_start(opener, prev_text, pause):
            continue
        if FILLER_OPENERS.search(opener):
            continue

        start = segments[i]["start"]
        parts = []
        hit_targets = set()

        for j in range(i, n):
            parts.append(segments[j]["text"])
            end = segments[j]["end"]
            duration = round(end - start, 2)
            if duration < CANDIDATE_MIN_SECONDS:
                continue
            nxt = segments[j + 1] if j + 1 < n else None
            closed = ends_sentence(segments[j].get("text") or "")
            if not closed and nxt is not None:
                gap = float(nxt.get("start") or end) - float(end)
                closed = gap >= 0.55
            if not closed:
                if nxt is None:
                    closed = duration >= CANDIDATE_MIN_SECONDS
                else:
                    continue

            text = " ".join(parts).strip()
            word_count = len(text.split())

            for target in CANDIDATE_TARGET_SECONDS:
                if target in hit_targets:
                    continue
                # Snap: emit once we reach / pass the target on a sentence end.
                if duration >= target - 3:
                    hit_targets.add(target)
                    if duration > CANDIDATE_MAX_SECONDS:
                        continue
                    raw.append({
                        "start": start,
                        "end": end,
                        "duration_seconds": duration,
                        "target_duration": target,
                        "word_count": word_count,
                        "text": text,
                        "heuristic_score": round(heuristic_score(text), 2),
                        "fits_platforms": platforms_for_duration(duration),
                    })

            if duration > CANDIDATE_MAX_SECONDS:
                break

    return raw


def nms_windows(candidates, iou_threshold=0.55):
    """
    Drop heavily overlapping windows, keeping the higher heuristic score.
    Same idea as non-max suppression in object detection.
    """
    ordered = sorted(
        candidates,
        key=lambda c: (c["heuristic_score"], -c["duration_seconds"]),
        reverse=True,
    )
    kept = []

    def overlap(a, b):
        inter = max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
        union = max(a["end"], b["end"]) - min(a["start"], b["start"])
        return inter / union if union else 0.0

    for cand in ordered:
        if any(overlap(cand, k) > iou_threshold for k in kept):
            continue
        kept.append(cand)
    return kept


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("python scripts/pipeline/chunk_transcript.py output/clean_transcript.json")
        return

    input_file = Path(sys.argv[1])
    if not input_file.is_absolute():
        input_file = PROJECT_ROOT / input_file

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments = [s for s in data.get("segments", []) if s.get("text")]
    raw = build_candidates(segments)
    suppressed = nms_windows(raw)

    # Always keep a mix of short / medium / long so platforms have options.
    by_target = {t: [] for t in CANDIDATE_TARGET_SECONDS}
    leftover = []
    for c in suppressed:
        bucket = by_target.get(c["target_duration"])
        if bucket is not None:
            bucket.append(c)
        else:
            leftover.append(c)

    selected = []
    slots = max(1, MAX_ANALYZED_CANDIDATES // max(len(CANDIDATE_TARGET_SECONDS), 1))
    for target in CANDIDATE_TARGET_SECONDS:
        selected.extend(by_target[target][:slots])
    selected.extend(leftover)

    selected = sorted(selected, key=lambda c: c["heuristic_score"], reverse=True)
    selected = selected[:MAX_ANALYZED_CANDIDATES]
    selected.sort(key=lambda c: c["start"])

    chunks = []
    for idx, cand in enumerate(selected, start=1):
        chunks.append({
            "chunk_id": idx,
            **cand,
        })

    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(exist_ok=True)

    candidates_file = output_dir / "candidates.json"
    with open(candidates_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "raw_candidate_count": len(raw),
                "after_nms": len(suppressed),
                "analyzed_count": len(chunks),
                "candidates": chunks,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    output = {
        **{k: v for k, v in data.items() if k != "chunks"},
        "chunk_count": len(chunks),
        "chunks": chunks,
    }

    output_file = output_dir / "chunks.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"✅ {len(raw)} raw windows → {len(suppressed)} after NMS → {len(chunks)} sent to AI")
    print(f"✅ Saved {output_file}")
    print(f"✅ Debug dump {candidates_file}")


if __name__ == "__main__":
    main()
