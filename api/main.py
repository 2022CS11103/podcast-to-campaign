from __future__ import annotations

from fastapi import FastAPI, HTTPException, File, UploadFile, Request, Header
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import json
import os
import time
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import unquote
from dotenv import load_dotenv
from api.schemas import (
    ProcessRequest,
    ProcessResponse,
    StatusResponse,
    PerformanceRequest,
    RepostRequest,
    RecommendPlanRequest,
    YouTubeUploadRequest,
    StopJobRequest,
    ScopeJobRequest,
    ScheduleControlRequest,
    ScheduleStatusRequest,
    ReviewBulkRequest,
    BrandUpdateRequest,
    BillingCheckoutRequest,
    BillingPortalRequest,
    ClipDeskRequest,
)
from api.job_manager import job_manager
from api.pipeline_runner import start_worker, enqueue_job
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from scripts.ai.quick_recommend import recommend
from scripts.ai.ab_engine import (
    record_performance as save_performance,
    list_winners,
    schedule_repost,
)
from config.platform_specs import PLATFORM_SPECS, CANDIDATE_TARGET_SECONDS
from utils.pipeline_timer import format_duration, snapshot as timing_snapshot
from utils.pipeline_steps import describe_step
from utils.campaign_calendar import from_bank as calendar_from_bank
from utils.content_plan import normalize_plan, load_plan, save_plan
from utils.brand_settings import (
    BRAND_DIR,
    load_brand,
    merge_and_save,
    public_brand,
    resolve_logo_path,
    save_brand,
)
from utils.billing import (
    billing_enabled,
    billing_enforced,
    can_run_campaign,
    construct_webhook_event,
    create_checkout_session,
    create_portal_session,
    entitled_max_days,
    handle_webhook_event,
    normalize_email,
    status_payload,
)
from utils.social_oauth import (
    all_statuses as social_account_statuses,
    authorization_url as social_authorization_url,
    configured as social_oauth_configured,
    disconnect as disconnect_social,
    exchange_callback as exchange_social_callback,
)

try:
    from utils.youtube_oauth import (
        authorization_url as youtube_authorization_url,
        configured as youtube_oauth_configured,
        connection_status as youtube_connection_status,
        disconnect as disconnect_youtube,
        exchange_callback as exchange_youtube_callback,
        upload_video as upload_youtube_video,
    )
except ImportError:
    def youtube_oauth_configured():
        return False

    def youtube_connection_status():
        return {
            "platform": "youtube",
            "label": "YouTube",
            "status": "not_configured",
            "connected": False,
        }

    def youtube_authorization_url():
        raise RuntimeError(
            "YouTube connect needs google-auth-oauthlib. "
            "Activate .venv and run: pip install google-auth-oauthlib"
        )

    def disconnect_youtube():
        return None

    def exchange_youtube_callback(*_args, **_kwargs):
        raise RuntimeError("YouTube connect needs google-auth-oauthlib in the project venv.")

    def upload_youtube_video(*_args, **_kwargs):
        raise RuntimeError("YouTube upload needs google-auth-oauthlib in the project venv.")

app = FastAPI(title="CreatorOS API")

# Lovable (browser) + ngrok: wildcard origin cannot be used with credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
PUBLIC_FRONTEND_URL = os.getenv(
    "FRONTEND_URL", "/app"
).rstrip("/")
CONTENT_BANK = PROJECT_ROOT / "output" / "content_bank.json"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
UPLOAD_DIR = PROJECT_ROOT / "input" / "uploads"
LOGO_MAX_BYTES = 8 * 1024 * 1024
LOGO_TYPES = {".png", ".jpg", ".jpeg", ".webp"}
MEDIA_FOLDERS = {
    "final_shorts", "youtube_shorts", "instagram_reels", "tiktok", "posts", "clip_desk",
}

def _merge_scope(current: dict, override: dict) -> dict:
    merged = dict(current or {})
    for platform, config in (override or {}).items():
        base = dict(merged.get(platform) or {})
        if isinstance(config, dict):
            base.update(config)
        else:
            base["count"] = config
        merged[platform] = base
    return merged




@app.on_event("startup")
def startup_event():
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if stream is not None and hasattr(stream, "reconfigure"):
                try:
                    stream.reconfigure(encoding="utf-8", errors="replace")
                except (OSError, ValueError):
                    pass
    start_worker()


@app.get("/")
def root():
    return {"status": "ok", "service": "creatoros"}


@app.get("/health")
def health():
    return JSONResponse({"status": "ok"})


@app.get("/auth/config")
def auth_config():
    return {
        "google_client_id": os.getenv("GOOGLE_CLIENT_ID") or "",
        "billing_enabled": billing_enforced(),
        "billing_preview": billing_enabled() and not billing_enforced(),
    }


def _request_email(
    request: Request,
    body_email: str | None = None,
    x_user_email: Optional[str] = Header(default=None, alias="X-User-Email"),
) -> str:
    return normalize_email(
        body_email
        or x_user_email
        or request.headers.get("x-user-email")
        or ""
    )


@app.get("/billing/status")
def billing_status(
    request: Request,
    x_user_email: Optional[str] = Header(default=None, alias="X-User-Email"),
):
    email = _request_email(request, x_user_email=x_user_email)
    return status_payload(email)


@app.post("/billing/checkout")
def billing_checkout(
    req: BillingCheckoutRequest,
    request: Request,
    x_user_email: Optional[str] = Header(default=None, alias="X-User-Email"),
):
    email = _request_email(request, req.email, x_user_email)
    try:
        return create_checkout_session(
            email,
            req.price_id,
            req.user_id,
            campaign_days=req.campaign_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/billing/portal")
def billing_portal(
    req: BillingPortalRequest,
    request: Request,
    x_user_email: Optional[str] = Header(default=None, alias="X-User-Email"),
):
    email = _request_email(request, req.email, x_user_email)
    try:
        return create_portal_session(email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    if not billing_enforced():
        raise HTTPException(status_code=503, detail="Billing is not enabled.")
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    try:
        event = construct_webhook_event(payload, signature)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Webhook error: {exc}") from exc
    if hasattr(event, "to_dict"):
        event = event.to_dict()
    return handle_webhook_event(event)


@app.get("/studio")
@app.get("/studio/")
def studio():
    return RedirectResponse(PUBLIC_FRONTEND_URL, status_code=302)


if (FRONTEND_DIST / "assets").exists():
    app.mount(
        "/app/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="creatoros-assets",
    )


def _frontend_app():
    index = FRONTEND_DIST / "index.html"
    if not index.exists():
        raise HTTPException(
            status_code=503,
            detail="Frontend build is missing. Run `npm run build` inside frontend/.",
        )
    return FileResponse(index, media_type="text/html")


@app.get("/app")
@app.get("/app/")
@app.get("/app/{route:path}")
def frontend_app(route: str = ""):
    return _frontend_app()


@app.post("/uploads/video")
async def upload_source_video(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    allowed = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
    if suffix not in allowed:
        raise HTTPException(
            status_code=415,
            detail="Upload an MP4, MOV, MKV, WebM, or M4V video.",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
    total = 0
    max_bytes = 5 * 1024 * 1024 * 1024
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail="Video exceeds the 5 GB upload limit.",
                    )
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    return {
        "path": str(destination.resolve()),
        "filename": file.filename,
        "size_bytes": total,
    }


def _logo_media_type(path: Path) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "application/octet-stream")


@app.get("/brand")
def get_brand():
    return public_brand()


@app.put("/brand")
def update_brand(req: BrandUpdateRequest):
    incoming = req.model_dump(exclude_none=True) if hasattr(req, "model_dump") else req.dict(exclude_none=True)
    extras = getattr(req, "model_extra", None) or {}
    incoming.update({k: v for k, v in extras.items() if v is not None})
    if incoming.get("end_screen_enabled") and not str(incoming.get("brand_name") or load_brand().get("brand_name") or "").strip():
        raise HTTPException(status_code=400, detail="Brand name is required for the end screen.")
    if "logo_path" in incoming and incoming.get("logo_path") in ("", None):
        current = load_brand()
        current["logo_path"] = ""
        current.update({k: v for k, v in incoming.items() if k != "logo_path"})
        return public_brand(save_brand(current))
    return public_brand(merge_and_save(incoming))


@app.get("/brand/logo")
def get_brand_logo():
    path = resolve_logo_path(load_brand().get("logo_path"))
    if path is None:
        raise HTTPException(status_code=404, detail="No brand logo uploaded.")
    return FileResponse(path, media_type=_logo_media_type(path), filename=path.name)


@app.delete("/brand/logo")
def clear_brand_logo():
    current = load_brand()
    old = resolve_logo_path(current.get("logo_path"))
    current["logo_path"] = ""
    saved = save_brand(current)
    if old and old.exists() and old.parent == BRAND_DIR.resolve():
        old.unlink(missing_ok=True)
    return public_brand(saved)


@app.post("/uploads/logo")
async def upload_brand_logo(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in LOGO_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Upload a PNG, JPG, or WebP logo. Transparent PNG works best.",
        )
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    destination = BRAND_DIR / f"logo_{uuid.uuid4().hex}{suffix}"
    total = 0
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > LOGO_MAX_BYTES:
                    raise HTTPException(status_code=413, detail="Logo exceeds the 8 MB upload limit.")
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    previous = resolve_logo_path(load_brand().get("logo_path"))
    relative = str(destination.relative_to(PROJECT_ROOT)).replace("\\", "/")
    saved = merge_and_save({"logo_path": relative})
    if previous and previous.exists() and previous != destination.resolve():
        if previous.parent.resolve() == BRAND_DIR.resolve():
            previous.unlink(missing_ok=True)
    return {
        "path": relative,
        "filename": file.filename,
        "size_bytes": total,
        "logo_url": "/brand/logo",
        "brand": public_brand(saved),
    }


@app.get("/media/{folder}/{filename}")
def get_media(folder: str, filename: str):
    filename = unquote(filename).split("?")[0].strip()
    if folder not in MEDIA_FOLDERS or "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=404, detail="Not found")
    path = PROJECT_ROOT / "output" / folder / filename
    if not path.exists() or not path.is_file():
        fallback = _media_fallback(folder, filename)
        if fallback is None:
            raise HTTPException(status_code=404, detail="File not found")
        path = fallback
    suffix = path.suffix.lower()
    media_type = {
        ".mp4": "video/mp4",
        ".md": "text/markdown",
        ".json": "application/json",
        ".srt": "text/plain",
        ".ass": "text/plain",
    }.get(suffix, "application/octet-stream")
    return FileResponse(path, media_type=media_type, filename=path.name)


def _play_url(path_str):
    if not path_str:
        return None
    p = Path(path_str)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    if not p.exists() or not p.is_file():
        return None
    if p.parent.name in MEDIA_FOLDERS:
        return f"/media/{p.parent.name}/{p.name}"
    return None


def _item_play_url(item):
    return _play_url(item.get("platform_video_file")) or _play_url(item.get("video_file"))


POST_DECK_FILES = {
    "linkedin": "linkedin.md",
    "twitter": "twitter.md",
    "youtube_shorts": "youtube.md",
    "instagram_reels": "instagram.md",
    "tiktok": "tiktok.md",
}


def _item_post_path(item):
    """Resolve a per-clip markdown post, including paths from another machine."""
    candidates = []
    raw = item.get("post_file")
    if raw:
        stored = Path(raw)
        candidates.append(stored if stored.is_absolute() else PROJECT_ROOT / stored)
        candidates.append(PROJECT_ROOT / "output" / "posts" / stored.name)
    item_id = item.get("id")
    platform = item.get("assigned_platform")
    if item_id and platform:
        candidates.append(
            PROJECT_ROOT / "output" / "posts" / f"{item_id}_{platform}.md"
        )
    seen = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.exists() and path.is_file():
            return path
    return None


def _read_post_markdown(item, limit=20000):
    path = _item_post_path(item)
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8")[:limit]
    except OSError:
        return ""


def _campaign_post_decks(limit=40000):
    decks = {}
    for platform, filename in POST_DECK_FILES.items():
        path = PROJECT_ROOT / "output" / filename
        if not path.exists() or not path.is_file():
            continue
        try:
            decks[platform] = path.read_text(encoding="utf-8")[:limit]
        except OSError:
            continue
    return decks


def _media_fallback(folder: str, filename: str):
    """If a platform copy was wiped mid-job, serve the source cut instead."""
    if not CONTENT_BANK.exists():
        return None
    with open(CONTENT_BANK, "r", encoding="utf-8") as f:
        bank = json.load(f)
    needle = filename.lower()
    for item in bank.get("items", []):
        platform_file = item.get("platform_video_file") or ""
        if Path(platform_file).name.lower() != needle:
            continue
        src = item.get("video_file")
        if not src:
            continue
        p = Path(src)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        if p.exists() and p.is_file():
            return p
    final = PROJECT_ROOT / "output" / "final_shorts" / filename
    if final.exists() and final.is_file():
        return final
    return None


def _decorate_board_items(raw_items):
    """
    Same talk moment can fill Shorts and Reels. The board must still
    look like different posts: rotate A/B/C copy and label the package.
    """
    platforms_by_chunk = {}
    for item in raw_items:
        cid = item.get("chunk_id")
        plat = item.get("assigned_platform")
        platforms_by_chunk.setdefault(cid, [])
        if plat not in platforms_by_chunk[cid]:
            platforms_by_chunk[cid].append(plat)

    variant_cursor = {}
    seen_on_platform = {}
    items = []
    for item in raw_items:
        row = dict(item)
        cid = item.get("chunk_id")
        plat = item.get("assigned_platform")
        variants = item.get("variants") or []
        n = variant_cursor.get(cid, 0)
        variant_cursor[cid] = n + 1
        chosen = variants[min(n, max(len(variants) - 1, 0))] if variants else {}
        also_on = [p for p in platforms_by_chunk.get(cid, []) if p != plat]
        here_key = (plat, cid)
        reused_here = seen_on_platform.get(here_key, 0) > 0
        seen_on_platform[here_key] = seen_on_platform.get(here_key, 0) + 1
        if reused_here:
            package_label = "calendar remix · different angle"
        elif also_on:
            package_label = "same moment · rewritten for this platform"
        else:
            package_label = "distinct opening"
        row["play_url"] = _item_play_url(item)
        row["display_hook"] = chosen.get("hook") or item.get("hook")
        row["display_caption"] = chosen.get("caption") or item.get("summary")
        row["post_markdown"] = _read_post_markdown(item)
        post_path = _item_post_path(item)
        row["post_url"] = _play_url(str(post_path)) if post_path else None
        row["display_angle"] = chosen.get("angle") or item.get("content_angle")
        row["variant_id"] = chosen.get("id") or item.get("active_variant") or "A"
        row["same_moment"] = bool(also_on)
        row["also_on"] = also_on
        row["package_label"] = package_label
        reasons = item.get("review_reasons") or []
        if not reasons:
            seed = []
            if item.get("highlight_reason"):
                seed.append(item["highlight_reason"])
            if item.get("content_angle") or item.get("detected_topic"):
                seed.append(item.get("detected_topic") or item.get("content_angle"))
            if item.get("editor_note"):
                seed.append(str(item["editor_note"])[:90])
            reasons = [r for r in seed if r][:4] or ["AI-selected highlight"]
        row["review_reasons"] = reasons
        row["transcript_excerpt"] = (
            item.get("transcript_excerpt")
            or (item.get("summary") or "")[:280]
        )
        row["detected_topic"] = item.get("detected_topic") or item.get("content_angle") or ""
        row["quality"] = {
            "overall_score": item.get("overall_score"),
            "platform_fit_score": item.get("platform_fit_score"),
            "word_score": item.get("word_score"),
            "visual_score": item.get("visual_score"),
            "audio_energy": item.get("audio_energy"),
        }
        items.append(row)
    return items


@app.get("/transcript")
def get_transcript(source: Optional[str] = None):
    """Campaign transcript, or the latest clip-desk transcript."""
    if (source or "").strip().lower() == "campaign":
        clean = PROJECT_ROOT / "output" / "clean_transcript.json"
        raw = PROJECT_ROOT / "output" / "transcript.json"
        path = clean if clean.exists() else raw if raw.exists() else None
        if not path:
            raise HTTPException(
                status_code=404,
                detail="No campaign transcript yet. Generate a campaign first.",
            )
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        segments = data.get("segments") or []
        text = (data.get("transcript") or "").strip()
        if not text:
            text = " ".join(
                str(seg.get("text") or "").strip()
                for seg in segments
                if str(seg.get("text") or "").strip()
            )
        return {
            "source": path.name,
            "kind": "campaign",
            "language": data.get("language") or data.get("lang"),
            "duration_seconds": data.get("duration") or data.get("duration_seconds"),
            "segment_count": len(segments),
            "transcript": text,
            "segments": [
                {
                    "start": float(seg.get("start") or 0),
                    "end": float(seg.get("end") or 0),
                    "text": str(seg.get("text") or "").strip(),
                }
                for seg in segments
                if str(seg.get("text") or "").strip()
            ],
        }

    from utils.clip_desk import latest_clip_transcript

    clip = latest_clip_transcript()
    if clip:
        return {**clip, "kind": "clip_desk"}

    # Fall back to campaign transcript
    clean = PROJECT_ROOT / "output" / "clean_transcript.json"
    raw = PROJECT_ROOT / "output" / "transcript.json"
    path = clean if clean.exists() else raw if raw.exists() else None
    if not path:
        raise HTTPException(
            status_code=404,
            detail="No transcript yet. Use the form below to fetch a link, or run a campaign.",
        )
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    segments = data.get("segments") or []
    text = (data.get("transcript") or "").strip()
    if not text:
        text = " ".join(
            str(seg.get("text") or "").strip()
            for seg in segments
            if str(seg.get("text") or "").strip()
        )
    return {
        "source": path.name,
        "kind": "campaign",
        "language": data.get("language") or data.get("lang"),
        "duration_seconds": data.get("duration") or data.get("duration_seconds"),
        "segment_count": len(segments),
        "transcript": text,
        "segments": [
            {
                "start": float(seg.get("start") or 0),
                "end": float(seg.get("end") or 0),
                "text": str(seg.get("text") or "").strip(),
            }
            for seg in segments
            if str(seg.get("text") or "").strip()
        ],
    }


@app.post("/tools/fetch-clip")
def tools_fetch_clip(req: ClipDeskRequest):
    """Download a URL (full or timespan) without starting a campaign."""
    from utils.clip_desk import fetch_clip

    try:
        return fetch_clip(req.url or "", start=req.start, end=req.end, job_id=req.job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/tools/transcribe-clip")
def tools_transcribe_clip(req: ClipDeskRequest):
    """Transcribe full video or only the selected timespan."""
    from utils.clip_desk import transcribe_clip

    try:
        return transcribe_clip(
            url=req.url,
            start=req.start,
            end=req.end,
            mode=req.mode or "range",
            job_id=req.job_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/campaign-board")
def campaign_board():
    summary = {}
    summary_file = PROJECT_ROOT / "output" / "campaign_summary.json"
    if summary_file.exists():
        with open(summary_file, "r", encoding="utf-8") as f:
            summary = json.load(f)
    bank = {}
    if CONTENT_BANK.exists():
        with open(CONTENT_BANK, "r", encoding="utf-8") as f:
            bank = json.load(f)
    items = _decorate_board_items(bank.get("items", []))
    videos_ready = any(item.get("play_url") for item in items)
    scan = summary.get("scan") or {}
    transcript_file = PROJECT_ROOT / "output" / "transcript.json"
    if not scan and transcript_file.exists():
        with open(transcript_file, "r", encoding="utf-8") as f:
            scan = json.load(f).get("scan") or {}
    needs_review = sum(
        1
        for item in items
        if (item.get("status") or "").lower() in {"ai_generated", "pending", "draft", ""}
    )
    return {
        "summary": summary,
        "plan": bank.get("requested_plan"),
        "total_allocated": bank.get("total_allocated", len(items)),
        "video_renders": bank.get("video_renders"),
        "videos_ready": videos_ready,
        "needs_review_count": needs_review,
        "scan": scan,
        "analysis_mode": summary.get("analysis_mode") or (
            "audio_visual" if scan.get("visual_analysis") else "audio_first"
        ),
        "items": items,
        "campaign_posts": _campaign_post_decks(),
        "calendar": calendar_from_bank({**bank, "items": items}) if items else None,
        "holds": dict(bank.get("holds") or {}),
    }


def _accounts_payload():
    youtube = youtube_connection_status()
    accounts = [youtube, *social_account_statuses()]
    linked = [row for row in accounts if row.get("connected")]
    return {
        "accounts": accounts,
        "connected": bool(linked),
        "can_skip": True,
        "message": (
            f"{len(linked)} channel(s) connected."
            if linked
            else "No accounts linked. Connect a channel or generate a downloadable campaign package."
        ),
    }


@app.get("/connected-accounts")
@app.get("/accounts")
@app.get("/integrations")
@app.get("/oauth/status")
@app.get("/auth/connections")
def connected_accounts():
    return _accounts_payload()


@app.post("/connect/skip")
@app.post("/oauth/skip")
def skip_connect():
    return {"status": "skipped", "can_continue": True, **_accounts_payload()}


@app.get("/connect/youtube")
def connect_youtube():
    if not youtube_oauth_configured():
        raise HTTPException(
            status_code=503,
            detail="Google OAuth is not configured. Check GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI.",
        )
    try:
        return RedirectResponse(youtube_authorization_url(), status_code=302)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/oauth/youtube/callback")
def youtube_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return RedirectResponse(f"{PUBLIC_FRONTEND_URL}?youtube=denied", status_code=302)
    if not code or not state:
        raise HTTPException(status_code=400, detail="Google callback is missing code or state.")
    try:
        exchange_youtube_callback(code, state)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(f"{PUBLIC_FRONTEND_URL}?youtube=connected", status_code=302)


@app.post("/disconnect/youtube")
def youtube_disconnect():
    disconnect_youtube()
    return {"status": "disconnected", **_accounts_payload()}


def _youtube_upload_item(item_id: str = None):
    if not CONTENT_BANK.exists():
        raise HTTPException(status_code=404, detail="Generate a campaign before uploading.")
    with open(CONTENT_BANK, "r", encoding="utf-8") as f:
        bank = json.load(f)
    candidates = [
        item for item in bank.get("items", [])
        if item.get("assigned_platform") == "youtube_shorts"
    ]
    if item_id:
        candidates = [item for item in candidates if item.get("id") == item_id]
    else:
        candidates = [item for item in candidates if _is_publishable(item)]
    if not candidates:
        raise HTTPException(status_code=404, detail="No matching YouTube Short found.")
    return bank, candidates[0]


def _approved_youtube_path(item: dict) -> Path:
    raw = item.get("platform_video_file") or item.get("video_file")
    if not raw:
        raise HTTPException(status_code=404, detail="This item has no rendered video.")
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    output_root = (PROJECT_ROOT / "output").resolve()
    try:
        path.relative_to(output_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Only rendered campaign files can be uploaded.")
    if not path.exists() or path.suffix.lower() != ".mp4":
        raise HTTPException(status_code=404, detail="Rendered MP4 is missing.")
    return path


@app.post("/youtube/upload")
def youtube_upload(req: YouTubeUploadRequest):
    status = youtube_connection_status()
    if not status.get("connected"):
        raise HTTPException(status_code=401, detail="Connect YouTube before uploading.")
    bank, item = _youtube_upload_item(req.item_id)
    if not _is_publishable(item):
        raise HTTPException(
            status_code=409,
            detail="This clip is not scheduled. Set it to Scheduled in the library first.",
        )
    path = _approved_youtube_path(item)
    variants = item.get("variants") or []
    active = next(
        (variant for variant in variants if variant.get("id") == item.get("active_variant", "A")),
        variants[0] if variants else {},
    )
    hook = active.get("hook") or item.get("hook") or path.stem
    title = hook if "#shorts" in hook.lower() else f"{hook} #Shorts"
    description = active.get("caption") or item.get("summary") or ""
    try:
        result = upload_youtube_video(
            path,
            title=title,
            description=description,
            privacy_status=req.privacy_status,
            made_for_kids=req.made_for_kids,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"YouTube upload failed: {exc}")

    for row in bank.get("items", []):
        if row.get("id") == item.get("id"):
            row["status"] = "posted"
            row["platform_post_id"] = result["video_id"]
            row["platform_post_url"] = result["url"]
            row["posted_at"] = result["uploaded_at"]
            break
    with open(CONTENT_BANK, "w", encoding="utf-8") as f:
        json.dump(bank, f, indent=2, ensure_ascii=False)
    return {"status": "uploaded", "item_id": item.get("id"), **result}


@app.get("/connect/{platform}")
def connect_platform(platform: str):
    key = (platform or "").strip().lower()
    if key == "youtube":
        return connect_youtube()
    if key not in ("instagram", "linkedin", "twitter"):
        raise HTTPException(status_code=404, detail="Unknown platform.")
    if not social_oauth_configured(key):
        raise HTTPException(
            status_code=503,
            detail=(
                f"{key.title()} OAuth is not configured. "
                "Add the app id, secret, and redirect URI to .env, restart the server, then try Connect again."
            ),
        )
    try:
        return RedirectResponse(social_authorization_url(key), status_code=302)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/oauth/{platform}/callback")
def social_callback(platform: str, code: str = "", state: str = "", error: str = ""):
    key = (platform or "").strip().lower()
    if key == "youtube":
        return youtube_callback(code=code, state=state, error=error)
    if key not in ("instagram", "linkedin", "twitter"):
        raise HTTPException(status_code=404, detail="Unknown platform.")
    if error:
        return RedirectResponse(f"{PUBLIC_FRONTEND_URL}?{key}=denied", status_code=302)
    if not code or not state:
        raise HTTPException(status_code=400, detail="OAuth callback is missing code or state.")
    try:
        exchange_social_callback(key, code, state)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(f"{PUBLIC_FRONTEND_URL}?{key}=connected", status_code=302)


@app.post("/disconnect/{platform}")
def disconnect_platform(platform: str):
    key = (platform or "").strip().lower()
    if key == "youtube":
        disconnect_youtube()
    elif key in ("instagram", "linkedin", "twitter"):
        disconnect_social(key)
    else:
        raise HTTPException(status_code=404, detail="Unknown platform.")
    return {"status": "disconnected", **_accounts_payload()}


@app.post("/process", response_model=ProcessResponse)
def process_video(
    req: ProcessRequest,
    request: Request,
    x_user_email: Optional[str] = Header(default=None, alias="X-User-Email"),
):
    email = _request_email(request, x_user_email=x_user_email)
    brand = req.brand_context or {}
    try:
        campaign_days = int(brand.get("campaign_duration_days") or 30)
    except (TypeError, ValueError):
        campaign_days = 30

    if not can_run_campaign(email, campaign_days):
        allowed = entitled_max_days(email)
        demo_gone = False
        try:
            from utils.billing import free_demo_used, stripe_entitled

            demo_gone = free_demo_used(email) and not stripe_entitled(email)
        except Exception:
            demo_gone = False
        raise HTTPException(
            status_code=402,
            detail={
                "error": "subscription_required" if not demo_gone else "demo_exhausted",
                "message": (
                    "You've used your free demo. Choose a campaign pack in Settings to pay and continue."
                    if demo_gone
                    else (
                        f"Your plan covers up to {allowed}-day campaigns. "
                        f"Upgrade to run a {campaign_days}-day calendar, or pick a shorter duration."
                        if allowed
                        else "Choose a campaign pack (14 / 30 / 45 / 60 days) to generate."
                    )
                ),
                "billing_url": "/app/workspace",
                "campaign_days": campaign_days,
                "max_campaign_days": allowed,
            },
        )

    # Consume free demo when this run is not covered by a paid pack.
    try:
        from utils.billing import mark_free_demo_used, stripe_entitled

        if email and not stripe_entitled(email):
            mark_free_demo_used(email)
    except Exception:
        pass

    existing = job_manager.active_job()
    if existing:
        return ProcessResponse(job_id=existing["job_id"], status=existing["status"])

    job_id = job_manager.create_job(req.source)
    enqueue_job(
        job_id,
        req.source,
        req.content_plan,
        req.brand_context,
        source_start=req.source_start,
        source_end=req.source_end,
    )
    return ProcessResponse(job_id=job_id, status="queued", studio_url="/studio")


@app.get("/status/{job_id}", response_model=StatusResponse)
def get_status(job_id: str):
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    started = job.get("started_at")
    finished = job.get("finished_at")
    if started:
        elapsed = (finished or time.time()) - started
    else:
        elapsed = 0.0
    timing = job.get("timing") or (job.get("result") or {}).get("timing")
    if job["status"] == "running":
        live = timing_snapshot()
        if live.get("steps"):
            timing = live
            elapsed = live.get("total_seconds") or elapsed

    ui = describe_step(job["step"], job["status"])
    scan_progress = None
    progress_file = PROJECT_ROOT / "output" / "scan_progress.json"
    if job["status"] in ("running", "stopping") and progress_file.exists():
        try:
            with open(progress_file, "r", encoding="utf-8") as f:
                json.load(f)
            scan_progress = {"label": ui["step_label"]}
        except (OSError, ValueError):
            scan_progress = None

    return StatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        step=job["step"],
        step_index=ui["step_index"],
        step_label=ui["step_label"],
        progress_percent=ui["progress_percent"],
        steps=ui["steps"],
        error=job.get("error"),
        message=job.get("message"),
        result=job.get("result"),
        elapsed_seconds=round(elapsed, 2) if elapsed else 0,
        elapsed_human=format_duration(elapsed) if elapsed else "0s",
        timing=timing,
        stop_requested=bool(job.get("stop_requested")),
        stop_mode=job.get("stop_mode"),
        scan_progress=scan_progress,
    )


@app.get("/jobs")
def list_jobs():
    return job_manager.list_jobs()


@app.post("/jobs/{job_id}/stop")
def stop_job(job_id: str, req: Optional[StopJobRequest] = None):
    req = req or StopJobRequest()
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") not in ("queued", "running", "stopping"):
        return {
            "job_id": job_id,
            "status": job.get("status"),
            "message": "This campaign is already finished.",
        }
    if req.plan:
        merged = _merge_scope(load_plan(required=False), req.plan)
        save_plan(merged)
        job_manager.set_scope(job_id, req.plan)
    updated = job_manager.request_stop(job_id, req.mode)
    return {
        "job_id": job_id,
        "status": updated.get("status") if updated else "stopping",
        "stop_mode": req.mode,
        "message": (
            "Stopping after the current step, then packaging whatever is already cut."
            if req.mode == "finish_current"
            else "Stop requested. The current slice will finish, then the run winds down."
        ),
    }


@app.post("/jobs/{job_id}/scope")
def reduce_job_scope(job_id: str, req: ScopeJobRequest):
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") not in ("queued", "running", "stopping"):
        raise HTTPException(status_code=409, detail="This campaign is already finished.")
    current = load_plan(required=False) or {}
    merged = _merge_scope(current, req.plan)
    save_plan(merged)
    job_manager.set_scope(job_id, req.plan)
    return {
        "job_id": job_id,
        "status": job.get("status"),
        "plan": load_plan(required=False),
        "message": "That platform is stopped. Later steps will skip it.",
    }


@app.get("/next-scheduled-post")
def next_scheduled_post():
    if not CONTENT_BANK.exists():
        raise HTTPException(status_code=404, detail="Content bank not found")

    with open(CONTENT_BANK, "r", encoding="utf-8") as f:
        data = json.load(f)

    pending = [
        item for item in data["items"]
        if _is_publishable(item)
    ]
    if not pending:
        return {"message": "No pending items to post"}

    pending.sort(key=lambda x: x["scheduled_date"])
    next_item = pending[0]
    return next_item


@app.get("/campaign-summary")
def get_campaign_summary():
    summary_file = PROJECT_ROOT / "output" / "campaign_summary.json"
    if not summary_file.exists():
        raise HTTPException(status_code=404, detail="Campaign summary not found")
    with open(summary_file, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/timing")
def get_timing():
    timing_file = PROJECT_ROOT / "output" / "timing_report.json"
    if not timing_file.exists():
        raise HTTPException(status_code=404, detail="Timing report not found")
    with open(timing_file, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/campaign-calendar")
def get_campaign_calendar(year: Optional[int] = None, month: Optional[int] = None):
    if not CONTENT_BANK.exists():
        raise HTTPException(status_code=404, detail="Campaign calendar not found")
    with open(CONTENT_BANK, "r", encoding="utf-8") as f:
        bank = json.load(f)
    markdown = ""
    calendar_file = PROJECT_ROOT / "output" / "campaign_calendar.md"
    if calendar_file.exists():
        markdown = calendar_file.read_text(encoding="utf-8")
    calendar = calendar_from_bank(bank, year=year, month=month)
    return {
        "calendar_markdown": markdown,
        "calendar": calendar,
        "holds": dict(bank.get("holds") or {}),
    }


SCHEDULE_KEYS = {
    "instagram": "instagram_reels",
    "instagram_reels": "instagram_reels",
    "youtube": "youtube_shorts",
    "youtube_shorts": "youtube_shorts",
    "linkedin": "linkedin",
    "twitter": "twitter",
    "x": "twitter",
    "tiktok": "tiktok",
}


def _read_bank():
    if not CONTENT_BANK.exists():
        raise HTTPException(status_code=404, detail="Generate a campaign before changing the schedule.")
    with open(CONTENT_BANK, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_bank(bank):
    with open(CONTENT_BANK, "w", encoding="utf-8") as f:
        json.dump(bank, f, indent=2, ensure_ascii=False)


def _schedule_payload(bank, year=None, month=None):
    return {
        "holds": dict(bank.get("holds") or {}),
        "calendar": calendar_from_bank(bank, year=year, month=month),
        "items": bank.get("items") or [],
    }


PUBLISHABLE_STATUSES = ("pending", "scheduled", "scheduled_repost")


def _is_publishable(item: dict) -> bool:
    return (item.get("status") or "pending") in PUBLISHABLE_STATUSES


def _item_by_id(bank, item_id):
    for item in bank.get("items") or []:
        if item.get("id") == item_id:
            return item
    return None


@app.post("/schedule/hold")
def hold_platform(req: ScheduleControlRequest):
    key = SCHEDULE_KEYS.get((req.platform or "").strip().lower())
    if not key:
        raise HTTPException(status_code=400, detail="Unknown platform.")
    bank = _read_bank()
    holds = dict(bank.get("holds") or {})
    holds[key] = True
    bank["holds"] = holds
    paused = 0
    for item in bank.get("items") or []:
        if item.get("assigned_platform") != key:
            continue
        if item.get("status") in ("posted", "skipped", "ai_generated"):
            continue
        item["status"] = "paused"
        item["paused_reason"] = "platform_hold"
        paused += 1
    _write_bank(bank)
    return {
        "status": "held",
        "platform": key,
        "paused": paused,
        **_schedule_payload(bank, year=req.year, month=req.month),
    }


@app.post("/schedule/resume")
def resume_platform(req: ScheduleControlRequest):
    key = SCHEDULE_KEYS.get((req.platform or "").strip().lower())
    if not key:
        raise HTTPException(status_code=400, detail="Unknown platform.")
    bank = _read_bank()
    holds = dict(bank.get("holds") or {})
    holds[key] = False
    bank["holds"] = holds
    restored = 0
    for item in bank.get("items") or []:
        if item.get("assigned_platform") != key:
            continue
        if item.get("status") == "paused" and item.get("paused_reason") in (None, "platform_hold"):
            item["status"] = "scheduled"
            item.pop("paused_reason", None)
            restored += 1
    _write_bank(bank)
    return {
        "status": "live",
        "platform": key,
        "restored": restored,
        **_schedule_payload(bank, year=req.year, month=req.month),
    }


@app.post("/schedule/skip/{item_id}")
def skip_scheduled_item(item_id: str, req: Optional[ScheduleControlRequest] = None):
    req = req or ScheduleControlRequest()
    bank = _read_bank()
    found = _item_by_id(bank, item_id)
    if not found:
        raise HTTPException(status_code=404, detail="Scheduled post not found.")
    if found.get("status") == "posted":
        raise HTTPException(status_code=400, detail="This post already went out.")
    found["status"] = "skipped"
    found.pop("paused_reason", None)
    _write_bank(bank)
    return {
        "status": "skipped",
        "item_id": item_id,
        **_schedule_payload(bank, year=req.year, month=req.month),
    }


@app.post("/schedule/pause/{item_id}")
def pause_scheduled_item(item_id: str, req: Optional[ScheduleControlRequest] = None):
    req = req or ScheduleControlRequest()
    bank = _read_bank()
    found = _item_by_id(bank, item_id)
    if not found:
        raise HTTPException(status_code=404, detail="Scheduled post not found.")
    if found.get("status") == "posted":
        raise HTTPException(status_code=400, detail="This post already went out.")
    found["status"] = "paused"
    found["paused_reason"] = "item"
    _write_bank(bank)
    return {
        "status": "paused",
        "item_id": item_id,
        **_schedule_payload(bank, year=req.year, month=req.month),
    }


@app.post("/schedule/resume-item/{item_id}")
def resume_scheduled_item(item_id: str, req: Optional[ScheduleControlRequest] = None):
    req = req or ScheduleControlRequest()
    bank = _read_bank()
    found = _item_by_id(bank, item_id)
    if not found:
        raise HTTPException(status_code=404, detail="Scheduled post not found.")
    if found.get("status") == "posted":
        raise HTTPException(status_code=400, detail="This post already went out.")
    found["status"] = "scheduled"
    found.pop("paused_reason", None)
    _write_bank(bank)
    return {
        "status": "live",
        "item_id": item_id,
        **_schedule_payload(bank, year=req.year, month=req.month),
    }


ITEM_STATUS_ALIASES = {
    "ai_generated": "ai_generated",
    "aigenerated": "ai_generated",
    "generated": "ai_generated",
    "draft": "ai_generated",
    "pending": "ai_generated",
    "needs_approval": "ai_generated",
    "needs_approval_review": "ai_generated",
    "scheduled": "scheduled",
    "approved": "scheduled",
    "approve": "scheduled",
    "scheduled_repost": "scheduled",
    "paused": "paused",
    "review": "paused",
    "needs_review": "paused",
    "needs_review_paused": "paused",
    "posted": "posted",
    "published": "posted",
    "skipped": "skipped",
    "rejected": "skipped",
    "reject": "skipped",
    "wont_post": "skipped",
    "wontpost": "skipped",
    "cancel": "skipped",
    "cancelled": "skipped",
    "canceled": "skipped",
}


def _canonical_item_status(raw: str) -> str:
    key = (raw or "").strip().lower().replace(" ", "_").replace("-", "_").replace("'", "")
    mapped = ITEM_STATUS_ALIASES.get(key)
    if not mapped:
        raise HTTPException(status_code=400, detail="Unknown post status.")
    return mapped


def _apply_item_status(item: dict, status: str) -> str:
    canonical = _canonical_item_status(status)
    if canonical == "paused":
        item["status"] = "paused"
        item["paused_reason"] = item.get("paused_reason") or "item"
    elif canonical == "posted":
        item["status"] = "posted"
        item.pop("paused_reason", None)
        item.setdefault("posted_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    elif canonical == "skipped":
        item["status"] = "skipped"
        item.pop("paused_reason", None)
    elif canonical == "ai_generated":
        item["status"] = "ai_generated"
        item.pop("paused_reason", None)
    else:
        item["status"] = "scheduled"
        item.pop("paused_reason", None)
    return canonical


@app.post("/schedule/status/{item_id}")
def set_scheduled_item_status(item_id: str, req: ScheduleStatusRequest):
    bank = _read_bank()
    found = _item_by_id(bank, item_id)
    if not found:
        raise HTTPException(status_code=404, detail="Scheduled post not found.")
    canonical = _apply_item_status(found, req.status)
    _write_bank(bank)
    return {
        "status": canonical,
        "item_id": item_id,
        **_schedule_payload(bank, year=req.year, month=req.month),
    }


@app.post("/review/bulk")
def review_bulk(req: ReviewBulkRequest):
    """Approve or reject many AI draft clips in one pass (HITL review board)."""
    bank = _read_bank()
    items = bank.get("items") or []
    if not items:
        raise HTTPException(status_code=404, detail="No campaign items to review.")
    target_status = "scheduled" if req.action == "approve" else "skipped"
    ids = {str(i) for i in (req.item_ids or []) if i}
    touched = []
    for item in items:
        item_id = str(item.get("id") or "")
        if ids and item_id not in ids:
            continue
        if not ids:
            status = (item.get("status") or "").lower()
            if status not in {"ai_generated", "pending", "draft", ""}:
                continue
        _apply_item_status(item, target_status)
        touched.append(item_id)
    if not touched:
        raise HTTPException(status_code=400, detail="No matching items to review.")
    _write_bank(bank)
    return {
        "action": req.action,
        "updated": touched,
        "count": len(touched),
        **_schedule_payload(bank, year=req.year, month=req.month),
    }


@app.get("/download-campaign/{job_id}")
def download_campaign(job_id: str):
    job = job_manager.get(job_id)
    if job is None or job["status"] not in ("completed", "stopped"):
        raise HTTPException(status_code=404, detail="Campaign not ready or not found")

    zip_path = job["result"].get("campaign_zip")
    if not zip_path or not Path(zip_path).exists():
        raise HTTPException(status_code=404, detail="Campaign zip not found")

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"campaign_{job_id[:8]}.zip"
    )


@app.get("/strategy-brief")
def get_strategy_brief():
    brief_file = PROJECT_ROOT / "output" / "strategy_brief.txt"
    if not brief_file.exists():
        raise HTTPException(status_code=404, detail="Strategy brief not found")
    with open(brief_file, "r", encoding="utf-8") as f:
        return {"strategy_brief": f.read()}


@app.post("/mark-posted/{clip_id}")
def mark_posted(clip_id: str):
    with open(CONTENT_BANK, "r", encoding="utf-8") as f:
        data = json.load(f)

    for item in data["items"]:
        if item["id"] == clip_id:
            item["status"] = "posted"

    with open(CONTENT_BANK, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return {"status": "updated", "id": clip_id}


@app.post("/recommend-plan")
def recommend_plan(req: RecommendPlanRequest):
    try:
        plan = recommend(req.as_brand_context())
        return {"content_plan": plan}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/platform-specs")
def platform_specs():
    return {
        "platforms": PLATFORM_SPECS,
        "candidate_target_seconds": list(CANDIDATE_TARGET_SECONDS),
        "suggested_lengths": {
            "instagram_reels": "15-45s",
            "youtube_shorts": "30-60s",
            "linkedin": "500-1200 words",
            "twitter": "5-15 tweets",
        },
    }


@app.get("/package-manifest")
def package_manifest():
    manifest_file = PROJECT_ROOT / "output" / "package_manifest.json"
    if not manifest_file.exists():
        raise HTTPException(status_code=404, detail="Package manifest not found")
    with open(manifest_file, "r", encoding="utf-8") as f:
        return json.load(f)


@app.post("/performance/{item_id}")
def record_clip_performance(item_id: str, req: PerformanceRequest):
    try:
        metrics = req.model_dump(exclude_none=True) if hasattr(req, "model_dump") else req.dict(exclude_none=True)
        variant_id = metrics.pop("variant_id", None)
        item = save_performance(item_id, metrics, variant_id=variant_id)
        return {"status": "updated", "item": item}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Content bank not found")
    except KeyError:
        raise HTTPException(status_code=404, detail="Item not found")


@app.get("/winners")
def get_winners():
    try:
        return {"winners": list_winners()}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Content bank not found")


@app.post("/repost/{item_id}")
def repost_winner(item_id: str, req: RepostRequest = RepostRequest()):
    try:
        clone = schedule_repost(
            item_id,
            platform=req.platform,
            days=req.days,
        )
        return {"status": "scheduled", "item": clone}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Content bank not found")
    except KeyError:
        raise HTTPException(status_code=404, detail="Item not found")
