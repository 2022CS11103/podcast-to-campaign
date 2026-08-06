import queue
import threading
import subprocess
import sys
import json
from pathlib import Path
import shutil
from agents.orchestrator import CreatorOS
from api.job_manager import job_manager
from utils.cost_tracker import generate_report, reset_log

PROJECT_ROOT = Path(__file__).resolve().parent.parent

task_queue = queue.Queue()


def _worker():
    while True:
        job_id, source, content_plan, brand_context = task_queue.get()
        try:
            reset_log()

            if brand_context:
                brand_file = PROJECT_ROOT / "brand_context.json"
                with open(brand_file, "w", encoding="utf-8") as f:
                    json.dump(brand_context, f, indent=2)

            job_manager.update(job_id, step="strategy")
            subprocess.run(
                [sys.executable, "scripts/ai/strategy_agent.py"],
                check=True,
                cwd=str(PROJECT_ROOT)
            )

            job_manager.update(job_id, status="running", step="video")


            if content_plan:
                plan_file = PROJECT_ROOT / "content_plan.json"
                with open(plan_file, "w", encoding="utf-8") as f:
                    json.dump(content_plan, f, indent=2)

            if brand_context:
                brand_file = PROJECT_ROOT / "brand_context.json"
                with open(brand_file, "w", encoding="utf-8") as f:
                    json.dump(brand_context, f, indent=2)

            job_manager.update(job_id, status="running", step="video")
            creator = CreatorOS()

            job_manager.update(job_id, step="video")
            creator.video.run(source)

            job_manager.update(job_id, step="transcript")
            creator.transcript.run()

            job_manager.update(job_id, step="highlight")
            creator.highlight.run()

            job_manager.update(job_id, step="trimming")
            subprocess.run(
                [sys.executable, "scripts/ai/trim_clips.py"],
                check=True,
                cwd=str(PROJECT_ROOT)
            )


            job_manager.update(job_id, step="editing")
            creator.editor.run()

            job_manager.update(job_id, step="marketing")
            creator.marketing.run()

            job_manager.update(job_id, step="routing")
            subprocess.run(
                [sys.executable, "scripts/ai/platform_router.py"],
                check=True,
                cwd=str(PROJECT_ROOT)
            )

            job_manager.update(job_id, step="planning")
            subprocess.run(
                [sys.executable, "scripts/ai/campaign_planner.py"],
                check=True,
                cwd=str(PROJECT_ROOT)
            )
            subprocess.run(
                [sys.executable, "scripts/ai/campaign_summary.py"],
                check=True,
                cwd=str(PROJECT_ROOT)
            )

            job_manager.update(job_id, step="packaging")
            # purani campaign zips clean kar pehle (taaki recursive growth na ho)
            for old_zip in (PROJECT_ROOT / "output").glob("campaign_*.zip"):
                old_zip.unlink()

            zip_base = PROJECT_ROOT / "output" / f"campaign_{job_id[:8]}"
            shutil.make_archive(str(zip_base), 'zip', str(PROJECT_ROOT / "output"))
            zip_path = str(zip_base) + ".zip"

            cost_report = generate_report()

            result = {
                "clips_path": str(PROJECT_ROOT / "output" / "clips.json"),
                "shorts_folder": str(PROJECT_ROOT / "output" / "final_shorts"),
                "marketing_folder": str(PROJECT_ROOT / "output"),
                "content_bank": str(PROJECT_ROOT / "output" / "content_bank.json"),
                "campaign_calendar": str(PROJECT_ROOT / "output" / "campaign_calendar.md"),
                "campaign_summary": str(PROJECT_ROOT / "output" / "campaign_summary.json"),
                "strategy_brief": str(PROJECT_ROOT / "output" / "strategy_brief.txt"),
                "campaign_zip": zip_path,
                "cost_report": cost_report,
            }

            job_manager.update(job_id, status="completed", step="done", result=result)

        except Exception as e:
            job_manager.update(job_id, status="failed", error=str(e))
        finally:
            task_queue.task_done()


def start_worker():
    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def enqueue_job(job_id: str, source: str, content_plan: dict = None, brand_context: dict = None):
    task_queue.put((job_id, source, content_plan, brand_context))