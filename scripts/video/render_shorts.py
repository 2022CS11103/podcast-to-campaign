"""
One FFmpeg pass per selected clip: seek + 9:16 + burn captions.

Old path re-encoded each clip three times (cut, vertical, subtitles)
and ran YOLO on every frame even though the crop never used tracking.
That was most of the 45 minutes on a 4-minute video.
"""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))


def ffmpeg_subtitles_path(subtitle_file: Path) -> str:
    return subtitle_file.resolve().as_posix().replace(":", r"\:")


def render_clip(source: Path, start, end, subtitle_file: Path, output_file: Path):
    sub = ffmpeg_subtitles_path(subtitle_file)
    filter_complex = (
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        "boxblur=20:10,crop=1080:1920[bg];"
        "[0:v]scale=1080:-2:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        f"subtitles='{sub}':force_style="
        "'FontName=Arial,FontSize=18,PrimaryColour=&HFFFFFF&,"
        "OutlineColour=&H000000&,BorderStyle=1,Outline=2,Shadow=1,"
        "Alignment=2,MarginV=60'"
    )

    # -ss before -i seeks in the container (fast). Output starts at 0s
    # so clip-relative SRT files line up.
    command = [
        "ffmpeg",
        "-y",
        "-ss", str(start),
        "-to", str(end),
        "-i", str(source),
        "-filter_complex", filter_complex,
        "-preset", "veryfast",
        "-crf", "26",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-ac", "2",
        "-movflags", "+faststart",
        str(output_file),
    ]
    subprocess.run(command, check=True)


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/video/render_shorts.py <source.mp4>")
        return

    source = Path(sys.argv[1])
    if not source.exists():
        raise FileNotFoundError(f"Video not found: {source}")

    clips_file = PROJECT_ROOT / "output" / "clips.json"
    with open(clips_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    subtitle_dir = PROJECT_ROOT / "output" / "subtitles"
    output_dir = PROJECT_ROOT / "output" / "final_shorts"
    output_dir.mkdir(parents=True, exist_ok=True)

    clips = data.get("clips") or []
    for i, clip in enumerate(clips, start=1):
        srt = subtitle_dir / f"short_{i}.srt"
        if not srt.exists():
            print(f"Subtitle missing for short_{i}, skipping")
            continue
        output_file = output_dir / f"short_{i}.mp4"
        print(f"Rendering short_{i}.mp4  {clip['start']}s → {clip['end']}s")
        render_clip(source, clip["start"], clip["end"], srt, output_file)
        print(f"Saved {output_file}")

    print(f"✅ Rendered {len(clips)} shorts in one encode each")


if __name__ == "__main__":
    main()
