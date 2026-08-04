from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def load_prompt(name: str) -> str:
    path = PROJECT_ROOT / "prompts" / f"{name}.txt"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()