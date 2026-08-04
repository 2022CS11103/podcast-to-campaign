import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from utils.gemini_clients import get_client
from utils.cost_tracker import log_gemini_call

PROMPT = """
You are an expert content strategist, YouTube growth expert, and podcast editor.

Your job is to identify whether a transcript chunk is worth turning into a YouTube Short.

Analyze the transcript carefully.

Score the following (0-10):

1. Hook Strength
2. Educational Value
3. Emotional Impact
4. Curiosity
5. Shareability

Also return:

- summary
- hook
- reason
- best_platform
- overall_score (0-100)

Return ONLY valid JSON.

Example:

{
    "summary":"...",
    "hook":"...",
    "scores":{
        "hook":9,
        "education":8,
        "emotion":7,
        "curiosity":9,
        "shareability":8
    },
    "overall_score":88,
    "best_platform":"YouTube Shorts",
    "reason":"Strong hook with educational value."
}

Transcript:
"""


def analyze_chunk(text):
    client = get_client()
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=PROMPT + text
    )

    log_gemini_call("highlight_analysis", response)   # <-- naya

    return response.text


def main():

    input_file = PROJECT_ROOT / "output" / "chunks.json"

    if not input_file.exists():
        raise FileNotFoundError(f"Chunks file not found: {input_file}")

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = []

    for chunk in data["chunks"]:

        print(f"Analyzing Chunk {chunk['chunk_id']}...")

        raw = analyze_chunk(chunk["text"])

        try:
            # Gemini sometimes returns ```json ... ```
            cleaned = (
                raw.replace("```json", "")
                   .replace("```", "")
                   .strip()
            )

            analysis = json.loads(cleaned)

        except Exception:

            analysis = {
                "summary": "",
                "hook": "",
                "scores": {},
                "overall_score": 0,
                "best_platform": "",
                "reason": "",
                "raw_response": raw
            }

        analysis["start"] = chunk["start"]
        analysis["end"] = chunk["end"]
        analysis["chunk_id"] = chunk["chunk_id"]
        analysis["word_count"] = chunk["word_count"]

        results.append(analysis)

    output = {
        "results": results
    }

    output_file = PROJECT_ROOT / "output" / "analysis.json"

    output_file.parent.mkdir(exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False
        )

    print(f"\n✅ Analysis saved to {output_file}")


if __name__ == "__main__":
    main()