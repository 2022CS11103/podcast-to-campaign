import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def main():
    bank_file = PROJECT_ROOT / "output" / "content_bank.json"
    if not bank_file.exists():
        raise FileNotFoundError(f"Content bank not found: {bank_file}")

    with open(bank_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = sorted(data["items"], key=lambda x: x["scheduled_date"])

    lines = []
    lines.append("# 30-Day Content Calendar\n")
    lines.append(f"Generated: {data['generated_at']}")
    lines.append(f"Total pieces: {data['total_allocated']}\n")

    for item in items:
        platform_label = item["assigned_platform"].replace("_", " ").title()
        lines.append(f"## {item['scheduled_date']} — {platform_label}")
        lines.append(f"**Hook (variant {item.get('active_variant', 'A')}):** {item['hook']}")
        lines.append(f"**Content Angle:** {item.get('content_angle', 'General')}")
        lines.append(f"**Why this clip:** Fit score {item['platform_fit_score']} for {platform_label} — selected for its strength in this platform's key drivers.")
        lines.append(f"**Duration:** {item['duration_seconds']}s")
        spec = item.get("duration_spec") or {}
        if spec.get("ideal_seconds"):
            lines.append(f"**Length target:** {spec.get('min_seconds')}–{spec.get('max_seconds')}s (ideal {spec.get('ideal_seconds')}s)")
        variants = item.get("variants") or []
        if len(variants) > 1:
            held = ", ".join(f"{v['id']} ({v.get('angle','')})" for v in variants[1:])
            lines.append(f"**A/B held:** {held}")
        lines.append(f"**Status:** {item.get('status', 'pending')}")
        lines.append("")

    output_file = PROJECT_ROOT / "output" / "campaign_calendar.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✅ Campaign calendar saved to {output_file}")


if __name__ == "__main__":
    main()