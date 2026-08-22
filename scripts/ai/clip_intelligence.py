import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from utils.gemini_clients import generate_content
from utils.cost_tracker import log_gemini_call
from config.platform_specs import platforms_for_duration, VIDEO_ANALYSIS_ENABLED
from scripts.pipeline.visual_energy import fuse_editor_score, highlight_reason
from config.show_style import load_resolved

PROMPT = """
You are an expert short-form editor for {show_label}.

{show_rules}

The window is already cut on sentence boundaries. Judge the OPENING (first 1-3 seconds / first sentence) especially hard — that is the hook.

Score the following (0-10):

1. Hook Strength (does the first sentence stop a scroll?)
2. Educational Value
3. Emotional Impact
4. Curiosity
5. Shareability
6. Completeness (does the idea resolve, or is it a mid-thought?)

Also return:

- summary (1 sentence)
- hook (max 12 words, as it would appear on screen)
- reason
- best_platform (one of: YouTube Shorts, Instagram Reels, TikTok, LinkedIn, Twitter)
- overall_score (0-100)
- starts_mid_thought (true/false)
- payoff_arrives (true/false) — viewer gets a complete takeaway before the clip ends

Return ONLY valid JSON with keys: summary, hook, scores (hook/education/emotion/curiosity/shareability/completeness), overall_score, best_platform, reason, starts_mid_thought, payoff_arrives.
"""


def analyze_chunk(text, duration, platforms):
    show = load_resolved()
    prompt = (
        PROMPT.format(show_label=show.get("label") or "podcasts", show_rules=show.get("rules") or "")
        + f"\nClip duration (seconds): {duration}\n"
        + f"Suggested platforms for this length: {', '.join(platforms) or 'any'}\n\n"
        + "Transcript:\n"
        + text
    )
    response = generate_content(prompt)
    log_gemini_call("highlight_analysis", response)
    return response.text


def parse_analysis(raw):
    cleaned = (
        raw.replace("```json", "")
           .replace("```", "")
           .strip()
    )
    try:
        return json.loads(cleaned)
    except Exception:
        return {
            "summary": "",
            "hook": "",
            "scores": {},
            "overall_score": 0,
            "best_platform": "",
            "reason": "",
            "starts_mid_thought": False,
            "payoff_arrives": False,
            "raw_response": raw,
        }


def score_chunk(chunk):
    duration = chunk.get("duration_seconds")
    if duration is None:
        duration = round(float(chunk.get("end", 0)) - float(chunk.get("start", 0)), 2)

    platforms = chunk.get("fits_platforms") or platforms_for_duration(duration)
    raw = analyze_chunk(chunk["text"], duration, platforms)
    analysis = parse_analysis(raw)

    if analysis.get("starts_mid_thought"):
        analysis["overall_score"] = max(10, int(analysis.get("overall_score", 0)) - 28)
    if analysis.get("payoff_arrives") is False:
        analysis["overall_score"] = max(10, int(analysis.get("overall_score", 0)) - 16)

    analysis["start"] = chunk["start"]
    analysis["end"] = chunk["end"]
    analysis["chunk_id"] = chunk["chunk_id"]
    analysis["word_count"] = chunk["word_count"]
    analysis["duration_seconds"] = duration
    analysis["target_duration"] = chunk.get("target_duration")
    analysis["fits_platforms"] = platforms
    analysis["text"] = chunk["text"]
    analysis["visual_score"] = chunk["visual_score"] if "visual_score" in chunk else None
    analysis["audio_energy"] = chunk["audio_energy"] if "audio_energy" in chunk else None
    analysis["visual_signals"] = chunk.get("visual_signals") or {}
    analysis["word_score"] = analysis.get("overall_score")
    analysis["overall_score"] = fuse_editor_score(
        analysis.get("word_score"),
        analysis.get("audio_energy"),
        analysis.get("visual_score"),
        enabled=VIDEO_ANALYSIS_ENABLED,
    )
    analysis["highlight_reason"] = highlight_reason(
        analysis.get("word_score"),
        analysis.get("audio_energy"),
        analysis.get("visual_score"),
        analysis.get("visual_signals"),
    )
    return analysis


def main():

    input_file = PROJECT_ROOT / "output" / "chunks.json"

    if not input_file.exists():
        raise FileNotFoundError(f"Chunks file not found: {input_file}")

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    chunks = data["chunks"]
    print(f"Analyzing {len(chunks)} windows in parallel...")

    results = [None] * len(chunks)
    with ThreadPoolExecutor(max_workers=3) as pool:
        future_map = {pool.submit(score_chunk, chunk): i for i, chunk in enumerate(chunks)}
        for future in as_completed(future_map):
            i = future_map[future]
            results[i] = future.result()
            print(f"  scored chunk {chunks[i]['chunk_id']}")

    output = {
        "results": results
    }

    output_file = PROJECT_ROOT / "output" / "analysis.json"
    output_file.parent.mkdir(exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Analysis saved to {output_file}")


if __name__ == "__main__":
    main()
