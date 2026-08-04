import uuid
import threading
from datetime import datetime

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
            }
        return job_id

    def update(self, job_id: str, **kwargs):
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(kwargs)

    def get(self, job_id: str):
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self):
        with self._lock:
            return list(self._jobs.values())

# single shared instance
job_manager = JobManager()