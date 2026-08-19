from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import json
import time
from pathlib import Path
from urllib.parse import unquote
from api.schemas import (
    ProcessRequest,
    ProcessResponse,
    StatusResponse,
    PerformanceRequest,
    RepostRequest,
    RecommendPlanRequest,
    YouTubeUploadRequest,
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
from utils.youtube_oauth import (
    authorization_url as youtube_authorization_url,
    configured as youtube_oauth_configured,
    connection_status as youtube_connection_status,
    disconnect as disconnect_youtube,
    exchange_callback as exchange_youtube_callback,
    upload_video as upload_youtube_video,
)

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
CONTENT_BANK = PROJECT_ROOT / "output" / "content_bank.json"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
MEDIA_FOLDERS = {
    "final_shorts", "youtube_shorts", "instagram_reels", "tiktok", "posts",
}

DISCONNECTED_ACCOUNTS = [
    {"platform": "instagram", "label": "Instagram", "status": "not_connected", "connected": False},
    {"platform": "linkedin", "label": "LinkedIn", "status": "not_connected", "connected": False},
    {"platform": "twitter", "label": "Twitter/X", "status": "not_connected", "connected": False},
]


@app.on_event("startup")
def startup_event():
    start_worker()


@app.get("/")
def root():
    return {"status": "ok", "service": "creatoros"}


@app.get("/health")
def health():
    return JSONResponse({"status": "ok"})


@app.get("/studio")
@app.get("/studio/")
def studio():
    index = FRONTEND_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Studio UI is missing")
    return FileResponse(index, media_type="text/html")


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
        row["display_angle"] = chosen.get("angle") or item.get("content_angle")
        row["variant_id"] = chosen.get("id") or item.get("active_variant") or "A"
        row["same_moment"] = bool(also_on)
        row["also_on"] = also_on
        row["package_label"] = package_label
        items.append(row)
    return items


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
    return {
        "summary": summary,
        "plan": bank.get("requested_plan"),
        "total_allocated": bank.get("total_allocated", len(items)),
        "video_renders": bank.get("video_renders"),
        "videos_ready": videos_ready,
        "scan": scan,
        "analysis_mode": summary.get("analysis_mode") or (
            "audio_visual" if scan.get("visual_analysis") else "audio_first"
        ),
        "items": items,
    }


def _accounts_payload():
    youtube = youtube_connection_status()
    accounts = [youtube, *DISCONNECTED_ACCOUNTS]
    return {
        "accounts": accounts,
        "connected": any(account.get("connected") for account in accounts),
        "can_skip": True,
        "message": (
            "YouTube connected. You can upload an approved Short."
            if youtube.get("connected")
            else "No accounts linked. Connect YouTube or generate a downloadable campaign package."
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
        return RedirectResponse("/studio?youtube=denied", status_code=302)
    if not code or not state:
        raise HTTPException(status_code=400, detail="Google callback is missing code or state.")
    try:
        exchange_youtube_callback(code, state)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse("/studio?youtube=connected", status_code=302)


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
@app.post("/connect/{platform}")
def connect_stub(platform: str):
    raise HTTPException(
        status_code=501,
        detail=(
            f"{platform} OAuth is not implemented yet. "
            "Do not mark this account connected; the user can skip this platform."
        ),
    )


@app.post("/process", response_model=ProcessResponse)
def process_video(req: ProcessRequest):
    existing = job_manager.active_job()
    if existing:
        return ProcessResponse(job_id=existing["job_id"], status=existing["status"])

    job_id = job_manager.create_job(req.source)
    enqueue_job(job_id, req.source, req.content_plan, req.brand_context)
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

    return StatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        step=job["step"],
        step_index=ui["step_index"],
        step_label=ui["step_label"],
        progress_percent=ui["progress_percent"],
        steps=ui["steps"],
        error=job["error"],
        result=job["result"],
        elapsed_seconds=round(elapsed, 2) if elapsed else 0,
        elapsed_human=format_duration(elapsed) if elapsed else "0s",
        timing=timing,
    )


@app.get("/jobs")
def list_jobs():
    return job_manager.list_jobs()


@app.get("/next-scheduled-post")
def next_scheduled_post():
    if not CONTENT_BANK.exists():
        raise HTTPException(status_code=404, detail="Content bank not found")

    with open(CONTENT_BANK, "r", encoding="utf-8") as f:
        data = json.load(f)

    pending = [item for item in data["items"] if item["status"] in ("pending", "scheduled_repost")]
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
def get_campaign_calendar():
    calendar_file = PROJECT_ROOT / "output" / "campaign_calendar.md"
    if not calendar_file.exists():
        raise HTTPException(status_code=404, detail="Campaign calendar not found")
    with open(calendar_file, "r", encoding="utf-8") as f:
        return {"calendar_markdown": f.read()}


@app.get("/download-campaign/{job_id}")
def download_campaign(job_id: str):
    job = job_manager.get(job_id)
    if job is None or job["status"] != "completed":
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
