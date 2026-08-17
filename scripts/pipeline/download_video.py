import sys
from pathlib import Path
import yt_dlp

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def download_video(url):
    """
    Downloads a YouTube video as MP4 into input/video.mp4
    """
    input_dir = PROJECT_ROOT / "input"
    input_dir.mkdir(exist_ok=True)

    output_path = input_dir / "video.mp4"
    if output_path.exists():
        output_path.unlink()

    # Avoid video.mp4.mp4 from yt-dlp treating the full name as a template.
    tmpl = str(input_dir / "video.%(ext)s")

    ydl_opts = {
        "format": "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b",
        "format_sort": ["res:1080", "ext:mp4:m4a"],
        "merge_output_format": "mp4",
        "outtmpl": tmpl,
        "quiet": False,
        "noplaylist": True,
        "retries": 5,
        "fragment_retries": 5,
        "nocheckcertificate": True,
        "extractor_args": {"youtube": {"player_client": ["web", "android"]}},
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    produced = output_path
    if not produced.exists():
        matches = sorted(input_dir.glob("video.*"))
        if not matches:
            raise FileNotFoundError("yt-dlp finished but input/video.mp4 was not created")
        produced = matches[0]
        if produced.suffix.lower() != ".mp4":
            produced.replace(output_path)
        elif produced != output_path:
            produced.replace(output_path)

    if not output_path.exists():
        raise FileNotFoundError(f"Expected {output_path} after download")

    return output_path


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("python scripts/pipeline/download_video.py <youtube_url>")
        sys.exit(2)

    url = sys.argv[1]
    print("Downloading video...")
    try:
        video_path = download_video(url)
    except Exception as e:
        print(f"DOWNLOAD FAILED: {e}", file=sys.stderr)
        sys.exit(1)

    print("\nVideo downloaded successfully!")
    print(f"Saved at: {video_path}")


if __name__ == "__main__":
    main()
