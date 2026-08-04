from agents.video_agent import VideoAgent
from agents.transcript_agent import TranscriptAgent
from agents.highlight_agent import HighlightAgent
from agents.editing_agent import EditingAgent
from agents.marketing_agent import MarketingAgent

class CreatorOS:

    def __init__(self):

        self.video = VideoAgent()
        self.transcript = TranscriptAgent()
        self.highlight = HighlightAgent()
        self.editor = EditingAgent()
        self.marketing = MarketingAgent()

    def run(self, input_source):

        print("\n" + "=" * 60)
        print("🚀 CreatorOS Multi-Agent System")
        print("=" * 60)

        # Step 1
        print("\n🎥 Video Agent")
        self.video.run(input_source)

        # Step 2
        print("\n📝 Transcript Agent")
        self.transcript.run()

        # Step 3
        print("\n🧠 Highlight Agent")
        self.highlight.run()

        # Step 4
        print("\n✂️ Editing Agent")
        self.editor.run()

        # Step 5
        print("\n📢 Marketing Agent")
        self.marketing.run()

        print("\n" + "=" * 60)
        print("🎉 CreatorOS completed successfully!")
        print("=" * 60)


if __name__ == "__main__":

    creator = CreatorOS()

    creator.run(
        "https://www.youtube.com/watch?v=GU_loPs2wXw"
    )