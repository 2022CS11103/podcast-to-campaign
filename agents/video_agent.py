from pathlib import Path
import subprocess
import sys

from agents.base_agent import BaseAgent

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


class VideoAgent(BaseAgent):

    def __init__(self):
        super().__init__()
        self.python = PYTHON

    def run(self, input_source):

        self.log("Starting video processing...")

        # Download if YouTube URL
        if input_source.startswith("http://") or input_source.startswith("https://"):

            subprocess.run(
                [
                    self.python,
                    "scripts/pipeline/download_video.py",
                    input_source
                ],
                cwd=PROJECT_ROOT,
                check=True
            )

            input_source = "input/video.mp4"

        # Save video path to memory
        self.memory.update(
            "video_path",
            input_source
        )

        # Extract audio + metadata
        subprocess.run(
            [
                self.python,
                "scripts/pipeline/video_processor.py",
                input_source
            ],
            cwd=PROJECT_ROOT,
            check=True
        )

        # Save outputs to memory
        self.memory.update(
            "audio_path",
            "output/audio.wav"
        )

        self.memory.update(
            "metadata_path",
            "output/metadata.json"
        )

        self.log("Video processing completed.")

        return "output/audio.wav"