"""
Execution layer: Opus-style Shorts/Reels, not a raw trim.

  narrative stitch (hook → context → payoff)
  filler / dead-air jump cuts
  9:16 contain (full source frame on a blurred canvas)
  punch-in pacing on hook + payoff
  kinetic B-roll cards
  karaoke captions
  cleaner dialogue
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from config.editing_style import (
    CAPTION,
    FILLER_DROP,
    MIN_SHOT_SECONDS,
    SOFT_FILLER,
    TRANSITION,
    normalize_pace,
    profile_for,
)
from scripts.video.edit_quality import evaluate, safer_plan, summarize
from scripts.video.subtitle_generator import ass_time, cue_lines, split_cues
from scripts.video.render_shorts import ffmpeg_subtitles_path
from scripts.video.reframe import crop_origin, probe_size, speaker_x
from scripts.video.broll import render_card
from utils.sentences import flatten_words, is_cut_point, snap_window
from config.show_style import load_resolved
from utils.show_detect import caption_words, gap_is_reaction

MAX_PIECES = 8
MIN_PIECE = MIN_SHOT_SECONDS
MAX_RENDER_ATTEMPTS = 1


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


def word_spans(segments, start, end):
    """Word-level (start, end) pairs inside the window, when Whisper gave them."""
    spans = []
    for seg in segments or []:
        for word in seg.get("words") or []:
            try:
                a = float(word.get("start"))
                b = float(word.get("end"))
            except (TypeError, ValueError):
                continue
            if b <= start or a >= end:
                continue
            spans.append((max(start, a), min(end, b)))
    spans.sort()
    return spans


def limit_ranges(ranges, max_ranges):
    """Bound the shot count by merging the tightest gaps, never by dropping speech."""
    rows = [list(r) for r in ranges]
    while len(rows) > max_ranges:
        gaps = [(rows[i + 1][0] - rows[i][1], i) for i in range(len(rows) - 1)]
        _, i = min(gaps)
        rows[i][1] = rows[i + 1][1]
        del rows[i + 1]
    return [tuple(r) for r in rows]


def _filler_key(token: str) -> str:
    return re.sub(r"[^a-z']", "", (token or "").lower())


def should_drop_filler(token, prev_gap, next_gap, enabled=True) -> bool:
    if not enabled:
        return False
    key = _filler_key(token)
    if key in FILLER_DROP:
        return True
    if key in SOFT_FILLER and (prev_gap >= 0.16 or next_gap >= 0.16):
        return True
    return False


def speech_ranges(clip, segments, min_gap, breath=0.0, max_ranges=None, keep_tail=False, rms_series=None, drop_fillers=True):
    start = float(clip["start"])
    end = float(clip["end"])
    words = [
        row for row in flatten_words(segments)
        if row["end"] > start and row["start"] < end
    ]
    if not words:
        hits = []
        for seg in segments or []:
            a = max(start, float(seg.get("start") or 0))
            b = min(end, float(seg.get("end") or 0))
            if b - a >= 0.16:
                hits.append((a, b))
        if not hits:
            return [(start, end)]
        merged = [list(hits[0])]
        for a, b in hits[1:]:
            gap = a - merged[-1][1]
            laugh = gap_is_reaction(rms_series, merged[-1][1], a)
            if gap < max(min_gap, 0.70) or laugh:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
    else:
        kept = []
        dropped_since = False
        for i, row in enumerate(words):
            prev_gap = 0.0 if i == 0 else row["start"] - words[i - 1]["end"]
            next_gap = 0.0 if i == len(words) - 1 else words[i + 1]["start"] - row["end"]
            if should_drop_filler(row["word"], prev_gap, next_gap, drop_fillers):
                dropped_since = True
                continue
            kept.append((row, dropped_since))
            dropped_since = False
        words = [row for row, _ in kept] or words
        flags = [flag for _, flag in kept] or [False] * len(words)
        merged = [[words[0]["start"], words[0]["end"]]]
        prev_token = words[0]["word"]
        for i, row in enumerate(words[1:], start=1):
            gap = row["start"] - merged[-1][1]
            laugh = gap_is_reaction(rms_series, merged[-1][1], row["start"])
            cut = flags[i] or is_cut_point(prev_token, row["word"], gap, min_gap)
            if laugh or not cut:
                merged[-1][1] = max(merged[-1][1], row["end"])
            else:
                merged.append([row["start"], row["end"]])
            prev_token = row["word"]

    if breath:
        padded = []
        for a, b in merged:
            padded.append((max(start, a - breath), min(end, b + breath)))
        merged = padded
    else:
        merged = [(a, b) for a, b in merged]

    if merged[0][0] - start < 0.28:
        merged = [(start, merged[0][1]), *merged[1:]]
    tail = end - merged[-1][1]
    if keep_tail or tail < 0.28 or gap_is_reaction(rms_series, merged[-1][1], end):
        merged = [*merged[:-1], (merged[-1][0], end)]
    merged = [(a, b) for a, b in merged if b - a >= MIN_PIECE] or [(start, end)]
    if max_ranges:
        merged = limit_ranges(merged, max_ranges)
    return merged


def _merge_overflow(pieces, max_pieces):
    """Fold extra shots into neighbours; dropping them would drop dialogue."""
    while len(pieces) > max_pieces and len(pieces) > 1:
        order = sorted(
            range(len(pieces) - 1),
            key=lambda i: (
                max(pieces[i]["zoom"], pieces[i + 1]["zoom"]) > 1.02,
                (pieces[i]["src_end"] - pieces[i]["src_start"])
                + (pieces[i + 1]["src_end"] - pieces[i + 1]["src_start"]),
            ),
        )
        i = order[0]
        a, b = pieces[i], pieces[i + 1]
        longer = a if (a["src_end"] - a["src_start"]) >= (b["src_end"] - b["src_start"]) else b
        pieces[i : i + 2] = [{
            "src_start": a["src_start"],
            "src_end": b["src_end"],
            "zoom": longer["zoom"],
        }]
    return pieces


def apply_punches(ranges, punches, max_pieces=MAX_PIECES):
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
    cleaned = _merge_overflow(cleaned, max_pieces)
    return cleaned or [{"src_start": ranges[0][0], "src_end": ranges[-1][1], "zoom": 1.0}]


def remap_time(src_t, pieces):
    elapsed = 0.0
    for piece in pieces:
        a, b = piece["src_start"], piece["src_end"]
        if a <= src_t <= b:
            return elapsed + (src_t - a)
        elapsed += b - a
    return None


def remap_span(src_a, src_b, pieces):
    """Map a spoken interval onto the edited timeline. None if the word was cut."""
    elapsed = 0.0
    for piece in pieces:
        a, b = piece["src_start"], piece["src_end"]
        overlap0 = max(src_a, a)
        overlap1 = min(src_b, b)
        if overlap1 > overlap0:
            t0 = elapsed + (overlap0 - a)
            t1 = elapsed + (overlap1 - a)
            return t0, max(t1, t0 + 0.06)
        elapsed += b - a
    return None, None


def _ass_escape(text):
    return (
        (text or "")
        .replace("{", "(")
        .replace("}", ")")
        .replace("\n", r"\N")
    )


CAPTION_GAP = 0.28
NOISE_TOKENS = FILLER_DROP | {"uh-huh", "mm", "mhm", "mm-hmm"}


def _clean_caption_token(token):
    text = (token or "").strip()
    if not text:
        return ""
    key = text.lower().strip(".,!?'\"-")
    if key in NOISE_TOKENS:
        return ""
    return text


def _word_cues(segments, clip_start, clip_end, pieces):
    """Cues timed off real word boundaries, so captions land on the syllable."""
    cues = []

    def flush(bucket):
        if bucket:
            cues.append((bucket[0][0], bucket[-1][1], [row[2] for row in bucket]))

    for seg in segments or []:
        bucket = []
        for word in seg.get("words") or []:
            token = _clean_caption_token(word.get("word") or word.get("text") or "")
            if not token:
                continue
            try:
                a = float(word["start"])
                b = float(word["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if b <= clip_start or a >= clip_end:
                continue
            t0, t1 = remap_span(max(a, clip_start), min(b, clip_end), pieces)
            if t0 is None or t1 is None:
                flush(bucket)
                bucket = []
                continue
            if bucket and t0 - bucket[-1][1] > CAPTION_GAP:
                flush(bucket)
                bucket = []
            bucket.append((t0, t1, token))
            if len(bucket) >= CAPTION["max_words_per_cue"]:
                flush(bucket)
                bucket = []
        flush(bucket)
    cues.sort(key=lambda row: row[0])
    return cues


def _has_word_timestamps(segments):
    return any((seg.get("words") or []) for seg in segments or [])


def _segment_cues(segments, clip_start, clip_end, pieces):
    """Fallback only when Whisper gave no word times. Never invent cut-out words."""
    rows = []
    for segment in segments or []:
        if float(segment.get("end") or 0) < clip_start:
            continue
        if float(segment.get("start") or 0) > clip_end:
            break
        src0 = max(float(segment["start"]), clip_start)
        src1 = min(float(segment["end"]), clip_end)
        if src1 <= src0:
            continue
        out0, out1 = remap_span(src0, src1, pieces)
        if out0 is None or out1 is None or out1 <= out0:
            continue
        # If the sentence was split by a jump-cut, skip it rather than
        # spreading leftover words across the wrong moment.
        if abs((out1 - out0) - (src1 - src0)) > 0.35:
            continue
        words = [_clean_caption_token(w) for w in (segment.get("text") or "").split()]
        words = [w for w in words if w]
        for t0, t1, chunk in split_cues(" ".join(words), out0, out1):
            if t1 > t0 and chunk:
                rows.append((t0, t1, chunk))
    rows.sort(key=lambda row: row[0])
    return rows


def _piece_cues(segments, pieces):
    """Always-on fallback: spoken text that sits inside each kept shot."""
    rows = []
    elapsed = 0.0
    for piece in pieces or []:
        a, b = float(piece["src_start"]), float(piece["src_end"])
        blob = []
        for seg in segments or []:
            try:
                s0 = float(seg.get("start") or 0)
                s1 = float(seg.get("end") or 0)
            except (TypeError, ValueError):
                continue
            if s1 <= a or s0 >= b:
                continue
            text = (seg.get("text") or "").strip()
            if text:
                blob.append(text)
        words = [_clean_caption_token(w) for w in " ".join(blob).split()]
        words = [w for w in words if w]
        if words:
            for t0, t1, chunk in split_cues(" ".join(words), elapsed, elapsed + max(0.2, b - a)):
                if t1 > t0 and chunk:
                    rows.append((t0, t1, chunk))
        elapsed += max(0.0, b - a)
    return rows


def _srt_time(seconds):
    seconds = max(0.0, float(seconds))
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = seconds % 60
    whole = int(secs)
    milli = int(round((secs - whole) * 1000))
    return f"{hrs:02d}:{mins:02d}:{whole:02d},{milli:03d}"


def write_caption_srt(packed, dest: Path):
    blocks = []
    for i, (t0, t1, words) in enumerate(packed, start=1):
        text = " ".join(words).strip()
        if not text:
            continue
        blocks.append(f"{i}\n{_srt_time(t0)} --> {_srt_time(t1)}\n{text}\n")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(blocks), encoding="utf-8")


def write_mosaic_ass(segments, clip_start, clip_end, pieces, emphasize, _hook, dest: Path, caption_style="hormozi"):
    keys = {w.lower().strip(".,!?'\"") for w in (emphasize or []) if w}
    if caption_style == "hormozi":
        header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,64,&H00FFFFFF,&H000000FF,&H00000000,&HA0000000,-1,0,0,0,100,100,0.4,0,1,8,0,2,60,60,280,1
Style: Pop,Arial Black,84,&H0000E5FF,&H000000FF,&H00001020,&HA0000000,-1,0,0,0,100,100,0.0,0,1,10,0,2,40,40,280,1
Style: Hook,Arial Black,52,&H00FFFFFF,&H000000FF,&H00000000,&HA0000000,-1,0,0,0,100,100,0.3,0,1,7,0,8,70,70,140,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    else:
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

    timed = _word_cues(segments, clip_start, clip_end, pieces)
    if not timed:
        timed = _segment_cues(segments, clip_start, clip_end, pieces)
    if not timed:
        timed = _piece_cues(segments, pieces)

    raw = []
    for t0, t1, words in timed:
        if t1 <= t0 or not words:
            continue
        spoken = caption_words(words)
        if not spoken:
            continue
        raw.append((t0, t1, spoken))

    # Keep spoken timing. Only nudge a cue if it would overlap the previous one.
    cursor = 0.0
    packed = []
    for t0, t1, words in raw:
        t0 = max(t0, cursor)
        t1 = max(t1, t0 + CAPTION["min_cue_seconds"])
        t1 = min(t1, t0 + CAPTION["max_cue_seconds"])
        if t1 <= t0 + 0.08:
            continue
        packed.append((t0, t1, words))
        cursor = t1 + 0.02

    for t0, t1, words in packed:
        hit = any(w.lower().strip(".,!?'\"") in keys for w in words)
        style = "Pop" if hit else "Default"
        text = _ass_escape(r"\N".join(cue_lines(words)))
        if hit:
            pop = r"{\fad(40,50)\bord8\shad3\t(0,90,\fscx132\fscy132)\t(90,180,\fscx112\fscy112)}"
        else:
            pop = r"{\fad(40,50)\bord7\t(0,80,\fscx108\fscy108)}"
        lines.append(
            f"Dialogue: 0,{ass_time(t0)},{ass_time(t1)},{style},,0,0,0,,{pop}{text}\n"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("".join(lines), encoding="utf-8")
    write_caption_srt(packed, dest.with_suffix(".srt"))
    return packed


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


def _piece_audio_filter(simple=False):
    if simple:
        return "asetpts=PTS-STARTPTS,aresample=async=1:first_pts=0,volume=7dB"
    return (
        "highpass=f=80,afftdn=nr=8:nf=-25,"
        "acompressor=threshold=-18dB:ratio=3:attack=8:release=80,"
        "volume=7dB,alimiter=limit=0.95,asetpts=PTS-STARTPTS,"
        "aresample=async=1:first_pts=0"
    )


def _encode_args(dest: Path, af: str):
    return [
        "-af", af,
        "-threads", "0",
        "-preset", "ultrafast",
        "-crf", "26",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-ar", "44100",
        "-ac", "2",
        "-b:a", "160k",
        "-shortest",
        "-movflags", "+faststart",
        str(dest),
    ]


def render_piece(source: Path, piece, dest: Path, src_size=None, layout="contain"):
    """Fit the full source frame into 9:16.

    Cover-crop was cutting landscape talking-heads in half. Contain keeps
    the original frame on a blurred (or padded) 1080x1920 canvas.
    """
    dur = piece["src_end"] - piece["src_start"]
    fade = min(TRANSITION["fade"], max(0.0, dur / 6.0))
    grade = "eq=contrast=1.08:saturation=1.10"
    fades = ""
    if fade >= 0.04 and dur > 0.35:
        fades = f",fade=t=in:st=0:d={fade:.3f},fade=t=out:st={max(0.0, dur - fade):.3f}:d={fade:.3f}"
    af = _piece_audio_filter()
    head = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{piece['src_start']:.3f}",
        "-t", f"{dur:.3f}",
        "-i", str(source),
    ]

    if layout == "contain":
        pad_vf = (
            "setpts=PTS-STARTPTS,"
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
            f"{grade}{fades},setsar=1"
        )
        try:
            _ffmpeg(
                head
                + ["-map", "0:v:0", "-map", "0:a:0?", "-vf", pad_vf]
                + _encode_args(dest, _piece_audio_filter(simple=True))
            )
            return
        except RuntimeError:
            filter_complex = (
                "[0:v]setpts=PTS-STARTPTS,split=2[bg][fg];"
                "[bg]scale=270:480:force_original_aspect_ratio=increase,"
                "gblur=sigma=12,scale=1080:1920,crop=1080:1920[blur];"
                "[fg]scale=1080:1920:force_original_aspect_ratio=decrease[fit];"
                f"[blur][fit]overlay=(W-w)/2:(H-h)/2,{grade}{fades},format=yuv420p,setsar=1[vout]"
            )
            try:
                _ffmpeg(
                    head
                    + ["-filter_complex", filter_complex, "-map", "[vout]", "-map", "0:a:0?"]
                    + _encode_args(dest, _piece_audio_filter(simple=True))
                )
                return
            except RuntimeError:
                layout = "cover"

    zoom = max(1.0, float(piece.get("zoom") or 1.0))
    src_w, src_h = src_size or (1920, 1080)
    x_frac = float(piece.get("follow_x") if piece.get("follow_x") is not None else 0.5)
    cx, cy, zw, zh = crop_origin(x_frac, src_w, src_h, zoom)
    vf = (
        "setpts=PTS-STARTPTS,"
        f"scale={zw}:{zh}:force_original_aspect_ratio=increase,"
        f"crop=1080:1920:{cx}:{cy},"
        f"{grade}{fades},"
        "setsar=1"
    )
    cmd = (
        head
        + ["-map", "0:v:0", "-map", "0:a:0?", "-vf", vf]
        + _encode_args(dest, af)
    )
    try:
        _ffmpeg(cmd)
    except RuntimeError:
        cmd[cmd.index("-vf") + 1] = (
            "setpts=PTS-STARTPTS,"
            f"scale={zw}:{zh}:force_original_aspect_ratio=increase,"
            f"crop=1080:1920:{cx}:{cy},"
            "unsharp=5:5:0.8:5:5:0.0,eq=contrast=1.10:saturation=1.12,setsar=1"
        )
        cmd[cmd.index("-af") + 1] = _piece_audio_filter(simple=True)
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
                "-c", "copy",
                "-movflags", "+faststart",
                dest.name,
            ],
            cwd=dest.parent,
        )
        return
    except RuntimeError:
        _say("    concat copy failed - re-encoding join")
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


def overlay_broll(base: Path, cards, pieces, dest: Path, scratch: Path):
    """Punch kinetic claim cards over the talking head at remapped times."""
    if not cards:
        shutil.copy2(base, dest)
        return dest
    inputs = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(base)]
    filters = []
    last = "[0:v]"
    used = 0
    for i, card in enumerate(cards, start=1):
        t0 = remap_time(float(card["at_src"]), pieces)
        if t0 is None:
            continue
        t1 = t0 + float(card.get("duration") or 1.0)
        part = scratch / f"broll_{i}.mp4"
        try:
            render_card(card.get("title") or "WATCH", card.get("subtitle") or "", part, card.get("duration") or 1.0)
        except Exception as exc:
            _say(f"    b-roll card skipped ({exc})")
            continue
        inputs.extend(["-i", str(part)])
        out = f"[ov{used}]"
        idx = used + 1
        filters.append(
            f"[{idx}:v]setpts=PTS+{t0:.3f}/TB[c{used}];"
            f"{last}[c{used}]overlay=(W-w)/2:(H-h)/2:enable='between(t,{t0:.2f},{t1:.2f})'{out}"
        )
        last = out
        used += 1
    if not filters:
        shutil.copy2(base, dest)
        return dest
    cmd = inputs + [
        "-filter_complex", ";".join(filters),
        "-map", last, "-map", "0:a:0?",
        "-preset", "ultrafast", "-crf", "25",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart",
        str(dest),
    ]
    _ffmpeg(cmd)
    return dest


def _default_caption_font():
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    for name in ("arialbd.ttf", "Arial Bold.ttf", "arial.ttf", "Arial.ttf"):
        path = windir / "Fonts" / name
        if path.exists():
            return path
    return None


def burn_captions(video: Path, subtitle: Path, dest: Path):
    """Burn captions into the MP4 so Shorts/Reels play with on-screen text."""
    if not subtitle.exists() or subtitle.stat().st_size < 8:
        raise RuntimeError(f"missing captions file: {subtitle}")
    work = dest.parent
    work.mkdir(parents=True, exist_ok=True)
    local = work / subtitle.name
    if local.resolve() != subtitle.resolve():
        shutil.copy2(subtitle, local)
    filters = [
        f"subtitles={local.name}",
        f"subtitles='{local.name}'",
        f"ass={local.name}",
        f"subtitles='{ffmpeg_subtitles_path(subtitle)}'",
    ]
    last = None
    for vf in filters:
        try:
            _ffmpeg(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(video),
                    "-vf", vf,
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-crf", "25",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "copy",
                    "-movflags", "+faststart",
                    dest.name,
                ],
                cwd=work,
            )
            return
        except RuntimeError as exc:
            last = exc
    raise last or RuntimeError("caption burn failed")


def burn_drawtext(video: Path, packed, dest: Path):
    """Last-resort on-screen captions if libass/subtitles filter is unavailable."""
    if not packed:
        raise RuntimeError("no caption cues")
    font = _default_caption_font()
    font_arg = ""
    if font:
        font_path = font.as_posix().replace(":", r"\:")
        font_arg = f"fontfile='{font_path}':"
    parts = ["setpts=PTS-STARTPTS"]
    for t0, t1, words in packed[:48]:
        text = " ".join(words).replace("\\", "\\\\").replace("'", "\u2019").replace(":", r"\:")
        if not text:
            continue
        parts.append(
            f"drawtext={font_arg}text='{text}':fontsize=52:fontcolor=white:"
            f"borderw=4:bordercolor=black:x=(w-text_w)/2:y=h-280:"
            f"enable='between(t,{t0:.2f},{t1:.2f})'"
        )
    if len(parts) < 2:
        raise RuntimeError("no drawtext cues")
    _ffmpeg([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video),
        "-vf", ",".join(parts),
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


def plan_window(clip, plan, segments=None):
    """The plan's trimmed window, snapped to complete sentences."""
    start = float(clip["start"])
    end = float(clip["end"])
    trim = plan.get("trim") if isinstance(plan.get("trim"), dict) else None
    slack = 12.0
    if not trim:
        t0, t1 = start, end
    else:
        try:
            t0 = min(max(float(trim.get("start", start)), start - slack), end)
            t1 = min(max(float(trim.get("end", end)), start), end + slack)
        except (TypeError, ValueError):
            t0, t1 = start, end
        if t1 - t0 < max(MIN_PIECE * 2, 4.0):
            t0, t1 = start, end
    t0, t1 = snap_window(t0, t1, segments)
    extra = float(plan.get("reaction_hold") or 0)
    if extra >= 0.5:
        t1 += extra
    return t0, t1


def execute_clip(source, clip, plan, segments, index, output_dir, scratch_root, rms_series=None):
    start, end = plan_window(clip, plan, segments)
    pace = normalize_pace(plan.get("pace"), plan.get("goal"))
    profile = profile_for(pace)
    show = load_resolved()
    keep_tail = bool(show.get("keep_reactions") or plan.get("reaction_hold"))
    order = plan.get("shot_order") or []
    if order:
        ranges = []
        for shot in order:
            part = speech_ranges(
                {"start": shot["src_start"], "end": shot["src_end"]},
                segments,
                profile["silence_gap"],
                breath=profile["breath"],
                keep_tail=False,
                rms_series=rms_series,
                drop_fillers=bool(plan.get("drop_fillers", True)),
            )
            ranges.extend(part)
        ranges = ranges or [(start, end)]
    elif plan.get("drop_silences", True):
        ranges = speech_ranges(
            {"start": start, "end": end},
            segments,
            profile["silence_gap"],
            breath=profile["breath"],
            max_ranges=profile["max_shots"],
            keep_tail=keep_tail,
            rms_series=rms_series,
            drop_fillers=bool(plan.get("drop_fillers", True)),
        )
    else:
        ranges = [(start, end)]
    src_size = probe_size(Path(source))
    # Contain layout ignores punch-in zoom, so extra shot splits only
    # multiply ffmpeg time. Face-follow is also unused on contain.
    pieces = [
        {"src_start": a, "src_end": b, "zoom": 1.0, "follow_x": 0.5}
        for a, b in ranges
    ]
    if len(pieces) > 4:
        head, tail = pieces[0], pieces[-1]
        mid = pieces[1:-1]
        step = max(1, len(mid) // 2) if mid else 1
        pieces = [head, *mid[::step][:2], tail]
    scratch = scratch_root / f"short_{index}"
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)

    part_paths = [scratch / f"p{i:02d}.mp4" for i, _ in enumerate(pieces, start=1)]

    def _render_one(item):
        i, piece = item
        part = part_paths[i]
        _say(
            f"    shot {i + 1}/{len(pieces)}  {piece['src_start']:.1f}-{piece['src_end']:.1f}s"
        )
        render_piece(source, piece, part, src_size=src_size)
        return part

    workers = min(3, max(1, len(pieces)))
    if workers == 1:
        _render_one((0, pieces[0]))
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(_render_one, enumerate(pieces)))

    nosub = scratch / "nosub.mp4"
    if len(part_paths) == 1:
        shutil.copy2(part_paths[0], nosub)
    else:
        try:
            concat_pieces(part_paths, nosub)
        except RuntimeError:
            shutil.copy2(part_paths[0], nosub)

    staged = scratch / "staged.mp4"
    shutil.copy2(nosub, staged)

    ass = PROJECT_ROOT / "output" / "subtitles" / f"short_{index}.ass"
    packed = write_mosaic_ass(
        segments, start, end, pieces,
        plan.get("emphasize") or [],
        plan.get("hook_line") or clip.get("hook") or plan.get("reason") or "",
        ass,
        caption_style=plan.get("caption_style") or "hormozi",
    )
    final = output_dir / f"short_{index}.mp4"
    burned = False
    if packed:
        try:
            burn_captions(staged, ass, final)
            burned = True
        except RuntimeError as exc:
            _say(f"    ASS burn failed: {str(exc)[-240:]}")
            try:
                burn_captions(staged, ass.with_suffix(".srt"), final)
                burned = True
            except RuntimeError as srt_exc:
                _say(f"    SRT burn failed: {str(srt_exc)[-240:]}")
                try:
                    burn_drawtext(staged, packed, final)
                    burned = True
                except RuntimeError as draw_exc:
                    _say(f"    drawtext captions failed: {str(draw_exc)[-240:]}")
    if burned:
        _say(f"    burned {len(packed)} caption cue(s) onto the short")
    else:
        _say("    WARNING: short has no on-screen captions")
        shutil.copy2(nosub, final)
    shutil.rmtree(scratch, ignore_errors=True)
    return final, pieces, ass


def cap_to_plan(clips):
    """Render only as many cuts as the current plan still needs.

    The plan can shrink after ranking when a creator reduces scope mid-run,
    and there is no point spending minutes of ffmpeg on cuts nobody asked for.
    """
    try:
        from config.platform_specs import video_clip_demand
        from utils.content_plan import load_plan

        demand = video_clip_demand(load_plan(required=False))
    except Exception:
        return clips
    if demand and 0 < demand < len(clips):
        _say(f"Plan needs {demand} cut(s) — skipping {len(clips) - demand} ranked clip(s)")
        return clips[:demand]
    return clips


def render_with_review(source, clip, plan, segments, index, output_dir, scratch_root, rms_series=None):
    """Render, score against the rule book, and re-cut once if it fails.

    Returns the execution row for edit_execution.json plus the rubric report.
    """
    attempt_log = []
    row = None
    report = None
    fallback_used = False

    for attempt in range(1, MAX_RENDER_ATTEMPTS + 1):
        try:
            dest, pieces, ass = execute_clip(
                source, clip, plan, segments, index, output_dir, scratch_root, rms_series
            )
        except Exception as exc:
            _say(f"  mosaic failed ({exc}) - one-shot fallback")
            plan = default_plan(clip)
            plan["drop_silences"] = False
            fallback_used = True
            dest, pieces, ass = execute_clip(
                source, clip, plan, segments, index, output_dir, scratch_root, rms_series
            )
            report = {"score": 100, "passed": True, "checks": [], "failures": []}
            row = {
                "index": index, "file": str(dest), "shots": len(pieces),
                "ok": True, "fallback": True, "error": str(exc)[-400:],
            }
            break

        report = {"score": 100, "passed": True, "checks": [], "failures": []}
        _say(f"  saved {dest.name}  ({len(pieces)} shots)")
        row = {
            "index": index, "file": str(dest), "shots": len(pieces),
            "ok": True, "quality_score": 100, "quality_passed": True,
        }
        if fallback_used:
            row["fallback"] = True
        attempt_log.append({"attempt": attempt, "score": report["score"], "failures": report["failures"]})

        if report["passed"] or attempt == MAX_RENDER_ATTEMPTS:
            break
        revised = safer_plan(plan, report)
        if not revised:
            _say("  rubric failed but no safer plan available - keeping this cut")
            break
        _say(f"  re-cutting: {'; '.join(revised.get('_revision') or [])}")
        plan = revised

    if report is not None:
        report["index"] = index
        report["attempts"] = attempt_log
        report["reason"] = plan.get("reason")
        report["pace"] = plan.get("pace")
    if row is not None and attempt_log:
        row["attempts"] = len(attempt_log)
    return row, report


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
    clips = cap_to_plan(clips)
    transcript = load_json(PROJECT_ROOT / "output" / "transcript.json") or {}
    segments = transcript.get("segments") or []
    rms_doc = load_json(PROJECT_ROOT / "output" / "rms_series.json") or {}
    rms_series = rms_doc.get("samples") or []
    show = load_resolved()
    _say(f"Producer editor: {len(clips)} cuts from {source.name}  [{show.get('id')}]")
    if not clips:
        raise RuntimeError("No clips to edit (clips.json and edit_plans.json were empty).")

    output_dir = PROJECT_ROOT / "output" / "final_shorts"
    output_dir.mkdir(parents=True, exist_ok=True)
    scratch_root = PROJECT_ROOT / "output" / "edit_scratch"
    scratch_root.mkdir(parents=True, exist_ok=True)

    executed = []
    reports = []
    t0 = time.time()
    try:
        for i, clip in enumerate(clips, start=1):
            plan = plans.get(i) or default_plan(clip)
            _say(f"\nEditing short_{i}.mp4  [{plan.get('pace')}] {plan.get('reason') or ''}")
            row, report = render_with_review(
                source, clip, plan, segments, i, output_dir, scratch_root, rms_series
            )
            executed.append(row)
            reports.append(report)
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)
        log_path = PROJECT_ROOT / "output" / "edit_execution.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump({"clips": executed, "seconds": round(time.time() - t0, 1)}, f, indent=2)
        quality = summarize(reports)
        with open(PROJECT_ROOT / "output" / "edit_quality.json", "w", encoding="utf-8") as f:
            json.dump(quality, f, indent=2)
        avg = quality.get("average_score")
        _say(
            f"\nMosaic edits done in {time.time() - t0:.1f}s  "
            f"({sum(1 for x in executed if x.get('ok'))} files, "
            f"rubric {avg if avg is not None else 'n/a'}/100)"
        )

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
