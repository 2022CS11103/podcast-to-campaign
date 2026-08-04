import sys
from pathlib import Path
import yt_dlp


# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def download_video(url):
    """
    Downloads a YouTube video as MP4 into input/video.mp4
    """

    input_dir = PROJECT_ROOT / "input"
    input_dir.mkdir(exist_ok=True)

    output_path = input_dir / "video.mp4"

    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "outtmpl": str(output_path),
        "quiet": False,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    return output_path


def main():

    if len(sys.argv) < 2:
        print("Usage:")
        print("python scripts/download_video.py <youtube_url>")
        return

    url = sys.argv[1]

    print("Downloading video...")

    video_path = download_video(url)

    print(f"\nVideo downloaded successfully!")
    print(f"Saved at: {video_path}")


if __name__ == "__main__":
    main()