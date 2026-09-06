import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from utils.gemini_clients import generate_content
from utils.prompt_loader import load_prompt
from utils.cost_tracker import log_gemini_call
from config.platform_specs import AB_VARIANT_IDS

# Per-clip copy is generated against the platform the router assigned.
# Pillar pieces are generated once from the full talk (SEO + email).
PILLAR_PLATFORMS = ("blog", "newsletter")

VARIANT_JSON_FOOTER = """
Return ONLY valid JSON, no markdown:
{{
  "variants": [
    {{"id": "A", "angle": "curiosity", "hook": "max 12 words", "caption": "platform-native caption"}},
    {{"id": "B", "angle": "educational", "hook": "max 12 words", "caption": "platform-native caption"}},
    {{"id": "C", "angle": "emotional", "hook": "max 12 words", "caption": "platform-native caption"}}
  ]
}}

Rules for all platforms:
- Variant A ships first. B and C are held for A/B tests.
- Hook is on-screen text for the edited Short (max 8 words). Match the jump-cut, not the full talk.
- Caption must sell THIS clip's moment — not the whole episode.
- Do not mention A/B testing, AI, or "we clipped this from a podcast".

Platform: {platform}
Brand context:
{brand}
Clip summary: {summary}
Existing hook: {hook}
Transcript window:
{text}
"""

SHORTFORM_VARIANT_PROMPT = """You write A/B/C hooks and captions for a vertical short-form clip.

Caption rules for {platform}:
- 80-130 words with line breaks
- End with 5-8 relevant hashtags
- Punchy, spoken-word energy; open with the same hook as the cut
- youtube_shorts may use Title / Description / Tags if that fits better than a single caption block
""" + VARIANT_JSON_FOOTER

LINKEDIN_VARIANT_PROMPT = """You write A/B/C LinkedIn posts for decision-makers from one short clip moment.

Follow this LinkedIn voice (thought-leadership, not entertainment):
{platform_brief}

Caption rules for linkedin:
- 150-220 words, short paragraphs, professional but human
- Open with a strong insight line (same idea as the hook)
- Frame as a lesson, framework, or business takeaway from THIS moment
- Max 3 hashtags at the end
- End with a question or clear CTA
- No emoji spam, no "thread" numbering
""" + VARIANT_JSON_FOOTER

TWITTER_VARIANT_PROMPT = """You write A/B/C X/Twitter threads from one short clip moment.

Follow this X voice:
{platform_brief}

Caption rules for twitter:
- Format the caption as a 5-8 tweet thread
- Tweet 1 = hook under 200 characters, no hashtags
- Tweets 2–N numbered (2/, 3/, …), one idea each
- Final tweet = question or CTA, max 2 hashtags
- Punchy and specific — no corporate filler
""" + VARIANT_JSON_FOOTER


def _platform_brief(platform: str) -> str:
    name = {
        "linkedin": "linkedin",
        "twitter": "twitter",
        "youtube_shorts": "youtube",
        "instagram_reels": "instagram",
        "tiktok": "instagram",
    }.get(platform)
    if not name:
        return ""
    try:
        return load_prompt(name).strip()
    except FileNotFoundError:
        return ""


def variant_prompt_for(platform: str) -> str:
    if platform == "linkedin":
        return LINKEDIN_VARIANT_PROMPT
    if platform == "twitter":
        return TWITTER_VARIANT_PROMPT
    return SHORTFORM_VARIANT_PROMPT


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_brand_context():
    return load_json(PROJECT_ROOT / "brand_context.json", default={}) or {}


def build_brand_prefix(brand):
    if not brand:
        return ""
    parts = []
    if brand.get("brand_name"):
        parts.append(f"Brand: {brand['brand_name']}")
    if brand.get("goal"):
        parts.append(f"Campaign Goal: {brand['goal']}")
    if brand.get("audience"):
        parts.append(f"Target Audience: {brand['audience']}")
    if brand.get("tone"):
        parts.append(f"Tone of Voice: {brand['tone']}")
    if not parts:
        return ""
    return "Context for this content:\n" + "\n".join(parts) + "\n\n"


def generate_text(prompt: str, step: str) -> str:
    response = generate_content(prompt)
    log_gemini_call(step, response)
    return response.text


def parse_variants(raw: str, fallback_hook: str, fallback_caption: str):
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(cleaned)
        variants = data.get("variants") or []
    except Exception:
        variants = []

    by_id = {v.get("id"): v for v in variants if isinstance(v, dict)}
    out = []
    for vid in AB_VARIANT_IDS:
        v = by_id.get(vid) or {}
        out.append({
            "id": vid,
            "angle": v.get("angle") or {"A": "curiosity", "B": "educational", "C": "emotional"}[vid],
            "hook": v.get("hook") or fallback_hook,
            "caption": v.get("caption") or fallback_caption,
            "status": "untested",
            "impressions": 0,
            "views": 0,
            "likes": 0,
            "comments": 0,
        })
    return out


def full_transcript_text():
    clean = load_json(PROJECT_ROOT / "output" / "clean_transcript.json") or {}
    text = clean.get("transcript") or ""
    if text:
        return text
    clips = load_json(PROJECT_ROOT / "output" / "clips.json") or {}
    parts = []
    for clip in clips.get("clips", []):
        parts.append(clip.get("text") or clip.get("summary") or "")
    return "\n\n".join(p for p in parts if p)


def generate_pillar(platform: str, brand_prefix: str, transcript: str) -> str:
    prompt = load_prompt(platform)
    try:
        return generate_text(
            f"{brand_prefix}{prompt}\n\nFull talk transcript:\n{transcript[:8000]}",
            f"marketing_{platform}",
        )
    except Exception as exc:
        print(f"  pillar {platform} failed after retries ({exc}). Writing a fallback.")
        excerpt = (transcript or "").strip()[:1200]
        return (
            f"# {platform.title()}\n\n"
            f"{brand_prefix}"
            f"Draft generated without live model (Gemini was busy).\n\n"
            f"{excerpt}\n"
        )


def generate_item_variants(item: dict, clip_lookup: dict, brand: dict) -> list:
    chunk_id = item.get("chunk_id")
    clip = clip_lookup.get(chunk_id, {})
    text = clip.get("text") or item.get("summary") or ""
    fallback_caption = item.get("summary") or ""
    fallback_hook = item.get("hook") or clip.get("hook") or ""
    platform = item.get("assigned_platform", "instagram_reels")
    template = variant_prompt_for(platform)
    prompt = template.format(
        platform=platform,
        platform_brief=_platform_brief(platform),
        brand=json.dumps(brand, indent=2),
        summary=item.get("summary") or clip.get("summary") or "",
        hook=fallback_hook,
        text=text[:4000],
    )
    try:
        raw = generate_text(prompt, f"marketing_variants_{platform}")
        return parse_variants(raw, fallback_hook, fallback_caption)
    except Exception as exc:
        print(f"  variants for {item.get('id')} failed ({exc}). Using hook fallback.")
        return parse_variants("", fallback_hook, fallback_caption)


def main():
    brand = load_brand_context()
    brand_prefix = build_brand_prefix(brand)
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(exist_ok=True)

    transcript = full_transcript_text()
    if not transcript:
        raise FileNotFoundError("No transcript or clips found to generate from.")

    for platform in PILLAR_PLATFORMS:
        print(f"Generating pillar {platform} content...")
        content = generate_pillar(platform, brand_prefix, transcript)
        output_file = output_dir / f"{platform}.md"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ Saved {platform} -> {output_file}")

    bank_file = output_dir / "content_bank.json"
    clips_file = output_dir / "clips.json"
    bank = load_json(bank_file)
    clips_data = load_json(clips_file, default={"clips": []}) or {"clips": []}
    clip_lookup = {c.get("chunk_id"): c for c in clips_data.get("clips", [])}

    if bank and bank.get("items"):
        posts_dir = output_dir / "posts"
        posts_dir.mkdir(exist_ok=True)

        def _variants_for(item):
            print(f"Generating A/B variants for {item['id']} ({item['assigned_platform']})...")
            return item["id"], generate_item_variants(item, clip_lookup, brand)

        variant_map = {}
        with ThreadPoolExecutor(max_workers=3) as pool:
            futs = [pool.submit(_variants_for, item) for item in bank["items"]]
            for fut in as_completed(futs):
                item_id, variants = fut.result()
                variant_map[item_id] = variants

        for item in bank["items"]:
            variants = variant_map.get(item["id"]) or parse_variants(
                "", item.get("hook") or "", item.get("summary") or ""
            )
            item["variants"] = variants
            item["active_variant"] = "A"
            item["performance"] = item.get("performance") or {
                "impressions": 0,
                "views": 0,
                "likes": 0,
                "comments": 0,
                "shares": 0,
                "ctr": 0.0,
                "engagement_rate": 0.0,
            }
            item["repost_count"] = item.get("repost_count", 0)

            post_file = posts_dir / f"{item['id']}_{item['assigned_platform']}.md"
            active = variants[0]
            with open(post_file, "w", encoding="utf-8") as f:
                f.write(f"# {item['id']} — {item['assigned_platform']}\n\n")
                f.write(f"**Active variant:** A ({active['angle']})\n\n")
                f.write(f"## Hook\n{active['hook']}\n\n")
                f.write(f"## Caption\n{active['caption']}\n\n")
                f.write("## Held variants (A/B)\n")
                for v in variants[1:]:
                    f.write(f"\n### {v['id']} — {v['angle']}\n**Hook:** {v['hook']}\n\n{v['caption']}\n")
            item["post_file"] = str(post_file)

        with open(bank_file, "w", encoding="utf-8") as f:
            json.dump(bank, f, indent=2, ensure_ascii=False)
        print(f"✅ Variants written into {bank_file}")

    # Keep legacy combined files so the current frontend still has
    # linkedin.md / twitter.md / youtube.md / instagram.md to preview.
    platform_blobs = {}
    if bank:
        for item in bank.get("items", []):
            p = item.get("assigned_platform")
            active = (item.get("variants") or [{}])[0]
            platform_blobs.setdefault(p, []).append(
                f"## {item.get('id')}\n**Hook:** {active.get('hook','')}\n\n{active.get('caption','')}\n"
            )
    name_map = {
        "linkedin": "linkedin.md",
        "twitter": "twitter.md",
        "youtube_shorts": "youtube.md",
        "instagram_reels": "instagram.md",
        "tiktok": "tiktok.md",
    }
    for platform, filename in name_map.items():
        blob = platform_blobs.get(platform)
        if not blob:
            continue
        with open(output_dir / filename, "w", encoding="utf-8") as f:
            f.write("\n".join(blob))


if __name__ == "__main__":
    main()
