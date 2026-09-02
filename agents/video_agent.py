from pathlib import Path
import os
import subprocess
import sys

from agents.base_agent import BaseAgent

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def _run(args, cwd=PROJECT_ROOT):
    """Stream child output. capture_output deadlocks on Windows when yt-dlp
    floods stderr with download progress and the pipe buffer fills."""
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "PYTHONUNBUFFERED": "1",
    }
    proc = subprocess.Popen(
        args,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        bufsize=1,
    )
    lines = []
    assert proc.stdout is not None
    for line in proc.stdout:
        lines.append(line)
        print(line, end="", flush=True)
    proc.wait()
    detail = "".join(lines).strip()
    if proc.returncode != 0:
        marker = "YouTube blocked this download"
        if marker in detail:
            raise RuntimeError(detail[detail.rfind(marker):].strip()[:1200])
        cmd = " ".join(str(a) for a in args)
        # Keep the real OS error visible (e.g. Errno 22) without losing context.
        raise RuntimeError(f"{cmd}\n{detail[-2500:] or f'exit {proc.returncode}'}")
    return detail


class VideoAgent(BaseAgent):

    def __init__(self):
        super().__init__()
        self.python = PYTHON

    def run(self, input_source):

        self.log("Starting video processing...")

        if str(input_source).startswith("http://") or str(input_source).startswith("https://"):
            # One argv: playlist query strings contain &, which a shell would split.
            try:
                _run(
                    [
                        self.python,
                        "scripts/pipeline/download_video.py",
                        str(input_source).strip(),
                    ]
                )
            except OSError as exc:
                raise RuntimeError(
                    "YouTube download hit a Windows file error while saving the video. "
                    "Try Again, or upload the MP4 instead."
                ) from exc

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
