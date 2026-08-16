from pathlib import Path
import subprocess
import sys

from agents.base_agent import BaseAgent

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


class EditingAgent(BaseAgent):

    def __init__(self):
        super().__init__()

    def run(self):

        self.log("Starting video editing...")

        video_path = self.memory.get("video_path")

        if video_path is None:
            raise ValueError("video_path not found in memory.")

        # Captions from the cheap transcript (segment timestamps).
        subprocess.run(
            [PYTHON, "scripts/video/subtitle_generator.py"],
            cwd=PROJECT_ROOT,
            check=True,
        )

        # One FFmpeg pass per winning clip. No YOLO, no triple re-encode.
        subprocess.run(
            [PYTHON, "scripts/video/render_shorts.py", video_path],
            cwd=PROJECT_ROOT,
            check=True,
        )

        self.memory.update("shorts_folder", "output/final_shorts")
        self.memory.update("editing_completed", True)
        self.log("Video editing completed.")

        return "output/final_shorts"
