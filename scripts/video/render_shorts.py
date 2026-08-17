"""
One FFmpeg pass per selected clip: seek + 9:16 crop + captions.

boxblur at 1080x1920 was the 30-minute bottleneck (5 clips ≈ 6 min each).
Center-crop to 9:16 is a single scale+crop and looks more like a Short.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))


def ffmpeg_subtitles_path(subtitle_file: Path) -> str:
    """Relative POSIX path from project root — Windows drive-letter escaping breaks libass."""
    resolved = subtitle_file.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix().replace(":", r"\:")


def render_clip(source: Path, start, end, subtitle_file: Path, output_file: Path):
    sub = ffmpeg_subtitles_path(subtitle_file)
    # 9:16 fill (no extra punch-in — source talks are often 360p).
    # Small ASS captions with outline sit in the lower third.
    vf = (
        "setpts=PTS-STARTPTS,"
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "unsharp=5:5:0.6:5:5:0.0,"
        "eq=contrast=1.04:saturation=1.05,"
        "setsar=1,"
        f"subtitles='{sub}'"
    )

    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-y",
        "-ss", str(start),
        "-to", str(end),
        "-i", str(source),
        "-map", "0:v:0",
        "-map", "0:a:0?",
        "-vf", vf,
        "-af", "asetpts=PTS-STARTPTS,aresample=async=1:first_pts=0,volume=6dB",
        "-preset", "ultrafast",
        "-crf", "28",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-ar", "44100",
        "-ac", "2",
        "-b:a", "192k",
        "-profile:a", "aac_low",
        "-shortest",
        "-threads", "0",
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
    total_t0 = time.time()
    for i, clip in enumerate(clips, start=1):
        ass = subtitle_dir / f"short_{i}.ass"
        srt = subtitle_dir / f"short_{i}.srt"
        subtitle = ass if ass.exists() else srt
        if not subtitle.exists():
            print(f"Subtitle missing for short_{i}, skipping")
            continue
        output_file = output_dir / f"short_{i}.mp4"
        dur = round(float(clip.get("end", 0)) - float(clip.get("start", 0)), 1)
        print(f"Rendering short_{i}.mp4  {clip['start']}s -> {clip['end']}s ({dur}s clip)")
        t0 = time.time()
        render_clip(source, clip["start"], clip["end"], subtitle, output_file)
        print(f"  saved in {time.time() - t0:.1f}s -> {output_file}")

    print(f"✅ Rendered {len(clips)} shorts in {time.time() - total_t0:.1f}s")


if __name__ == "__main__":
    main()
