from abc import ABC, abstractmethod
import os
import subprocess
import sys
from pathlib import Path
from memory.memory_manager import MemoryManager

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


class BaseAgent(ABC):

    def __init__(self):
        self.memory = MemoryManager()

    @abstractmethod
    def run(self, *args, **kwargs):
        pass

    def log(self, message):
        print(f"[{self.__class__.__name__}] {message}")

    def run_script(self, *args):
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        result = subprocess.run(
            [PYTHON, *args],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        if result.stdout:
            print(result.stdout)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"{args[0]} failed:\n{detail[-2500:]}")
        return result