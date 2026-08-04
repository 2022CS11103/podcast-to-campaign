import json
import sys
from pathlib import Path

CHUNK_SIZE = 80  # Approximate words per chunk


def create_chunks(segments, chunk_size=300):
    chunks = []

    current_text = []
    current_words = 0
    current_start = None
    current_end = None

    chunk_id = 1

    for segment in segments:

        words = segment["text"].split()

        if current_start is None:
            current_start = segment["start"]

        current_text.append(segment["text"])
        current_words += len(words)
        current_end = segment["end"]

        if current_words >= chunk_size:

            chunks.append({
                "chunk_id": chunk_id,
                "start": current_start,
                "end": current_end,
                "word_count": current_words,
                "text": " ".join(current_text)
            })

            chunk_id += 1

            current_text = []
            current_words = 0
            current_start = None
            current_end = None

    # Remaining text
    if current_text:

        chunks.append({
            "chunk_id": chunk_id,
            "start": current_start,
            "end": current_end,
            "word_count": current_words,
            "text": " ".join(current_text)
        })

    return chunks


def main():

    if len(sys.argv) < 2:
        print("Usage:")
        print("python scripts/chunk_transcript.py output/clean_transcript.json")
        return

    input_file = Path(sys.argv[1])

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    chunks = create_chunks(
        data["segments"],
        CHUNK_SIZE
    )

    output = {
        **data,
        "chunk_count": len(chunks),
        "chunks": chunks
    }

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / "chunks.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False
        )

    print(f"✅ Created {len(chunks)} chunks")
    print(f"✅ Saved to {output_file}")


if __name__ == "__main__":
    main()