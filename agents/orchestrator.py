from pathlib import Path
import subprocess
import sys

from agents.video_agent import VideoAgent
from agents.transcript_agent import TranscriptAgent
from agents.highlight_agent import HighlightAgent
from agents.editing_agent import EditingAgent
from agents.marketing_agent import MarketingAgent

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


class CreatorOS:

    def __init__(self):

        self.video = VideoAgent()
        self.transcript = TranscriptAgent()
        self.highlight = HighlightAgent()
        self.editor = EditingAgent()
        self.marketing = MarketingAgent()

    def _script(self, path: str):
        subprocess.run([PYTHON, path], cwd=PROJECT_ROOT, check=True)

    def run(self, input_source):

        print("\n" + "=" * 60)
        print("🚀 CreatorOS Multi-Agent System")
        print("=" * 60)

        print("\n🎥 Video Agent")
        self.video.run(input_source)

        print("\n📝 Transcript Agent")
        self.transcript.run()

        print("\n🧠 Highlight Agent")
        self.highlight.run()

        print("\n🎯 Strategy")
        self._script("scripts/ai/strategy_agent.py")

        print("\n🏆 Ranking")
        self._script("scripts/ai/clip_ranker.py")

        print("\n✂️ Editing Agent")
        self.editor.run()

        print("\n🧭 Platform routing")
        self._script("scripts/ai/platform_router.py")

        print("\n📢 Marketing Agent")
        self.marketing.run()

        print("\n📅 Campaign planning")
        self._script("scripts/ai/campaign_planner.py")
        self._script("scripts/ai/campaign_summary.py")
        self._script("scripts/ai/package_manifest.py")

        print("\n" + "=" * 60)
        print("🎉 CreatorOS completed successfully!")
        print("=" * 60)


if __name__ == "__main__":

    creator = CreatorOS()

    creator.run(
        "https://www.youtube.com/watch?v=GU_loPs2wXw"
    )
