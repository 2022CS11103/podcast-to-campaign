import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

STATE_FILE = PROJECT_ROOT / "memory" / "state.json"


class MemoryManager:

    def __init__(self):

        STATE_FILE.parent.mkdir(exist_ok=True)

        if not STATE_FILE.exists():
            with open(STATE_FILE, "w") as f:
                json.dump({}, f)

    def load(self):
        with open(STATE_FILE, "r") as f:
            return json.load(f)

    def save(self, data):
        with open(STATE_FILE, "w") as f:
            json.dump(data, f, indent=4)

    def update(self, key, value):
        data = self.load()
        data[key] = value
        self.save(data)

    def get(self, key):
        data = self.load()
        return data.get(key)