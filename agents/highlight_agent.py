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

        self.log("Analyzing transcript windows...")

        # Score every candidate. Ranking happens AFTER strategy so we
        # know how many videos the campaign actually needs.
        subprocess.run(
            [
                PYTHON,
                "scripts/ai/clip_intelligence.py"
            ],
            cwd=PROJECT_ROOT,
            check=True
        )

        self.memory.update(
            "analysis_path",
            "output/analysis.json"
        )

        self.log("Highlight analysis completed.")

        return "output/analysis.json"