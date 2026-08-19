"""
Execution layer: Mosaic-style Shorts/Reels, not a raw trim.

  jump cuts (drop dead air)
  9:16 reframe
  punch-in zooms on hook + payoff
  hook title for the first beat
  keyword-pop captions in the TikTok safe area
  louder, tighter dialogue
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from scripts.video.subtitle_generator import ass_time, cue_lines, split_cues
from scripts.video.render_shorts import ffmpeg_subtitles_path

MAX_PIECES = 8
MIN_PIECE = 0.35


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _say(msg):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(str(msg).encode("ascii", "replace").decode("ascii"), flush=True)


def load_clips_and_plans():
    clips_doc = load_json(PROJECT_ROOT / "output" / "clips.json") or {}
    clips = clips_doc.get("clips") if isinstance(clips_doc, dict) else None
    if not clips and isinstance(clips_doc, list):
        clips = clips_doc
    clips = clips or []

    plans_doc = load_json(PROJECT_ROOT / "output" / "edit_plans.json") or {}
    plan_rows = plans_doc.get("clips") or []
    plans = {int(item.get("index") or i + 1): item for i, item in enumerate(plan_rows)}

    if not clips and plan_rows:
        _say(f"clips.json empty - recovering {len(plan_rows)} windows from edit_plans.json")
        clips = [
            {
                "start": row.get("start"),
                "end": row.get("end"),
                "hook": row.get("reason") or "",
                "chunk_id": row.get("chunk_id"),
            }
            for row in plan_rows
        ]
    if not clips:
        analysis = load_json(PROJECT_ROOT / "output" / "analysis.json") or {}
        clips = (analysis.get("results") or [])[:5]
        if clips:
            _say(f"clips.json empty - using {len(clips)} analysis windows")
    return clips, plans


def speech_ranges(clip, segments, min_gap):
    start = float(clip["start"])
    end = float(clip["end"])
    hits = []
    for seg in segments or []:
        a = max(start, float(seg.get("start") or 0))
        b = min(end, float(seg.get("end") or 0))
        if b - a >= 0.16:
            hits.append((a, b))
    if not hits:
        return [(start, end)]
    hits.sort()
    merged = [hits[0]]
    for a, b in hits[1:]:
        if a - merged[-1][1] < min_gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    if merged[0][0] - start < 0.28:
        merged[0] = (start, merged[0][1])
    if end - merged[-1][1] < 0.28:
        merged[-1] = (merged[-1][0], end)
    return merged


def apply_punches(ranges, punches):
    pieces = [{"src_start": a, "src_end": b, "zoom": 1.0} for a, b in ranges]
    for punch in punches or []:
        at = float(punch["at_src"])
        dur = float(punch.get("duration") or 0.75)
        zoom = float(punch.get("zoom") or 1.2)
        p0, p1 = at, at + dur
        next_pieces = []
        for piece in pieces:
            a, b = piece["src_start"], piece["src_end"]
            z0 = piece["zoom"]
            if p1 <= a or p0 >= b:
                next_pieces.append(piece)
                continue
            if p0 > a + 0.16:
                next_pieces.append({"src_start": a, "src_end": p0, "zoom": z0})
            mid0 = max(a, p0)
            mid1 = min(b, p1)
            if mid1 - mid0 >= MIN_PIECE:
                next_pieces.append({"src_start": mid0, "src_end": mid1, "zoom": max(z0, zoom)})
            if p1 < b - 0.16:
                next_pieces.append({"src_start": p1, "src_end": b, "zoom": z0})
        pieces = next_pieces or pieces
    cleaned = []
    for piece in pieces:
        if piece["src_end"] - piece["src_start"] < MIN_PIECE:
            if cleaned:
                cleaned[-1]["src_end"] = piece["src_end"]
            continue
        cleaned.append(piece)
    if len(cleaned) > MAX_PIECES:
        zooms = [p for p in cleaned[1:-1] if p["zoom"] > 1.02]
        keep = [cleaned[0]] + zooms[: MAX_PIECES - 2] + [cleaned[-1]]
        cleaned = keep[:MAX_PIECES]
    return cleaned or [{"src_start": ranges[0][0], "src_end": ranges[-1][1], "zoom": 1.0}]


def remap_time(src_t, pieces):
    elapsed = 0.0
    for piece in pieces:
        a, b = piece["src_start"], piece["src_end"]
        if a <= src_t <= b:
            return elapsed + (src_t - a)
        elapsed += b - a
    return None


def _ass_escape(text):
    return (
        (text or "")
        .replace("{", "(")
        .replace("}", ")")
        .replace("\n", r"\N")
    )


HOOK_HOLD = 1.45
FILLER = {
    "the", "a", "an", "and", "of", "to", "it", "it's", "its", "yeah",
    "uh", "um", "like", "i", "i'm", "im", "oh", "so", "just", "very",
}


def write_mosaic_ass(segments, clip_start, clip_end, pieces, emphasize, hook, dest: Path):
    keys = {w.lower().strip(".,!?'\"") for w in (emphasize or []) if w}
    hook_line = _ass_escape(" ".join((hook or "").split()[:8]))
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H96000000,-1,0,0,0,100,100,0.4,0,1,5,0,2,70,70,240,1
Style: Pop,Arial,64,&H0000F5FF,&H000000FF,&H00000000,&H96000000,-1,0,0,0,100,100,0.2,0,1,6,0,2,60,60,240,1
Style: Hook,Arial,44,&H00FFFFFF,&H000000FF,&H00000000,&H96000000,-1,0,0,0,100,100,0.3,0,1,5,0,8,80,80,110,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    if hook_line:
        lines.append(
            f"Dialogue: 1,0:00:00.00,{ass_time(HOOK_HOLD)},Hook,,0,0,0,,{{\\fad(80,140)\\bord5}}{hook_line}\n"
        )

    raw = []
    for segment in segments or []:
        if float(segment.get("end") or 0) < clip_start:
            continue
        if float(segment.get("start") or 0) > clip_end:
            break
        src0 = max(float(segment["start"]), clip_start)
        src1 = min(float(segment["end"]), clip_end)
        if src1 <= src0:
            continue
        out0 = remap_time(src0, pieces)
        out1 = remap_time(src1 - 0.01, pieces)
        if out0 is None or out1 is None or out1 <= out0:
            continue
        for t0, t1, words in split_cues(segment.get("text", ""), out0, out1):
            if t1 <= t0 or not words:
                continue
            meaningful = [
                w for w in words
                if w.lower().strip(".,!?'\"") not in FILLER
            ]
            if not meaningful:
                continue
            raw.append((t0, t1, words))
    raw.sort(key=lambda row: row[0])

    cursor = HOOK_HOLD if hook_line else 0.0
    packed = []
    for t0, t1, words in raw:
        t0 = max(t0, cursor)
        t1 = max(t1, t0 + 0.45)
        t1 = min(t1, t0 + 2.1)
        if t1 <= t0 + 0.28:
            continue
        packed.append((t0, t1, words))
        cursor = t1

    for t0, t1, words in packed:
        hit = any(w.lower().strip(".,!?'\"") in keys for w in words)
        style = "Pop" if hit else "Default"
        text = _ass_escape(r"\N".join(cue_lines(words)))
        pop = r"{\fad(50,50)\bord5\t(0,120,\fscx108\fscy108)}" if hit else r"{\fad(50,50)\bord5}"
        lines.append(
            f"Dialogue: 0,{ass_time(t0)},{ass_time(t1)},{style},,0,0,0,,{pop}{text}\n"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("".join(lines), encoding="utf-8")


def _ffmpeg(command, cwd=None):
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd) if cwd else str(PROJECT_ROOT),
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(err[-1500:] or f"ffmpeg exit {result.returncode}")


def render_piece(source: Path, piece, dest: Path):
    dur = piece["src_end"] - piece["src_start"]
    zoom = max(1.0, float(piece.get("zoom") or 1.0))
    zw = int(round(1080 * zoom))
    zh = int(round(1920 * zoom))
    grade = (
        "hqdn3d=1.8:1.2:4:4,"
        "unsharp=5:5:0.8:5:5:0.0,"
        "eq=contrast=1.10:saturation=1.12:brightness=0.02,"
        "vignette=PI/6"
    )
    vf = (
        "setpts=PTS-STARTPTS,"
        f"scale={zw}:{zh}:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        f"{grade},"
        "setsar=1"
    )
    af = "highpass=f=70,volume=8dB,alimiter=limit=0.95,asetpts=PTS-STARTPTS,aresample=async=1:first_pts=0"
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{piece['src_start']:.3f}",
        "-t", f"{dur:.3f}",
        "-i", str(source),
        "-map", "0:v:0",
        "-map", "0:a:0?",
        "-vf", vf,
        "-af", af,
        "-preset", "ultrafast",
        "-crf", "25",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-ar", "44100",
        "-ac", "2",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(dest),
    ]
    try:
        _ffmpeg(cmd)
    except RuntimeError:
        cmd[cmd.index("-vf") + 1] = (
            "setpts=PTS-STARTPTS,"
            f"scale={zw}:{zh}:force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            "unsharp=5:5:0.8:5:5:0.0,eq=contrast=1.10:saturation=1.12,setsar=1"
        )
        cmd[cmd.index("-af") + 1] = "asetpts=PTS-STARTPTS,aresample=async=1:first_pts=0,volume=7dB"
        _ffmpeg(cmd)


def concat_pieces(paths, dest: Path):
    listing = dest.parent / "concat.txt"
    listing.write_text("".join(f"file {path.name}\n" for path in paths), encoding="utf-8")
    try:
        _ffmpeg(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "concat", "-safe", "0",
                "-i", listing.name,
                "-preset", "ultrafast",
                "-crf", "25",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-ar", "44100",
                "-ac", "2",
                "-b:a", "192k",
                "-movflags", "+faststart",
                dest.name,
            ],
            cwd=dest.parent,
        )
        return
    except RuntimeError:
        _say("    concat demuxer failed - joining with filter_complex")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for path in paths:
        cmd.extend(["-i", str(path)])
    n = len(paths)
    streams = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(n))
    cmd.extend([
        "-filter_complex", f"{streams}concat=n={n}:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]",
        "-preset", "ultrafast", "-crf", "25",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
        "-movflags", "+faststart",
        str(dest),
    ])
    _ffmpeg(cmd)


def burn_captions(video: Path, ass: Path, dest: Path):
    sub = ffmpeg_subtitles_path(ass)
    _ffmpeg([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video),
        "-vf", f"subtitles='{sub}'",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "25",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(dest),
    ])


def default_plan(clip):
    start = float(clip["start"])
    end = float(clip["end"])
    dur = max(1.0, end - start)
    return {
        "pace": "fast",
        "drop_silences": True,
        "punch_ins": [
            {"at_src": round(start + 0.2, 2), "duration": 0.85, "zoom": 1.22, "why": "hook"},
            {"at_src": round(min(end - 0.9, start + dur * 0.62), 2), "duration": 0.9, "zoom": 1.28, "why": "payoff"},
        ],
        "emphasize": [],
        "reason": "fast Short: hook zoom, jump cuts, payoff zoom",
    }


def execute_clip(source, clip, plan, segments, index, output_dir, scratch_root):
    start = float(clip["start"])
    end = float(clip["end"])
    pace = plan.get("pace") or "fast"
    min_gap = {"fast": 0.22, "medium": 0.4, "hold": 9.0}.get(pace, 0.28)
    ranges = speech_ranges(clip, segments, min_gap)
    if not plan.get("drop_silences", True):
        ranges = [(start, end)]
    punches = plan.get("punch_ins") or default_plan(clip)["punch_ins"]
    pieces = apply_punches(ranges, punches)
    scratch = scratch_root / f"short_{index}"
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)

    part_paths = []
    for i, piece in enumerate(pieces, start=1):
        part = scratch / f"p{i:02d}.mp4"
        _say(
            f"    shot {i}/{len(pieces)}  {piece['src_start']:.1f}-{piece['src_end']:.1f}s  "
            f"zoom {piece['zoom']:.2f}"
        )
        render_piece(source, piece, part)
        part_paths.append(part)

    nosub = scratch / "nosub.mp4"
    if len(part_paths) == 1:
        shutil.copy2(part_paths[0], nosub)
    else:
        try:
            concat_pieces(part_paths, nosub)
        except RuntimeError:
            shutil.copy2(part_paths[0], nosub)

    ass = PROJECT_ROOT / "output" / "subtitles" / f"short_{index}.ass"
    write_mosaic_ass(
        segments, start, end, pieces,
        plan.get("emphasize") or [],
        clip.get("hook") or plan.get("reason") or "",
        ass,
    )
    final = output_dir / f"short_{index}.mp4"
    try:
        burn_captions(nosub, ass, final)
    except RuntimeError:
        shutil.copy2(nosub, final)
    shutil.rmtree(scratch, ignore_errors=True)
    return final, pieces


def run_edits(source: Path):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if not source.is_absolute():
        source = PROJECT_ROOT / source
    source = source.resolve()
    if not source.exists():
        raise FileNotFoundError(source)

    clips, plans = load_clips_and_plans()
    transcript = load_json(PROJECT_ROOT / "output" / "transcript.json") or {}
    segments = transcript.get("segments") or []
    _say(f"Mosaic editor: {len(clips)} cuts from {source.name}")
    if not clips:
        raise RuntimeError("No clips to edit (clips.json and edit_plans.json were empty).")

    output_dir = PROJECT_ROOT / "output" / "final_shorts"
    output_dir.mkdir(parents=True, exist_ok=True)
    scratch_root = PROJECT_ROOT / "output" / "edit_scratch"
    scratch_root.mkdir(parents=True, exist_ok=True)

    executed = []
    t0 = time.time()
    try:
        for i, clip in enumerate(clips, start=1):
            plan = plans.get(i) or default_plan(clip)
            _say(f"\nEditing short_{i}.mp4  [{plan.get('pace')}] {plan.get('reason') or ''}")
            try:
                dest, pieces = execute_clip(
                    source, clip, plan, segments, i, output_dir, scratch_root
                )
                _say(f"  saved {dest.name}  ({len(pieces)} shots)")
                executed.append({"index": i, "file": str(dest), "shots": len(pieces), "ok": True})
            except Exception as exc:
                _say(f"  mosaic failed ({exc}) - one-shot fallback")
                simple = default_plan(clip)
                simple["drop_silences"] = False
                dest, pieces = execute_clip(
                    source, clip, simple, segments, i, output_dir, scratch_root
                )
                executed.append({
                    "index": i, "file": str(dest), "shots": len(pieces),
                    "ok": True, "fallback": True, "error": str(exc)[-400:],
                })
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)
        log_path = PROJECT_ROOT / "output" / "edit_execution.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump({"clips": executed, "seconds": round(time.time() - t0, 1)}, f, indent=2)
        _say(f"\nMosaic edits done in {time.time() - t0:.1f}s  ({sum(1 for x in executed if x.get('ok'))} files)")

    ok_files = list(output_dir.glob("short_*.mp4"))
    if not ok_files:
        raise RuntimeError("Mosaic editor produced no short_*.mp4 files")
    return executed


def main():
    if len(sys.argv) < 2:
        _say("Usage: python scripts/video/edit_executor.py <source.mp4>")
        sys.exit(2)
    run_edits(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
