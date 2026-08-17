from agents.base_agent import BaseAgent


class MarketingAgent(BaseAgent):

    def __init__(self):
        super().__init__()

    def run(self):

        self.log("Generating marketing content...")
        self.run_script("scripts/ai/content_generator.py")

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