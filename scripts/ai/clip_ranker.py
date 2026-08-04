import json
import sys
from pathlib import Path

# ==========================
# Project Root
# ==========================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

TOP_K = 10


def remove_duplicates(results):
    """
    Remove duplicate clips based on summary similarity.
    Simple MVP implementation.
    """
    seen = set()
    unique = []

    for clip in results:
        summary = clip.get("summary", "").strip().lower()

        if summary not in seen:
            seen.add(summary)
            unique.append(clip)

    return unique


def main():

    input_file = PROJECT_ROOT / "output" / "analysis.json"

    if not input_file.exists():
        raise FileNotFoundError(f"Analysis file not found: {input_file}")

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    ranked = sorted(
        data["results"],
        key=lambda x: x.get("overall_score", 0),
        reverse=True
    )

    ranked = remove_duplicates(ranked)

    top_clips = ranked[:TOP_K]

    output = {
        "total_selected": len(top_clips),
        "clips": top_clips
    }

    output_file = PROJECT_ROOT / "output" / "clips.json"

    output_file.parent.mkdir(exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            output,
            f,
            indent=4,
            ensure_ascii=False
        )

    print("\n========== TOP CLIPS ==========")

    for clip in top_clips:

        print(
            f"""
Chunk: {clip['chunk_id']}
Score: {clip['overall_score']}
Time: {clip['start']}s -> {clip['end']}s
Hook: {clip['hook']}
"""
        )

    print(f"\n✅ Saved to {output_file}")


if __name__ == "__main__":
    main()