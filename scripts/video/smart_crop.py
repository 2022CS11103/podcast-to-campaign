import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920


def moving_average(values, window=15):
    """
    Smooth camera movement.
    """
    if not values:
        return values

    smoothed = []

    for i in range(len(values)):
        start = max(0, i - window)
        end = min(len(values), i + window)

        avg = sum(values[start:end]) / (end - start)

        smoothed.append(avg)

    return smoothed


def build_camera_path(tracking, video_width):

    centers = []

    for frame in tracking:
        centers.append(frame["center"]["x"])

    centers = moving_average(centers)

    camera_path = []

    for x in centers:

        crop_x = x - TARGET_WIDTH / 2

        crop_x = max(0, crop_x)

        crop_x = min(
            crop_x,
            max(0, video_width - TARGET_WIDTH)
        )

        camera_path.append(round(crop_x, 2))

    return camera_path


def render_vertical(input_video, output_video):

    """
    MVP version.

    We still use FFmpeg blur background.

    In V2 we will use OpenCV with dynamic crop.
    """

    filter_complex = (
        "[0:v]"
        "scale=1080:1920:"
        "force_original_aspect_ratio=increase,"
        "boxblur=20:10,"
        "crop=1080:1920[bg];"

        "[0:v]"
        "scale=1080:-2:"
        "force_original_aspect_ratio=decrease[fg];"

        "[bg][fg]"
        "overlay=(W-w)/2:(H-h)/2"
    )

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_video),
        "-filter_complex",
        filter_complex,
        "-preset",
        "fast",
        "-crf",
        "22",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        str(output_video)
    ]

    subprocess.run(command, check=True)


def main():

    shorts_dir = PROJECT_ROOT / "output" / "shorts"

    tracking_dir = PROJECT_ROOT / "output" / "tracking"

    output_dir = PROJECT_ROOT / "output" / "vertical_shorts"

    output_dir.mkdir(exist_ok=True)

    videos = sorted(shorts_dir.glob("*.mp4"))

    if not videos:
        print("No shorts found.")
        return

    for video in videos:

        tracking_file = tracking_dir / f"{video.stem}.json"

        if not tracking_file.exists():
            print(f"Tracking missing for {video.name}")
            continue

        with open(tracking_file, "r", encoding="utf-8") as f:
            tracking = json.load(f)

        cap = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video)
            ],
            capture_output=True,
            text=True
        )

        width = int(cap.stdout.strip())

        camera_path = build_camera_path(
            tracking,
            width
        )

        print(
            f"{video.name}: generated {len(camera_path)} camera positions."
        )

        output_video = output_dir / video.name

        render_vertical(
            video,
            output_video
        )

        print(f"Saved -> {output_video}")

    print("\n✅ Vertical formatting complete.")


if __name__ == "__main__":
    main()