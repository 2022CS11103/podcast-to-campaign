import json
import uuid
import threading
from datetime import datetime
from pathlib import Path

STOP_FLAG = Path(__file__).resolve().parent.parent / "output" / "job_stop.json"

ACTIVE_STATUSES = ("queued", "running", "stopping")
STOP_MODES = ("finish_current", "now")


class JobManager:
    def __init__(self):
        self._jobs = {}
        self._lock = threading.Lock()

    def create_job(self, source: str) -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "source": source,
                "status": "queued",
                "step": None,
                "error": None,
                "result": None,
                "created_at": datetime.utcnow().isoformat(),
                "stop_requested": False,
                "stop_mode": None,
                "stopped_at_step": None,
                "scope_override": None,
            }
        return job_id

    def update(self, job_id: str, **kwargs):
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(kwargs)

    def get(self, job_id: str):
        with self._lock:
            return self._jobs.get(job_id)

    def active_job(self):
        with self._lock:
            for job in self._jobs.values():
                if job.get("status") in ACTIVE_STATUSES:
                    return job
        return None

    def list_jobs(self, limit: int = 25):
        with self._lock:
            jobs = sorted(
                self._jobs.values(),
                key=lambda job: job.get("created_at") or "",
                reverse=True,
            )
            return [dict(job) for job in jobs[:limit]]

    def clear_stop_flag(self):
        try:
            STOP_FLAG.unlink(missing_ok=True)
        except OSError:
            pass

    def _write_stop_flag(self, job_id: str, mode: str, plan=None):
        STOP_FLAG.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "job_id": job_id,
            "mode": mode,
            "plan": plan,
            "requested_at": datetime.utcnow().isoformat(),
        }
        STOP_FLAG.write_text(json.dumps(payload), encoding="utf-8")

    def request_stop(self, job_id: str, mode: str = "finish_current"):
        """Flag a run to wind down. The worker acts on it at the next step."""
        if mode not in STOP_MODES:
            mode = "finish_current"
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            if job.get("status") not in ACTIVE_STATUSES:
                return dict(job)
            job["stop_requested"] = True
            job["stop_mode"] = mode
            job["stop_requested_at"] = datetime.utcnow().isoformat()
            job["status"] = "stopping"
            self._write_stop_flag(job_id, mode, job.get("scope_override"))
            return dict(job)

    def stop_request(self, job_id: str):
        """The stop mode if one is pending, else None. Read by the worker."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or not job.get("stop_requested"):
                return None
            return job.get("stop_mode") or "finish_current"

    def set_scope(self, job_id: str, plan: dict):
        """Reduced platform counts to apply to the rest of the run."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            job["scope_override"] = plan
            job["scope_updated_at"] = datetime.utcnow().isoformat()
            if job.get("stop_requested"):
                self._write_stop_flag(
                    job_id, job.get("stop_mode") or "finish_current", plan
                )
            return dict(job)

    def scope_override(self, job_id: str):
        with self._lock:
            job = self._jobs.get(job_id)
            return (job or {}).get("scope_override")


# single shared instance
job_manager = JobManager()
