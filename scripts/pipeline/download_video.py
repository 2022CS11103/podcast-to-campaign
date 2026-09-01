import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SIDECAR_PY = PROJECT_ROOT / ".tools" / "ytdlp" / "bin" / "python"


def _bootstrap_ytdlp_sidecar() -> None:
    """Current yt-dlp needs Python 3.10+. The app venv may still be 3.9."""
    if SIDECAR_PY.exists():
        return
    py = (
        shutil.which("python3.12")
        or shutil.which("python3.13")
        or shutil.which("python3.11")
        or shutil.which("python3.10")
    )
    if not py:
        return
    print("Installing a current yt-dlp (Python 3.10+ is required)...")
    venv_dir = SIDECAR_PY.parent.parent
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([py, "-m", "venv", str(venv_dir)], check=True)
    subprocess.run(
        [
            str(SIDECAR_PY),
            "-m",
            "pip",
            "install",
            "-U",
            "pip",
            "yt-dlp[default]",
            "python-dotenv",
        ],
        check=True,
    )


def _reexec_with_current_ytdlp() -> None:
    if sys.version_info >= (3, 10):
        return
    if Path(sys.executable).resolve() == SIDECAR_PY.resolve():
        return
    _bootstrap_ytdlp_sidecar()
    if not SIDECAR_PY.exists():
        return
    os.execv(str(SIDECAR_PY), [str(SIDECAR_PY), *sys.argv])


if __name__ == "__main__":
    _reexec_with_current_ytdlp()

import yt_dlp
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

# One client per attempt. Bundling mweb/web with android makes yt-dlp
# fetch the webpage/web player and hit the bot/PO-token path.
# android_vr and android still offer progressive MP4 (format 18) without a PO token.
CLIENTS_ANON = ["android", "android_vr", "tv", "mweb"]
CLIENTS_COOKIES = ["android", "android_vr", "tv"]

BOT_HINTS = ("sign in to confirm", "not a bot", "confirm you’re not a bot", "confirm you're not a bot")
LOCKED_COOKIE_HINTS = (
    "could not copy chrome cookie database",
    "could not find firefox cookies",
    "failed to decrypt",
    "keychain",
)


def canonical_youtube_url(url: str) -> str:
    """Keep only the video id so playlist (&list=) junk cannot leak into the request."""
    raw = (url or "").strip()
    if not raw:
        return raw

    short = re.search(r"(?:youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_-]{6,})", raw)
    if short:
        return f"https://www.youtube.com/watch?v={short.group(1)}"

    parsed = urlparse(raw)
    video_id = (parse_qs(parsed.query).get("v") or [None])[0]
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"

    embed = re.search(r"youtube\.com/embed/([A-Za-z0-9_-]{6,})", raw)
    if embed:
        return f"https://www.youtube.com/watch?v={embed.group(1)}"

    return raw


def _is_bot_check(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(hint in text for hint in BOT_HINTS)


def _is_locked_cookie_db(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(hint in text for hint in LOCKED_COOKIE_HINTS)


def _js_runtimes():
    runtimes = {}
    node = shutil.which("node")
    if node:
        runtimes["node"] = {"path": node}
    deno = shutil.which("deno")
    if deno:
        runtimes["deno"] = {"path": deno}
    if not runtimes:
        runtimes["node"] = {}
    return runtimes


def _probe_media(path: Path):
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height:format=duration",
                "-of", "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            return None, None, None
        data = json.loads(result.stdout or "{}")
        stream = (data.get("streams") or [{}])[0]
        duration = float((data.get("format") or {}).get("duration") or 0)
        return duration, stream.get("width"), stream.get("height")
    except Exception:
        return None, None, None


def _media_ok(path: Path, expected_duration=None):
    duration, width, height = _probe_media(path)
    if not duration:
        return False, "could not probe downloaded file"
    if expected_duration and duration < float(expected_duration) * 0.8:
        return False, f"got {duration:.0f}s, expected ~{float(expected_duration):.0f}s"
    note = f"Downloaded {width}x{height} · {duration:.0f}s"
    if height and height < 720:
        note += " (YouTube only offered this resolution for this session)"
    print(note)
    return True, None


def _cookie_files():
    env_path = os.getenv("YTDLP_COOKIES", "").strip()
    paths = []
    if env_path:
        paths.append(Path(env_path).expanduser())
    paths.extend([PROJECT_ROOT / "cookies.txt", PROJECT_ROOT / "youtube_cookies.txt"])
    seen = set()
    for path in paths:
        try:
            resolved = str(path.resolve())
        except OSError:
            continue
        if resolved in seen or not path.is_file():
            continue
        seen.add(resolved)
        yield path


def _browser_profile_roots():
    home = Path.home()
    if sys.platform == "darwin":
        support = home / "Library" / "Application Support"
        return {
            "chrome": support / "Google" / "Chrome",
            "edge": support / "Microsoft Edge",
            "brave": support / "BraveSoftware" / "Brave-Browser",
            "chromium": support / "Chromium",
            "firefox": support / "Firefox" / "Profiles",
        }
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        roaming = Path(os.environ.get("APPDATA", ""))
        return {
            "edge": local / "Microsoft" / "Edge" / "User Data",
            "chrome": local / "Google" / "Chrome" / "User Data",
            "brave": local / "BraveSoftware" / "Brave-Browser" / "User Data",
            "chromium": local / "Chromium" / "User Data",
            "firefox": roaming / "Mozilla" / "Firefox" / "Profiles",
        }
    config = Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config")))
    return {
        "chrome": Path(config) / "google-chrome",
        "edge": Path(config) / "microsoft-edge",
        "brave": Path(config) / "BraveSoftware" / "Brave-Browser",
        "chromium": Path(config) / "chromium",
        "firefox": home / ".mozilla" / "firefox",
    }


def _browser_installed(name: str) -> bool:
    root = _browser_profile_roots().get(name)
    return bool(root and root.exists())


def _browser_names():
    env_browser = os.getenv("YTDLP_COOKIES_FROM_BROWSER", "").strip().lower()
    # Firefox cookies can be read while the browser is open. Chrome/Edge
    # lock (and often encrypt) their cookie DB on Windows.
    preferred = ("firefox", "edge", "chrome", "brave", "chromium")
    if sys.platform != "win32":
        preferred = ("chrome", "edge", "firefox", "brave", "chromium")
    ordered = []
    if env_browser:
        ordered.append(env_browser)
    for name in preferred:
        if name not in ordered and _browser_installed(name):
            ordered.append(name)
    return ordered


def _auth_attempts():
    for client in CLIENTS_ANON:
        yield f"YouTube {client} client", {}, [client]
    for path in _cookie_files():
        for client in CLIENTS_COOKIES:
            yield f"cookies file {path.name} ({client})", {"cookiefile": str(path)}, [client]
    profile = os.getenv("YTDLP_BROWSER_PROFILE", "").strip() or None
    for browser in _browser_names():
        spec = (browser, profile) if profile else (browser,)
        for client in CLIENTS_COOKIES:
            yield f"cookies from {browser} ({client})", {"cookiesfrombrowser": spec}, [client]


def _base_opts(tmpl: str, clients: list) -> dict:
    return {
        # Prefer progressive HTTP MP4 (18/22) over HLS/m3u8.
        "format": (
            "18/22/"
            "b[ext=mp4][protocol^=http]/"
            "bv*[height<=1080][protocol^=http]+ba/"
            "bv*[height<=1080][height>=720]+ba/"
            "bv*[height<=1080]+ba/"
            "b[height<=1080]/b"
        ),
        "format_sort": ["proto:https", "res:1080", "ext:mp4:m4a"],
        "merge_output_format": "mp4",
        "outtmpl": tmpl,
        "quiet": False,
        "noplaylist": True,
        "retries": 5,
        "fragment_retries": 5,
        "nocheckcertificate": True,
        # Windows raises [Errno 22] Invalid argument when yt-dlp applies
        # a Last-Modified / upload timestamp outside the valid range.
        "mtime": False,
        "extractor_args": {"youtube": {"player_client": clients}},
        "js_runtimes": _js_runtimes(),
        "remote_components": ["ejs:github"],
    }


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        # File may still be open in Explorer / Defender / a previous probe.
        print(f"Could not remove {path.name}: {exc}", file=sys.stderr)


def _clear_partials(input_dir: Path, output_path: Path) -> None:
    _safe_unlink(output_path)
    for leftover in input_dir.glob("video.*"):
        _safe_unlink(leftover)
    for leftover in input_dir.glob("_thin_backup.mp4"):
        _safe_unlink(leftover)


def _bot_help(url: str, tried: list[str], locked_cookies: bool = False) -> str:
    tried_txt = ", ".join(tried) if tried else "none"
    return (
        "YouTube blocked this download (bot check).\n"
        f"Watch URL: {url}\n"
        f"Tried: {tried_txt}\n"
        "Paste-a-link does not require a signed-in browser. Try Again in a moment, "
        "or upload the MP4 if YouTube keeps challenging this network."
    )


def download_video(url):
    """
    Downloads a YouTube video as MP4 into input/video.mp4
    """
    url = canonical_youtube_url(url)
    print(f"yt-dlp {yt_dlp.version.__version__} on Python {sys.version.split()[0]}")
    print(f"Downloading: {url}")

    input_dir = PROJECT_ROOT / "input"
    input_dir.mkdir(exist_ok=True)
    output_path = input_dir / "video.mp4"
    tmpl = str(input_dir / "video.%(ext)s")

    thin_keep = None
    tried = []
    last_error = None
    saw_bot = False
    saw_locked = False
    expected_duration = None

    for label, auth, clients in _auth_attempts():
        tried.append(label)
        print(f"Trying {label}...")
        _clear_partials(input_dir, output_path)
        ydl_opts = _base_opts(tmpl, clients)
        ydl_opts.update(auth)
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info and info.get("duration"):
                    expected_duration = info.get("duration")
            last_error = None
        except Exception as exc:
            last_error = exc
            print(f"{label} failed: {exc}", file=sys.stderr)
            if _is_bot_check(exc):
                saw_bot = True
            if _is_locked_cookie_db(exc):
                saw_locked = True
            if "is not a valid url" in str(exc).lower() or "unsupported url" in str(exc).lower():
                break
            continue

        produced = output_path
        if not produced.exists():
            matches = sorted(
                p for p in input_dir.glob("video.*")
                if p.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}
            )
            if matches:
                produced = matches[0]
                if produced != output_path:
                    produced.replace(output_path)

        if output_path.exists():
            ok, why = _media_ok(output_path, expected_duration)
            if ok:
                break
            print(f"{label} produced a thin file ({why}) - trying next method...")
            last_error = RuntimeError(why)
            thin_keep = input_dir / "_thin_backup.mp4"
            shutil.copy2(output_path, thin_keep)
            _clear_partials(input_dir, output_path)

    if not output_path.exists() and thin_keep and thin_keep.exists():
        shutil.move(str(thin_keep), str(output_path))
        print("Could not get a fuller file - keeping the thinner download.")

    if thin_keep and thin_keep.exists() and output_path.exists():
        thin_keep.unlink()

    if not output_path.exists():
        if saw_bot or saw_locked:
            raise RuntimeError(_bot_help(url, tried, locked_cookies=saw_locked)) from last_error
        if last_error:
            raise RuntimeError(f"DOWNLOAD FAILED: {last_error}") from last_error
        raise FileNotFoundError(f"Expected {output_path} after download")

    return output_path


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("python scripts/pipeline/download_video.py <youtube_url>")
        sys.exit(2)

    url = sys.argv[1]
    print("Downloading video...")
    try:
        video_path = download_video(url)
    except Exception as e:
        print(f"DOWNLOAD FAILED: {e}", file=sys.stderr)
        sys.exit(1)

    print("\nVideo downloaded successfully!")
    print(f"Saved at: {video_path}")


if __name__ == "__main__":
    main()
