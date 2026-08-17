from agents.base_agent import BaseAgent


class TranscriptAgent(BaseAgent):

    def run(self):

        self.log("Scan talk in slices until enough strong clips — skip the rest.")

        self.run_script("scripts/pipeline/scan_highlights.py")

        self.memory.update("transcript_path", "output/transcript.json")
        self.memory.update("clean_transcript_path", "output/clean_transcript.json")
        self.memory.update("chunks_path", "output/chunks.json")
        self.memory.update("analysis_path", "output/analysis.json")

        self.log("Highlight scan completed.")

        return "output/chunks.json"
