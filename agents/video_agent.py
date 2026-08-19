from pathlib import Path
import subprocess
import sys

from agents.base_agent import BaseAgent

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def _run(args, cwd=PROJECT_ROOT):
    result = subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        marker = "YouTube blocked this download"
        if marker in detail:
            raise RuntimeError(detail[detail.rfind(marker):].strip()[:1200])
        cmd = " ".join(str(a) for a in args)
        raise RuntimeError(f"{cmd}\n{detail[-2500:]}")
    if result.stdout:
        print(result.stdout)
    return result


class VideoAgent(BaseAgent):

    def __init__(self):
        super().__init__()
        self.python = PYTHON

    def run(self, input_source):

        self.log("Starting video processing...")

        if str(input_source).startswith("http://") or str(input_source).startswith("https://"):
            # One argv: playlist query strings contain &, which a shell would split.
            _run(
                [
                    self.python,
                    "scripts/pipeline/download_video.py",
                    str(input_source).strip(),
                ]
            )

            input_source = "input/video.mp4"

        self.memory.update(
            "video_path",
            input_source
        )

        _run(
            [
                self.python,
                "scripts/pipeline/video_processor.py",
                input_source
            ]
        )

        self.memory.update(
            "metadata_path",
            "output/metadata.json"
        )

        self.log("Video processing completed.")

        return input_source
