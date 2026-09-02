"""Append a brand end screen to platform Shorts/Reels after routing.

Deterministic (no AI): brand settings → still card → FFmpeg concat.
Failures leave the original clip in place.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from utils.brand_settings import (  # noqa: E402
    BRAND_DIR,
    display_website,
    load_brand,
    resolve_logo_path,
)
from config.platform_specs import SHORTS_PLATFORM_MAX_SECONDS  # noqa: E402

try:
    from PIL import Image, ImageDraw, ImageFont

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

OUTPUT = PROJECT_ROOT / "output"
SHORTS_DIR = OUTPUT / "final_shorts"
BANK_FILE = OUTPUT / "content_bank.json"
REPORT_FILE = OUTPUT / "end_screen_report.json"
PLATFORM_FOLDERS = ("youtube_shorts", "instagram_reels", "tiktok")

BG = (10, 10, 14)
BG_MID = (22, 18, 32)
ACCENT = (167, 139, 250)
ACCENT_SOFT = (88, 52, 180)
NAME_COLOR = (250, 250, 252)
MUTED = (168, 168, 178)
WEBSITE_COLOR = (250, 250, 252)
WEBSITE_PILL = (99, 58, 198)
DIVIDER = (72, 58, 110)


def _short_tagline(text: str, max_chars: int = 42) -> str:
    """End cards need a short line — not a full poem or paragraph."""
    cleaned = re.sub(r"\s+", " ", (text or "").strip().strip("\"'“”"))
    if not cleaned:
        return ""
    sentence = re.split(r"[.!?…]\s+", cleaned, maxsplit=1)[0].strip()
    candidate = sentence or cleaned
    if len(candidate) <= max_chars:
        return candidate
    words = candidate.split()
    out = []
    for word in words:
        trial = " ".join(out + [word])
        if len(trial) > max_chars - 1:
            break
        out.append(word)
    return (" ".join(out) + "…") if out else candidate[: max_chars - 1] + "…"


def _even(value: int) -> int:
    value = max(2, int(value or 0))
    return value - (value % 2)


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


def probe_video(path: Path) -> dict:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "stream=codec_type,width,height,r_frame_rate",
                "-show_entries", "format=duration",
                "-of", "json", str(path),
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout or "{}")
    except Exception:
        return {}
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    try:
        duration = float((data.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    fps = 30.0
    if video and video.get("r_frame_rate") and "/" in str(video.get("r_frame_rate")):
        num, den = str(video["r_frame_rate"]).split("/", 1)
        try:
            fps = float(num) / float(den or 1)
        except (TypeError, ValueError, ZeroDivisionError):
            fps = 30.0
    return {
        "width": int(video.get("width") or 0) if video else 0,
        "height": int(video.get("height") or 0) if video else 0,
        "duration": duration,
        "fps": fps if 1 <= fps <= 120 else 30.0,
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


def choose_duration(clip_seconds: float, requested: int) -> float | None:
    """Keep the outro from dominating a very short clip."""
    requested = max(2, min(5, int(requested or 3)))
    if clip_seconds < 4:
        return None
    cap = max(2, int(clip_seconds * 0.3))
    # Whole file must stay inside the Shorts limit once the end card is appended.
    room = max(0, int(SHORTS_PLATFORM_MAX_SECONDS - clip_seconds))
    if room < 2:
        return None
    return float(min(requested, cap, room))


def _font(size: int, bold: bool = False):
    if not HAS_PIL:
        return None
    names = (
        ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf")
        if bold
        else ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")
    )
    roots = [
        Path(r"C:\Windows\Fonts"),
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/usr/share/fonts/truetype/liberation"),
        Path("/System/Library/Fonts/Supplemental"),
    ]
    for root in roots:
        for name in names:
            path = root / name
            if path.is_file():
                try:
                    return ImageFont.truetype(str(path), size)
                except OSError:
                    continue
    return ImageFont.load_default()


def _wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    words = [w for w in (text or "").split() if w]
    if not words:
        return []
    lines, bucket = [], []
    for word in words:
        trial = " ".join(bucket + [word])
        width = draw.textlength(trial, font=font) if hasattr(draw, "textlength") else font.getlength(trial)
        if width > max_width and bucket:
            lines.append(" ".join(bucket))
            bucket = [word]
        else:
            bucket.append(word)
    if bucket:
        lines.append(" ".join(bucket))
    return lines[:3]


def _load_logo_rgba(path: Path, max_w: int, max_h: int):
    if HAS_PIL:
        try:
            logo = Image.open(path).convert("RGBA")
        except OSError:
            return None
        resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
        logo.thumbnail((max_w, max_h), resample)
        return logo
    raw = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if raw is None:
        return None
    if raw.ndim == 2:
        raw = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGRA)
    elif raw.shape[2] == 3:
        raw = cv2.cvtColor(raw, cv2.COLOR_BGR2BGRA)
    h, w = raw.shape[:2]
    scale = min(max_w / max(w, 1), max_h / max(h, 1), 1.0)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    return cv2.resize(raw, (nw, nh), interpolation=cv2.INTER_AREA)


def card_copy(brand: dict) -> dict:
    name = (brand.get("brand_name") or "").strip()
    website = display_website(brand.get("website") or "")
    tagline = _short_tagline(brand.get("tagline") or "")
    cta = (brand.get("end_screen_cta") or "").strip()
    template = brand.get("end_screen_template") or "logo_name_website"
    if template not in ("logo_name", "logo_name_website", "logo_cta"):
        template = "logo_name_website"
    secondary = ""
    tertiary = ""
    if template == "logo_name":
        secondary = tagline
    elif template == "logo_cta":
        if cta:
            secondary = cta
        elif website:
            secondary = f"Learn more → {website}"
        else:
            secondary = tagline
    else:
        # Long poems/paragraphs clutter Shorts — keep only a crisp line.
        raw = (brand.get("tagline") or "").strip()
        secondary = tagline if len(raw) <= 90 else ""
        tertiary = website
    return {
        "name": name,
        "secondary": secondary,
        "tertiary": tertiary,
        "template": template,
    }


def _draw_modern_backdrop(width: int, height: int):
    """Soft vertical gradient + vignette for phone Shorts/Reels."""
    img = Image.new("RGB", (width, height), BG)
    pixels = img.load()
    for y in range(height):
        t = y / max(height - 1, 1)
        lift = max(0.0, 1.0 - abs(t - 0.28) * 2.2)
        r = int(BG[0] + (BG_MID[0] - BG[0]) * (0.35 + 0.45 * lift))
        g = int(BG[1] + (BG_MID[1] - BG[1]) * (0.35 + 0.45 * lift))
        b = int(BG[2] + (BG_MID[2] - BG[2]) * (0.45 + 0.55 * lift))
        for x in range(width):
            edge = min(x, width - 1 - x) / max(width * 0.5, 1)
            shade = 0.78 + 0.22 * min(1.0, edge * 1.4)
            pixels[x, y] = (int(r * shade), int(g * shade), int(b * shade))
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    glow_r = int(width * 0.42)
    cx, cy = width // 2, int(height * 0.30)
    for i, alpha in ((glow_r, 28), (int(glow_r * 0.72), 42), (int(glow_r * 0.46), 58)):
        odraw.ellipse((cx - i, cy - i, cx + i, cy + i), fill=(*ACCENT_SOFT, alpha))
    rail = max(3, height // 220)
    odraw.rectangle((0, 0, width, rail), fill=(*ACCENT, 200))
    odraw.rectangle((0, height - rail, width, height), fill=(*ACCENT, 140))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def render_end_card_image(brand: dict, width: int, height: int, dest: Path) -> Path:
    width, height = _even(width), _even(height)
    copy = card_copy(brand)
    logo_path = resolve_logo_path(brand.get("logo_path"))
    dest.parent.mkdir(parents=True, exist_ok=True)

    if HAS_PIL:
        img = _draw_modern_backdrop(width, height)
        base = img.convert("RGBA")
        draw_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(draw_layer)
        scale = width / 1080.0

        name_font = _font(max(70, int(112 * scale)), bold=True)
        secondary_font = _font(max(32, int(44 * scale)))
        tertiary_font = _font(max(34, int(48 * scale)), bold=True)
        max_text = int(width * 0.82)

        layers = []
        if logo_path:
            logo = _load_logo_rgba(logo_path, int(width * 0.56), int(height * 0.32))
            if logo is not None:
                layers.append(("logo", logo))
        if copy["name"]:
            layers.append(("name", copy["name"]))
        if copy["secondary"]:
            layers.append(("secondary", copy["secondary"]))
        if copy["tertiary"]:
            layers.append(("tertiary", copy["tertiary"]))

        gap = int(34 * scale)
        blocks = []
        total_h = 0
        for kind, payload in layers:
            if kind == "logo":
                plate = int(max(payload.size) * 1.16)
                blocks.append(("logo", payload, (plate, plate)))
                total_h += plate
            elif kind == "name":
                lines = _wrap_text(draw, payload, name_font, max_text) or [payload]
                line_h = int(getattr(name_font, "size", 48) * 1.12)
                blocks.append((kind, lines, (0, line_h * len(lines))))
                total_h += line_h * len(lines)
            elif kind == "secondary":
                lines = _wrap_text(draw, payload, secondary_font, max_text) or [payload]
                line_h = int(getattr(secondary_font, "size", 28) * 1.28)
                blocks.append((kind, lines, (0, line_h * len(lines))))
                total_h += line_h * len(lines)
            else:
                pill_h = int(getattr(tertiary_font, "size", 28) * 1.9)
                blocks.append((kind, [payload], (0, pill_h)))
                total_h += pill_h
            total_h += gap
        total_h = max(0, total_h - gap)
        y = max(int(height * 0.14), (height - total_h) // 2)

        for kind, payload, size in blocks:
            if kind == "logo":
                plate = size[0]
                px = (width - plate) // 2
                plate_img = Image.new("RGBA", (plate, plate), (0, 0, 0, 0))
                pdraw = ImageDraw.Draw(plate_img)
                inset = int(8 * scale)
                # Soft white plate — works for transparent PNGs and solid square logos.
                pdraw.rounded_rectangle(
                    (inset, inset, plate - inset, plate - inset),
                    radius=int(plate * 0.18),
                    fill=(255, 255, 255, 235),
                    outline=(*ACCENT, 90),
                    width=max(2, int(2 * scale)),
                )
                lx = (plate - payload.size[0]) // 2
                ly = (plate - payload.size[1]) // 2
                plate_img.paste(payload, (lx, ly), payload)
                draw_layer.paste(plate_img, (px, y), plate_img)
                y += plate + gap
                continue

            if kind == "name":
                max_line_w = 0
                for line in payload:
                    tw = (
                        draw.textlength(line, font=name_font)
                        if hasattr(draw, "textlength")
                        else name_font.getlength(line)
                    )
                    max_line_w = max(max_line_w, tw)
                    draw.text(((width - tw) / 2, y), line, font=name_font, fill=(*NAME_COLOR, 255))
                    y += int(getattr(name_font, "size", 48) * 1.12)
                line_w = max(int(width * 0.12), int(max_line_w * 0.42))
                ly = y + int(10 * scale)
                draw.rounded_rectangle(
                    ((width - line_w) / 2, ly, (width + line_w) / 2, ly + max(3, int(4 * scale))),
                    radius=2,
                    fill=(*ACCENT, 230),
                )
                y += gap + int(16 * scale)
                continue

            if kind == "secondary":
                for line in payload:
                    tw = (
                        draw.textlength(line, font=secondary_font)
                        if hasattr(draw, "textlength")
                        else secondary_font.getlength(line)
                    )
                    draw.text(((width - tw) / 2, y), line, font=secondary_font, fill=(*MUTED, 255))
                    y += int(getattr(secondary_font, "size", 28) * 1.28)
                y += gap
                continue

            for line in payload:
                tw = (
                    draw.textlength(line, font=tertiary_font)
                    if hasattr(draw, "textlength")
                    else tertiary_font.getlength(line)
                )
                pad_x = int(30 * scale)
                pill_w = tw + pad_x * 2
                pill_h = int(getattr(tertiary_font, "size", 28) * 1.9)
                px = (width - pill_w) / 2
                draw.rounded_rectangle(
                    (px, y, px + pill_w, y + pill_h),
                    radius=int(pill_h / 2),
                    fill=(*WEBSITE_PILL, 245),
                )
                ty = y + (pill_h - getattr(tertiary_font, "size", 28)) / 2 - 1
                draw.text((px + pad_x, ty), line, font=tertiary_font, fill=(*WEBSITE_COLOR, 255))
                y += pill_h + gap

        out = Image.alpha_composite(base, draw_layer).convert("RGB")
        out.save(dest, "PNG")
        return dest

    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    for row in range(height):
        t = row / max(height - 1, 1)
        lift = max(0.0, 1.0 - abs(t - 0.28) * 2.2)
        shade = 0.82 + 0.18 * lift
        canvas[row, :] = (
            int(BG[2] * shade + BG_MID[2] * (1 - shade) * 0.5),
            int(BG[1] * shade + BG_MID[1] * (1 - shade) * 0.5),
            int(BG[0] * shade + BG_MID[0] * (1 - shade) * 0.5),
        )
    bar = max(3, height // 220)
    canvas[0:bar, :] = (ACCENT[2], ACCENT[1], ACCENT[0])
    canvas[height - bar:height, :] = (ACCENT[2], ACCENT[1], ACCENT[0])
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = width / 1080.0
    y = int(height * 0.22)
    if logo_path:
        logo = _load_logo_rgba(logo_path, int(width * 0.56), int(height * 0.32))
        if logo is not None:
            lh, lw = logo.shape[:2]
            x = (width - lw) // 2
            if logo.shape[2] == 4:
                alpha = logo[:, :, 3:4] / 255.0
                roi = canvas[y:y + lh, x:x + lw]
                bgr = logo[:, :, :3]
                canvas[y:y + lh, x:x + lw] = (alpha * bgr + (1 - alpha) * roi).astype(np.uint8)
            else:
                canvas[y:y + lh, x:x + lw] = logo
            y += lh + int(56 * scale)

    def put_centered(text, font_scale, color, thickness):
        nonlocal y
        size, _ = cv2.getTextSize(text, font, font_scale, thickness)
        x = max(20, (width - size[0]) // 2)
        bgr = (color[2], color[1], color[0])
        cv2.putText(canvas, text, (x, y + size[1]), font, font_scale, bgr, thickness, cv2.LINE_AA)
        y += size[1] + int(44 * scale)

    if copy["name"]:
        put_centered(copy["name"][:42], 2.8 * scale, NAME_COLOR, 5)
    if copy["secondary"]:
        put_centered(_short_tagline(copy["secondary"])[:48], 1.3 * scale, MUTED, 2)
    if copy["tertiary"]:
        put_centered(copy["tertiary"][:48], 1.45 * scale, NAME_COLOR, 3)
    cv2.imwrite(str(dest), canvas)
    return dest


def still_to_video(png: Path, dest: Path, duration: float, width: int, height: int, fps: float = 30.0):
    width, height = _even(width), _even(height)
    dur = max(1.5, float(duration))
    _ffmpeg(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-loop", "1", "-t", f"{dur:.2f}", "-i", str(png),
            "-f", "lavfi", "-t", f"{dur:.2f}", "-i", "anullsrc=r=44100:cl=stereo",
            "-vf", f"scale={width}:{height},format=yuv420p,setsar=1",
            "-r", f"{fps:.3f}",
            "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", "-crf", "20",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart",
            str(dest),
        ]
    )


def concat_with_fade(clip: Path, end_card: Path, dest: Path, clip_dur: float, has_audio: bool):
    fade = 0.4 if clip_dur >= 1.2 else 0.15
    fade_start = max(0.0, clip_dur - fade)
    w_filter = (
        f"scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1,fade=t=out:st={fade_start:.3f}:d={fade:.3f}"
    )
    end_filter = "scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1"
    if has_audio:
        filter_complex = (
            f"[0:v]{w_filter}[v0];"
            f"[0:a]afade=t=out:st={fade_start:.3f}:d={fade:.3f},aresample=44100[a0];"
            f"[1:v]{end_filter}[v1];"
            "[1:a]aresample=44100[a1];"
            "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
        )
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(clip), "-i", str(end_card),
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
        ]
    else:
        filter_complex = (
            f"[0:v]{w_filter}[v0];"
            f"[2:a]aformat=sample_rates=44100:channel_layouts=stereo,atrim=0:{clip_dur:.3f},"
            f"afade=t=out:st={fade_start:.3f}:d={fade:.3f}[a0];"
            f"[1:v]{end_filter}[v1];"
            "[1:a]aresample=44100[a1];"
            "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
        )
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(clip), "-i", str(end_card),
            "-f", "lavfi", "-t", f"{clip_dur:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
        ]
    command.extend([
        "-preset", "ultrafast", "-crf", "23",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "160k",
        "-movflags", "+faststart",
        str(dest),
    ])
    _ffmpeg(command)


def append_end_screen(video_path: Path, brand: dict) -> tuple[bool, float, str]:
    info = probe_video(video_path)
    width = info.get("width") or 1080
    height = info.get("height") or 1920
    clip_dur = float(info.get("duration") or 0)
    extra = choose_duration(clip_dur, brand.get("end_screen_duration") or 3)
    if extra is None:
        return False, 0.0, f"clip too short ({clip_dur:.1f}s)"

    png = video_path.parent / f".{video_path.stem}_endcard.png"
    card_mp4 = video_path.parent / f".{video_path.stem}_endcard.mp4"
    staged = video_path.parent / f".{video_path.stem}_branded.mp4"
    try:
        render_end_card_image(brand, width, height, png)
        still_to_video(png, card_mp4, extra, width, height, info.get("fps") or 30)
        concat_with_fade(video_path, card_mp4, staged, clip_dur, bool(info.get("has_audio")))
        branded = probe_video(staged)
        if not staged.exists() or (branded.get("duration") or 0) < clip_dur + extra * 0.5:
            raise RuntimeError("branded file missing or shorter than expected")
        staged.replace(video_path)
        return True, extra, "ok"
    except Exception as exc:
        return False, 0.0, str(exc)[:400]
    finally:
        for path in (png, card_mp4, staged):
            path.unlink(missing_ok=True)


def _load_bank() -> dict:
    if not BANK_FILE.exists():
        return {}
    try:
        with open(BANK_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_bank(bank: dict):
    with open(BANK_FILE, "w", encoding="utf-8") as handle:
        json.dump(bank, handle, indent=2, ensure_ascii=False)


def apply_brand_end_screens(brand: dict | None = None) -> dict:
    brand = brand or load_brand()
    report = {
        "enabled": bool(brand.get("end_screen_enabled")),
        "applied": 0,
        "skipped": 0,
        "failed": 0,
        "details": [],
    }
    if not brand.get("end_screen_enabled"):
        print("Brand end screen is off — leaving clips unchanged.")
        return report
    if not (brand.get("brand_name") or "").strip():
        print("⚠️  End screen is on but brand name is missing — skipping. Original clips kept.")
        report["skipped"] = 1
        report["details"].append({"reason": "brand_name required"})
        return report

    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    masters = sorted(SHORTS_DIR.glob("short_*.mp4")) if SHORTS_DIR.exists() else []
    extras_by_master: dict[str, float] = {}

    for master in masters:
        ok, extra, reason = append_end_screen(master, brand)
        report["details"].append({"file": master.name, "ok": ok, "seconds": extra, "reason": reason})
        if ok:
            report["applied"] += 1
            extras_by_master[str(master.resolve())] = extra
            print(f"   +{extra:.1f}s end screen → {master.name}")
        elif reason.startswith("clip too short"):
            report["skipped"] += 1
            print(f"   skipped {master.name}: {reason}")
        else:
            report["failed"] += 1
            print(f"   ⚠️  {master.name} left unchanged ({reason})")

    bank = _load_bank()
    items = bank.get("items") or []
    for item in items:
        source = Path(item["video_file"]) if item.get("video_file") else None
        dest = Path(item["platform_video_file"]) if item.get("platform_video_file") else None
        if source and source.exists() and dest:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source), str(dest))
            extra = extras_by_master.get(str(source.resolve()), 0)
            if extra:
                try:
                    item["duration_seconds"] = round(float(item.get("duration_seconds") or 0) + extra, 2)
                except (TypeError, ValueError):
                    pass
                item["end_screen_applied"] = True
                item["end_screen_seconds"] = extra
    if items:
        _save_bank(bank)

    if not masters:
        for folder in PLATFORM_FOLDERS:
            folder_path = OUTPUT / folder
            if not folder_path.exists():
                continue
            for clip in sorted(folder_path.glob("*.mp4")):
                ok, extra, reason = append_end_screen(clip, brand)
                report["details"].append({"file": str(clip.relative_to(OUTPUT)), "ok": ok, "seconds": extra, "reason": reason})
                if ok:
                    report["applied"] += 1
                elif str(reason).startswith("clip too short"):
                    report["skipped"] += 1
                else:
                    report["failed"] += 1

    REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"✅ End screen: {report['applied']} applied, "
        f"{report['skipped']} skipped, {report['failed']} failed (originals kept)"
    )
    return report


def main():
    try:
        apply_brand_end_screens()
    except Exception as exc:
        print(f"⚠️  Brand end screen step failed: {exc}")
        print("   Original generated clips were left unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
