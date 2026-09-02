from pathlib import Path
import os
import subprocess
import sys

from agents.base_agent import BaseAgent
from scripts.pipeline.download_video import local_video_for_url

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
_SUBPROCESS_LOG = PROJECT_ROOT / "output" / "_last_subprocess.log"


def _safe_console_write(text: str) -> None:
    """Worker threads on Windows can hit cp1252 / broken stdout — never crash on print."""
    try:
        print(text, end="" if text.endswith("\n") else "\n", flush=True)
    except OSError:
        pass


def _run(args, cwd=PROJECT_ROOT):
    """Run a pipeline script; log output to a file instead of a pipe.

    Piping yt-dlp progress through a background thread can raise OSError on
    Windows and was misreported as a failed YouTube save.
    """
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "PYTHONUNBUFFERED": "1",
    }
    _SUBPROCESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(_SUBPROCESS_LOG, "w", encoding="utf-8", errors="replace") as log:
        result = subprocess.run(
            args,
            cwd=str(cwd),
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    detail = _SUBPROCESS_LOG.read_text(encoding="utf-8", errors="replace").strip()
    if detail:
        _safe_console_write(detail if detail.endswith("\n") else detail + "\n")
    if result.returncode != 0:
        marker = "YouTube blocked this download"
        if marker in detail:
            raise RuntimeError(detail[detail.rfind(marker):].strip()[:1200])
        cmd = " ".join(str(a) for a in args)
        raise RuntimeError(f"{cmd}\n{detail[-2500:] or f'exit {result.returncode}'}")
    return detail


class VideoAgent(BaseAgent):

    def __init__(self):
        super().__init__()
        self.python = PYTHON

    def run(self, input_source):

        self.log("Starting video processing...")

        if str(input_source).startswith("http://") or str(input_source).startswith("https://"):
            url = str(input_source).strip()
            if local_video_for_url(url):
                self.log("Reusing the existing download for this YouTube link.")
            else:
                # One argv: playlist query strings contain &, which a shell would split.
                _run(
                    [
                        self.python,
                        "scripts/pipeline/download_video.py",
                        url,
                    ]
                )
            input_source = "input/video.mp4"

        video_path = Path(input_source)
        if not video_path.is_absolute():
            video_path = PROJECT_ROOT / video_path
        if not video_path.exists():
            raise RuntimeError(
                f"Source video not found: {video_path}. "
                "Re-upload the file or paste the YouTube URL again."
            )

        self.memory.update(
            "video_path",
            str(input_source)
        )

        _run(
            [
                self.python,
                "scripts/pipeline/video_processor.py",
                str(input_source)
            ]
        )

        self.memory.update(
            "metadata_path",
            "output/metadata.json"
        )

        self.log("Video processing completed.")

        return input_source
