from pathlib import Path

from agents.base_agent import BaseAgent

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class EditingAgent(BaseAgent):

    def __init__(self):
        super().__init__()

    def run(self):

        self.log("Starting Mosaic-style edit agent...")

        video_path = self.memory.get("video_path")
        if video_path is None:
            raise ValueError("video_path not found in memory.")

        video = Path(str(video_path))
        if not video.is_absolute():
            video = PROJECT_ROOT / video

        self.run_script("scripts/ai/edit_director.py")
        self.run_script("scripts/video/edit_executor.py", str(video))

        shorts = list((PROJECT_ROOT / "output" / "final_shorts").glob("short_*.mp4"))
        if not shorts:
            raise RuntimeError("Editing finished but no short_*.mp4 files were written.")

        self.memory.update("shorts_folder", "output/final_shorts")
        self.memory.update("editing_completed", True)
        self.log(f"Edit agent completed ({len(shorts)} mosaic cuts).")

        return "output/final_shorts"
