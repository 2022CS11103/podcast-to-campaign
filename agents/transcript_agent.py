from pathlib import Path
import subprocess
import sys

from agents.base_agent import BaseAgent

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


class TranscriptAgent(BaseAgent):

    def __init__(self):
        super().__init__()

    def run(self):

        self.log("Generating transcript...")

        # Transcribe audio
        subprocess.run(
            [
                PYTHON,
                "scripts/pipeline/transcriber.py"
            ],
            cwd=PROJECT_ROOT,
            check=True
        )

        # Clean transcript
        subprocess.run(
            [
                PYTHON,
                "scripts/pipeline/clean_transcript.py",
                "output/transcript.json"
            ],
            cwd=PROJECT_ROOT,
            check=True
        )

        # Create chunks
        subprocess.run(
            [
                PYTHON,
                "scripts/pipeline/chunk_transcript.py",
                "output/clean_transcript.json"
            ],
            cwd=PROJECT_ROOT,
            check=True
        )

        # Update shared memory
        self.memory.update(
            "transcript_path",
            "output/transcript.json"
        )

        self.memory.update(
            "clean_transcript_path",
            "output/clean_transcript.json"
        )

        self.memory.update(
            "chunks_path",
            "output/chunks.json"
        )

        self.log("Transcript generation completed.")

        return "output/chunks.json"