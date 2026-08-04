import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))


def convert_to_vertical(input_video: Path, output_video: Path):
    """
    Convert a landscape video to a 9:16 vertical video
    using a blurred background + centered original video.
    """

    filter_complex = (
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        "boxblur=20:10,crop=1080:1920[bg];"
        "[0:v]scale=1080:-2:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2"
    )

    command = [
        "ffmpeg",
        "-y",
        "-i", str(input_video),
        "-filter_complex", filter_complex,
        "-c:v", "libx264",
        "-c:a", "copy",
        "-preset", "fast",
        "-crf", "23",
        str(output_video)
    ]

    subprocess.run(command, check=True)


def main():

    shorts_dir = PROJECT_ROOT / "output" / "shorts"

    vertical_dir = PROJECT_ROOT / "output" / "vertical_shorts"
    vertical_dir.mkdir(exist_ok=True)

    videos = list(shorts_dir.glob("*.mp4"))

    if not videos:
        print("No shorts found.")
        return

    for video in videos:

        output_video = vertical_dir / video.name

        print(f"Formatting {video.name}...")

        convert_to_vertical(
            video,
            output_video
        )

        print(f"Saved -> {output_video}")

    print("\nAll shorts converted successfully.")


if __name__ == "__main__":
    main()