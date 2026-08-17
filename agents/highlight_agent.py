import json
from pathlib import Path

from agents.base_agent import BaseAgent

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class HighlightAgent(BaseAgent):

    def run(self):
        analysis = PROJECT_ROOT / "output" / "analysis.json"
        if analysis.exists():
            with open(analysis, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("scan_complete"):
                self.log("Scan already scored clips — skipping a second Gemini pass.")
                self.memory.update("analysis_path", "output/analysis.json")
                return "output/analysis.json"

        self.log("Analyzing transcript windows...")
        self.run_script("scripts/ai/clip_intelligence.py")
        self.memory.update("analysis_path", "output/analysis.json")
        self.log("Highlight analysis completed.")
        return "output/analysis.json"
