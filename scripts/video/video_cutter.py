import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))


def cut_video(input_video, start, end, output_file):
    """
    Cut a video clip using FFmpeg.
    """

    command = [
        "ffmpeg",
        "-y",
        "-ss", str(start),
        "-to", str(end),
        "-i", str(input_video),

        # Re-encode for compatibility
        "-c:v", "libx264",
        "-c:a", "aac",

        "-preset", "fast",
        "-crf", "23",

        str(output_file)
    ]

    subprocess.run(command, check=True)


def main():

    if len(sys.argv) < 2:
        print("Usage:")
        print("python scripts/video_cutter.py input/video.mp4")
        return

    input_video = Path(sys.argv[1])

    if not input_video.exists():
        print("Video not found.")
        return

    clips_file = PROJECT_ROOT / "output" / "clips.json"

    with open(clips_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    shorts_dir = PROJECT_ROOT / "output" / "shorts"
    shorts_dir.mkdir(exist_ok=True)

    for i, clip in enumerate(data["clips"], start=1):

        output_file = shorts_dir / f"short_{i}.mp4"

        print(f"\nCreating Short {i}")

        print(
            f"Time: {clip['start']}s → {clip['end']}s"
        )

        cut_video(
            input_video,
            clip["start"],
            clip["end"],
            output_file
        )

        print(f"Saved: {output_file}")

    print("\n🎉 All Shorts Created!")


if __name__ == "__main__":
    main()