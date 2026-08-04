from pathlib import Path
import subprocess
import sys

from agents.base_agent import BaseAgent

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


class HighlightAgent(BaseAgent):

    def __init__(self):
        super().__init__()

    def run(self):

        self.log("Analyzing transcript...")

        # AI analyzes transcript chunks
        subprocess.run(
            [
                PYTHON,
                "scripts/ai/clip_intelligence.py"
            ],
            cwd=PROJECT_ROOT,
            check=True
        )

        self.log("Ranking best clips...")

        # Rank clips
        subprocess.run(
            [
                PYTHON,
                "scripts/ai/clip_ranker.py"
            ],
            cwd=PROJECT_ROOT,
            check=True
        )

        # Update shared memory
        self.memory.update(
            "analysis_path",
            "output/analysis.json"
        )

        self.memory.update(
            "clips_path",
            "output/clips.json"
        )

        self.log("Highlight generation completed.")

        return "output/clips.json"