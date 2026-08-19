"""Build Shorts-style captions: short lines, 1080x1920 ASS (not oversized SRT)."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

# Keep captions small so the speaker stays visible.
MAX_WORDS_PER_CUE = 4
MAX_CUE_SECONDS = 2.0


def ass_time(seconds):
    seconds = max(0.0, float(seconds))
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hrs}:{mins:02d}:{secs:05.2f}"


def split_words(text):
    return [w for w in (text or "").replace("\n", " ").split() if w]


def cue_lines(words):
    if len(words) <= 3:
        return [" ".join(words)]
    mid = (len(words) + 1) // 2
    return [" ".join(words[:mid]), " ".join(words[mid:])]


def split_cues(text, start, end):
    words = split_words(text)
    if not words:
        return []
    duration = max(0.12, end - start)
    chunks = []
    i = 0
    n = len(words)
    while i < n:
        take = min(MAX_WORDS_PER_CUE, n - i)
        piece = words[i : i + take]
        t0 = start + duration * i / n
        t1 = start + duration * (i + take) / n
        if t1 - t0 > MAX_CUE_SECONDS and take > 2:
            take = max(2, take - 1)
            piece = words[i : i + take]
            t1 = start + duration * (i + take) / n
        chunks.append((t0, t1, piece))
        i += take
    return chunks


def ass_header():
    return """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,30,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0.4,0,1,3.5,1,2,90,90,165,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def create_ass(segments, clip_start, clip_end, output_file):
    lines = [ass_header()]
    for segment in segments:
        if segment["end"] < clip_start:
            continue
        if segment["start"] > clip_end:
            break
        start = max(float(segment["start"]), clip_start)
        end = min(float(segment["end"]), clip_end)
        if end <= start:
            continue
        rel_start = start - clip_start
        rel_end = end - clip_start
        for t0, t1, words in split_cues(segment.get("text", ""), rel_start, rel_end):
            if t1 <= t0 or not words:
                continue
            text = r"\N".join(cue_lines(words)).replace("{", "(").replace("}", ")")
            lines.append(
                f"Dialogue: 0,{ass_time(t0)},{ass_time(t1)},Default,,0,0,0,,{{\\bord4\\shad1}}{text}\n"
            )
    output_file.write_text("".join(lines), encoding="utf-8")


def main():
    transcript_file = PROJECT_ROOT / "output" / "transcript.json"
    clips_file = PROJECT_ROOT / "output" / "clips.json"

    with open(transcript_file, "r", encoding="utf-8") as f:
        transcript = json.load(f)
    with open(clips_file, "r", encoding="utf-8") as f:
        clips = json.load(f)

    subtitle_dir = PROJECT_ROOT / "output" / "subtitles"
    subtitle_dir.mkdir(exist_ok=True)

    for i, clip in enumerate(clips["clips"], start=1):
        output_file = subtitle_dir / f"short_{i}.ass"
        create_ass(transcript["segments"], clip["start"], clip["end"], output_file)
        print(f"Created {output_file}")


if __name__ == "__main__":
    main()
