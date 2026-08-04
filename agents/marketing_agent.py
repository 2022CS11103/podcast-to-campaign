from pathlib import Path
import subprocess
import sys

from agents.base_agent import BaseAgent

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


class MarketingAgent(BaseAgent):

    def __init__(self):
        super().__init__()

    def run(self):

        self.log("Generating marketing content...")

        subprocess.run(
            [
                PYTHON,
                "scripts/ai/content_generator.py"
            ],
            cwd=PROJECT_ROOT,
            check=True
        )

        # Update shared memory
        self.memory.update(
            "marketing_folder",
            "output"
        )

        self.memory.update(
            "marketing_completed",
            True
        )

        self.log("Marketing content generated.")

        return "output"