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

        # Get video path from shared memory
        video_path = self.memory.get("video_path")

        if video_path is None:
            raise ValueError("video_path not found in memory.")

        # Cut top clips
        subprocess.run(
            [
                PYTHON,
                "scripts/video/video_cutter.py",
                video_path
            ],
            cwd=PROJECT_ROOT,
            check=True
        )

        # Detect speaker
        subprocess.run(
            [
                PYTHON,
                "scripts/video/face_tracker.py"
            ],
            cwd=PROJECT_ROOT,
            check=True
        )

        # Smart crop
        subprocess.run(
            [
                PYTHON,
                "scripts/video/smart_crop.py"
            ],
            cwd=PROJECT_ROOT,
            check=True
        )

        # Generate subtitles
        subprocess.run(
            [
                PYTHON,
                "scripts/video/subtitle_generator.py"
            ],
            cwd=PROJECT_ROOT,
            check=True
        )

        # Burn subtitles
        subprocess.run(
            [
                PYTHON,
                "scripts/video/subtitle_burner.py"
            ],
            cwd=PROJECT_ROOT,
            check=True
        )

        # Update memory
        self.memory.update(
            "shorts_folder",
            "output/final_shorts"
        )

        self.memory.update(
            "editing_completed",
            True
        )

        self.log("Video editing completed.")

        return "output/final_shorts"