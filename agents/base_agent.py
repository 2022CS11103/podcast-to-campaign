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
        env = {
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "PYTHONUNBUFFERED": "1",
        }
        proc = subprocess.Popen(
            [PYTHON, "-u", *args],
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            bufsize=1,
        )
        output = []
        for line in proc.stdout:
            output.append(line)
            print(line, end="", flush=True)
        proc.wait()
        if proc.returncode != 0:
            detail = "".join(output).strip()
            raise RuntimeError(f"{args[0]} failed:\n{detail[-2500:]}")
        return proc