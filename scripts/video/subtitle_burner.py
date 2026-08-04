import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def burn_subtitles(video_file: Path, subtitle_file: Path, output_file: Path):
    """
    Burn subtitles into a video using FFmpeg.
    """
    subtitle_path = subtitle_file.as_posix().replace(":", "\\:")

    command = [
        "ffmpeg",
        "-y",
        "-i", str(video_file),

        "-vf",
        f"subtitles='{subtitle_path}':force_style="
        "'FontName=Arial,"
        "FontSize=18,"
        "PrimaryColour=&HFFFFFF&,"
        "OutlineColour=&H000000&,"
        "BorderStyle=1,"
        "Outline=2,"
        "Shadow=1,"
        "Alignment=2,"
        "MarginV=60'",

        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",

        "-c:a", "copy",

        str(output_file)
    ]

    subprocess.run(command, check=True)


def main():

    vertical_dir = PROJECT_ROOT / "output" / "vertical_shorts"

    subtitle_dir = PROJECT_ROOT / "output" / "subtitles"

    output_dir = PROJECT_ROOT / "output" / "final_shorts"

    output_dir.mkdir(exist_ok=True)

    videos = sorted(vertical_dir.glob("*.mp4"))

    if not videos:
        print("No vertical shorts found.")
        return

    for video in videos:

        subtitle_file = subtitle_dir / f"{video.stem}.srt"

        if not subtitle_file.exists():
            print(f"Subtitle missing for {video.name}")
            continue

        output_file = output_dir / video.name

        print(f"Burning subtitles into {video.name}")

        burn_subtitles(
            video,
            subtitle_file,
            output_file
        )

        print(f"Saved -> {output_file}")

    print("\n✅ Subtitle burning completed.")


if __name__ == "__main__":
    main()