import json
import re
import sys
from pathlib import Path


def clean_text(text: str) -> str:
    """
    Clean transcript text while preserving meaning.
    """

    # Remove text inside square brackets
    text = re.sub(r"\[.*?\]", "", text)

    # Remove musical notes
    text = text.replace("♪", "")

    # Replace newlines
    text = text.replace("\n", " ")

    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def main():

    if len(sys.argv) < 2:
        print("Usage:")
        print("python scripts/clean_transcript.py output/transcript.json")
        return

    input_file = Path(sys.argv[1])

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    cleaned_segments = []

    for segment in data["segments"]:

        cleaned_segments.append({
            "start": segment["start"],
            "end": segment["end"],
            "text": clean_text(segment["text"])
        })

    full_text = " ".join(
        segment["text"] for segment in cleaned_segments
    )

    output = {
        **data,
        "transcript": full_text,
        "segments": cleaned_segments
    }

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / "clean_transcript.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(f"✅ Clean transcript saved to {output_file}")


if __name__ == "__main__":
    main()