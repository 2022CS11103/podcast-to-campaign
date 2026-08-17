import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))


def extract_metadata(video_path):

    command = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(video_path)
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    return json.loads(result.stdout)


def main():

    if len(sys.argv) < 2:
        print("Usage: python video_processor.py video.mp4")
        return

    video_path = Path(sys.argv[1])

    if not video_path.exists():
        print("Video not found.")
        return

    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(exist_ok=True)

    metadata = extract_metadata(video_path)

    metadata_file = output_dir / "metadata.json"

    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    print("Metadata saved:", metadata_file)
    print("Skipping full-talk audio extract — scan cuts 8-min windows from the video.")


if __name__ == "__main__":
    main()