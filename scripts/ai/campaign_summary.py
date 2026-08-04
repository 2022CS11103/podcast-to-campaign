import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def main():
    output_dir = PROJECT_ROOT / "output"

    content_bank_file = output_dir / "content_bank.json"
    cost_file = output_dir / "cost_report.json"
    brand_file = PROJECT_ROOT / "brand_context.json"

    content_bank = {}
    if content_bank_file.exists():
        with open(content_bank_file, "r", encoding="utf-8") as f:
            content_bank = json.load(f)

    cost_report = {}
    if cost_file.exists():
        with open(cost_file, "r", encoding="utf-8") as f:
            cost_report = json.load(f)

    brand = {}
    if brand_file.exists():
        with open(brand_file, "r", encoding="utf-8") as f:
            brand = json.load(f)

    items = content_bank.get("items", [])

    # platform-wise breakdown
    platform_counts = {}
    for item in items:
        p = item["assigned_platform"]
        platform_counts[p] = platform_counts.get(p, 0) + 1

    dates = [item["scheduled_date"] for item in items]
    campaign_span_days = 0
    if dates:
        d_min = datetime.strptime(min(dates), "%Y-%m-%d")
        d_max = datetime.strptime(max(dates), "%Y-%m-%d")
        campaign_span_days = (d_max - d_min).days

    summary = {
        "brand_name": brand.get("brand_name", "N/A"),
        "campaign_goal": brand.get("goal", "N/A"),
        "target_audience": brand.get("audience", "N/A"),
        "tone": brand.get("tone", "N/A"),
        "total_content_pieces": len(items),
        "platform_breakdown": platform_counts,
        "campaign_span_days": campaign_span_days,
        "estimated_cost_inr": cost_report.get("estimated_cost_inr", 0),
        "estimated_cost_usd": cost_report.get("estimated_cost_usd", 0),
        "total_ai_calls": cost_report.get("total_gemini_calls", 0),
        "whisper_processing_seconds": cost_report.get("whisper_processing_seconds", 0),
    }

    # human-readable markdown version
    lines = []
    lines.append(f"# Campaign Summary — {summary['brand_name']}\n")
    lines.append(f"**Goal:** {summary['campaign_goal']}")
    lines.append(f"**Audience:** {summary['target_audience']}")
    lines.append(f"**Tone:** {summary['tone']}\n")
    lines.append(f"## What was generated")
    lines.append(f"- **{summary['total_content_pieces']} content pieces** total")
    for platform, count in platform_counts.items():
        label = platform.replace("_", " ").title()
        lines.append(f"  - {count} × {label}")
    lines.append(f"- Spread across **{summary['campaign_span_days']} days**\n")
    lines.append(f"## Cost")
    lines.append(f"- Estimated cost: ₹{summary['estimated_cost_inr']} (${summary['estimated_cost_usd']})")
    lines.append(f"- AI calls used: {summary['total_ai_calls']}")
    lines.append(f"- Transcription time: {summary['whisper_processing_seconds']}s\n")

    md_file = output_dir / "campaign_summary.md"
    with open(md_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    json_file = output_dir / "campaign_summary.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"✅ Campaign summary saved to {md_file} and {json_file}")


if __name__ == "__main__":
    main()