from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import json
from pathlib import Path
from api.schemas import ProcessRequest, ProcessResponse, StatusResponse
from api.job_manager import job_manager
from api.pipeline_runner import start_worker, enqueue_job
from fastapi.responses import FileResponse

app = FastAPI(title="CreatorOS API")

@app.on_event("startup")
def startup_event():
    start_worker()

@app.post("/process", response_model=ProcessResponse)
def process_video(req: ProcessRequest):
    job_id = job_manager.create_job(req.source)
    enqueue_job(job_id, req.source)
    return ProcessResponse(job_id=job_id, status="queued")

@app.get("/status/{job_id}", response_model=StatusResponse)
def get_status(job_id: str):
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return StatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        step=job["step"],
        error=job["error"],
        result=job["result"],
    )

@app.get("/jobs")
def list_jobs():
    return job_manager.list_jobs()

@app.get("/health")
def health():
    return JSONResponse({"status": "ok"})

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTENT_BANK = PROJECT_ROOT / "output" / "content_bank.json"

@app.get("/next-scheduled-post")
def next_scheduled_post():
    if not CONTENT_BANK.exists():
        raise HTTPException(status_code=404, detail="Content bank not found")

    with open(CONTENT_BANK, "r", encoding="utf-8") as f:
        data = json.load(f)

    pending = [item for item in data["items"] if item["status"] == "pending"]
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

@app.post("/process", response_model=ProcessResponse)
def process_video(req: ProcessRequest):
    job_id = job_manager.create_job(req.source)
    enqueue_job(job_id, req.source, req.content_plan, req.brand_context)
    return ProcessResponse(job_id=job_id, status="queued")