import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def main():
    clips_file = PROJECT_ROOT / "output" / "clips.json"
    plan_file = PROJECT_ROOT / "content_plan.json"

    if not clips_file.exists():
        raise FileNotFoundError(f"Clips file not found: {clips_file}")

    with open(clips_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # total demand nikaalo content_plan se
    total_needed = 8  # safe default
    if plan_file.exists():
        with open(plan_file, "r", encoding="utf-8") as f:
            plan = json.load(f)
        total_needed = sum(p.get("count", 0) for p in plan.values())

    # kam se kam thoda buffer rakho (duplicates avoid karne ke liye jo platform_router baad me karega)
    buffer = min(total_needed + 3, len(data["clips"]))

    sorted_clips = sorted(
        data["clips"],
        key=lambda c: c.get("overall_score", 0),
        reverse=True
    )

    trimmed = sorted_clips[:buffer]

    output = {
        "total_selected": len(trimmed),
        "clips": trimmed
    }

    with open(clips_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4, ensure_ascii=False)

    print(f"✅ Trimmed clips.json: {len(data['clips'])} -> {len(trimmed)} clips (needed: {total_needed})")


if __name__ == "__main__":
    main()