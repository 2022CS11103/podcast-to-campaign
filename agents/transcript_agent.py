from agents.base_agent import BaseAgent


class TranscriptAgent(BaseAgent):

    def run(self):

        self.log("Fast transcript, then chunk windows (select before any video encode)...")

        self.run_script("scripts/pipeline/transcriber.py")
        self.run_script("scripts/pipeline/clean_transcript.py", "output/transcript.json")
        self.run_script("scripts/pipeline/chunk_transcript.py", "output/clean_transcript.json")

        self.memory.update("transcript_path", "output/transcript.json")
        self.memory.update("clean_transcript_path", "output/clean_transcript.json")
        self.memory.update("chunks_path", "output/chunks.json")

        self.log("Transcript generation completed.")

        return "output/chunks.json"
