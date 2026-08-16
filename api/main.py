from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import json
import time
from pathlib import Path
from api.schemas import (
    ProcessRequest,
    ProcessResponse,
    StatusResponse,
    PerformanceRequest,
    RepostRequest,
    RecommendPlanRequest,
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

DISCONNECTED_ACCOUNTS = [
    {"platform": "youtube", "label": "YouTube", "status": "not_connected", "connected": False},
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


def _accounts_payload():
    return {
        "accounts": DISCONNECTED_ACCOUNTS,
        "connected": False,
        "can_skip": True,
        "message": "No accounts linked. Skip and generate a downloadable campaign package.",
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


@app.get("/connect/{platform}")
@app.post("/connect/{platform}")
def connect_stub(platform: str):
    return {
        "status": "not_connected",
        "platform": platform,
        "connected": False,
        "can_skip": True,
        "message": "OAuth is not enabled yet. Skip and continue — Generate works with zero accounts.",
    }


@app.post("/process", response_model=ProcessResponse)
def process_video(req: ProcessRequest):
    job_id = job_manager.create_job(req.source)
    enqueue_job(job_id, req.source, req.content_plan, req.brand_context)
    return ProcessResponse(job_id=job_id, status="queued")


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

    return StatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        step=job["step"],
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
