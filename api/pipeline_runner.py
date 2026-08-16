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
from utils.content_plan import plan_is_usable

PROJECT_ROOT = Path(__file__).resolve().parent.parent

task_queue = queue.Queue()


def _run_script(script: str):
    subprocess.run(
        [sys.executable, script],
        check=True,
        cwd=str(PROJECT_ROOT),
    )


def _worker():
    while True:
        job_id, source, content_plan, brand_context = task_queue.get()
        try:
            reset_log()

            # Clean leftover files from the previous run so this job
            # only ever sees clips it generated itself.
            stale_dirs = [
                PROJECT_ROOT / "output" / "shorts",
                PROJECT_ROOT / "output" / "tracking",
                PROJECT_ROOT / "output" / "final_shorts",
                PROJECT_ROOT / "output" / "vertical_shorts",
                PROJECT_ROOT / "output" / "youtube_shorts",
                PROJECT_ROOT / "output" / "instagram_reels",
                PROJECT_ROOT / "output" / "tiktok",
                PROJECT_ROOT / "output" / "posts",
                PROJECT_ROOT / "output" / "subtitles",
            ]
            for stale_dir in stale_dirs:
                if stale_dir.exists():
                    shutil.rmtree(stale_dir)
                stale_dir.mkdir(parents=True, exist_ok=True)

            if brand_context:
                brand_file = PROJECT_ROOT / "brand_context.json"
                with open(brand_file, "w", encoding="utf-8") as f:
                    json.dump(brand_context, f, indent=2)

            content_plan = content_plan or {}
            content_plan_file = PROJECT_ROOT / "content_plan.json"
            with open(content_plan_file, "w", encoding="utf-8") as f:
                json.dump(content_plan, f, indent=2)

            creator = CreatorOS()

            job_manager.update(job_id, status="running", step="video")
            creator.video.run(source)

            job_manager.update(job_id, step="transcript")
            creator.transcript.run()

            # Score every candidate window. Do not rank yet — we need
            # the campaign plan first so we only render what we'll post.
            job_manager.update(job_id, step="highlight")
            creator.highlight.run()

            job_manager.update(job_id, step="strategy")
            _run_script("scripts/ai/strategy_agent.py")

            job_manager.update(job_id, step="ranking")
            _run_script("scripts/ai/clip_ranker.py")

            job_manager.update(job_id, step="editing")
            creator.editor.run()

            job_manager.update(job_id, step="routing")
            _run_script("scripts/ai/platform_router.py")

            # Marketing runs AFTER routing so each post is written for
            # the platform it was assigned, plus one SEO blog + newsletter.
            job_manager.update(job_id, step="marketing")
            creator.marketing.run()

            job_manager.update(job_id, step="planning")
            _run_script("scripts/ai/campaign_planner.py")
            _run_script("scripts/ai/campaign_summary.py")
            _run_script("scripts/ai/package_manifest.py")

            job_manager.update(job_id, step="packaging")
            for old_zip in (PROJECT_ROOT / "output").glob("campaign_*.zip"):
                old_zip.unlink()

            tmp_zip_base = PROJECT_ROOT / f"campaign_{job_id[:8]}"
            shutil.make_archive(str(tmp_zip_base), "zip", str(PROJECT_ROOT / "output"))

            final_zip_path = PROJECT_ROOT / "output" / f"campaign_{job_id[:8]}.zip"
            shutil.move(str(tmp_zip_base) + ".zip", str(final_zip_path))
            zip_path = str(final_zip_path)

            cost_report = generate_report()

            result = {
                "clips_path": str(PROJECT_ROOT / "output" / "clips.json"),
                "shorts_folder": str(PROJECT_ROOT / "output" / "final_shorts"),
                "marketing_folder": str(PROJECT_ROOT / "output"),
                "content_bank": str(PROJECT_ROOT / "output" / "content_bank.json"),
                "campaign_calendar": str(PROJECT_ROOT / "output" / "campaign_calendar.md"),
                "campaign_summary": str(PROJECT_ROOT / "output" / "campaign_summary.json"),
                "strategy_brief": str(PROJECT_ROOT / "output" / "strategy_brief.txt"),
                "package_manifest": str(PROJECT_ROOT / "output" / "package_manifest.json"),
                "campaign_zip": zip_path,
                "cost_report": cost_report,
                "plan_locked": plan_is_usable(content_plan),
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
