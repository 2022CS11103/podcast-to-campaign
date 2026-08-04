import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))


def seconds_to_srt(seconds):
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)

    return f"{hrs:02}:{mins:02}:{secs:02},{millis:03}"


def create_srt(segments, clip_start, clip_end, output_file):

    index = 1

    with open(output_file, "w", encoding="utf-8") as f:

        for segment in segments:

            if segment["end"] < clip_start:
                continue

            if segment["start"] > clip_end:
                break

            start = max(segment["start"], clip_start)
            end = min(segment["end"], clip_end)

            start -= clip_start
            end -= clip_start

            f.write(f"{index}\n")
            f.write(
                f"{seconds_to_srt(start)} --> {seconds_to_srt(end)}\n"
            )
            f.write(segment["text"] + "\n\n")

            index += 1


def main():

    transcript_file = PROJECT_ROOT / "output" / "transcript.json"
    clips_file = PROJECT_ROOT / "output" / "clips.json"

    with open(transcript_file, "r", encoding="utf-8") as f:
        transcript = json.load(f)

    with open(clips_file, "r", encoding="utf-8") as f:
        clips = json.load(f)

    subtitle_dir = PROJECT_ROOT / "output" / "subtitles"
    subtitle_dir.mkdir(exist_ok=True)

    for i, clip in enumerate(clips["clips"], start=1):

        output_file = subtitle_dir / f"short_{i}.srt"

        create_srt(
            transcript["segments"],
            clip["start"],
            clip["end"],
            output_file
        )

        print(f"Created {output_file}")


if __name__ == "__main__":
    main()