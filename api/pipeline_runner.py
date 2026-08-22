import queue
import os
import threading
import subprocess
import sys
import json
import time
from pathlib import Path
import shutil
from agents.orchestrator import CreatorOS
from api.job_manager import job_manager
from utils.cost_tracker import generate_report, reset_log
from utils.content_plan import plan_is_usable, normalize_plan
from utils.pipeline_timer import reset as reset_timer, log_step, finish, snapshot, format_duration

PROJECT_ROOT = Path(__file__).resolve().parent.parent

task_queue = queue.Queue()

VIDEO_PLATFORMS = ("youtube_shorts", "instagram_reels", "tiktok")


class JobStopped(Exception):
    """Raised at a checkpoint when the creator asked the run to wind down."""

    def __init__(self, mode: str, stage: str):
        super().__init__(f"stopped before {stage}")
        self.mode = mode
        self.stage = stage


def _public_error(exc: Exception) -> str:
    text = str(exc)
    lowered = text.lower()
    bot = "not a bot" in lowered or "sign in to confirm" in lowered or "bot check" in lowered
    locked = "could not copy chrome cookie database" in lowered
    if bot or locked:
        marker = "YouTube blocked this download"
        if marker in text:
            return text[text.rfind(marker):].strip()[:1200]
        return (
            "YouTube blocked the download (bot check). "
            "Open Firefox, log into youtube.com, then Try Again. "
            "Keep Firefox open — Chrome/Edge can stay open. "
            "Chrome/Edge cookies cannot be read on Windows while those browsers are running."
        )
    return text

INTERMEDIATE_DIRS = [
    "shorts",
    "tracking",
    "vertical_shorts",
    "subtitles",
]
RENDER_DIRS = [
    "final_shorts",
    "youtube_shorts",
    "instagram_reels",
    "tiktok",
    "posts",
]


def _wipe_output_dirs(names):
    for name in names:
        stale = PROJECT_ROOT / "output" / name
        if stale.exists():
            shutil.rmtree(stale)


def _run_script(script: str):
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "PYTHONUNBUFFERED": "1",
    }
    result = subprocess.run(
        [sys.executable, "-u", script],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n", flush=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"{script} failed:\n{detail[-2500:]}")


def _timed(job_id, name, fn):
    job_manager.update(job_id, step=name, timing=snapshot())
    print(f"\n⏱  {name} started")
    t0 = time.time()
    ok = True
    try:
        return fn()
    except Exception:
        ok = False
        raise
    finally:
        elapsed = time.time() - t0
        timing = log_step(name, elapsed, ok=ok)
        print(f"⏱  {name} finished in {format_duration(elapsed)}")
        job_manager.update(job_id, timing=timing)


def _checkpoint(job_id, stage):
    """Wind down here if a stop was requested during the previous stage."""
    mode = job_manager.stop_request(job_id)
    if mode:
        print(f"\n🛑 stop requested ({mode}) — winding down before {stage}")
        raise JobStopped(mode, stage)


def _write_plan(plan: dict) -> dict:
    plan = normalize_plan(plan or {})
    with open(PROJECT_ROOT / "content_plan.json", "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)
    return plan


def _reduce_plan(plan: dict, override: dict) -> dict:
    """Apply a scope change, allowing reductions only.

    Raising counts mid-run would need clips that were never cut, so a bigger
    number is treated as "leave it alone".
    """
    if not override:
        return plan
    revised = {}
    for platform, config in (plan or {}).items():
        wanted = (override or {}).get(platform)
        count = int(config.get("count", 0) or 0)
        if isinstance(wanted, dict) and wanted.get("count") is not None:
            try:
                count = min(count, max(0, int(wanted["count"])))
            except (TypeError, ValueError):
                pass
        elif isinstance(wanted, (int, float, str)):
            try:
                count = min(count, max(0, int(wanted)))
            except (TypeError, ValueError):
                pass
        revised[platform] = {**config, "count": count}
    return normalize_plan(revised)


def _apply_scope(job_id, plan):
    override = job_manager.scope_override(job_id)
    if not override:
        return plan
    reduced = _reduce_plan(plan, override)
    if reduced != plan:
        print(f"\n✂  scope reduced mid-run: "
              f"{ {k: v['count'] for k, v in reduced.items()} }")
        return _write_plan(reduced)
    return plan


def _rendered_shorts():
    folder = PROJECT_ROOT / "output" / "final_shorts"
    return sorted(folder.glob("short_*.mp4")) if folder.exists() else []


def _cap_plan_to_renders(plan):
    """A stopped run publishes what it actually cut, not what it promised."""
    renders = len(_rendered_shorts())
    revised = {}
    for platform, config in (plan or {}).items():
        count = int(config.get("count", 0) or 0)
        if platform in VIDEO_PLATFORMS:
            count = min(count, renders)
        revised[platform] = {**config, "count": count}
    return normalize_plan(revised)


def _package(job_id):
    for old_zip in (PROJECT_ROOT / "output").glob("campaign_*.zip"):
        old_zip.unlink()
    tmp_zip_base = PROJECT_ROOT / f"campaign_{job_id[:8]}"
    shutil.make_archive(str(tmp_zip_base), "zip", str(PROJECT_ROOT / "output"))
    final_zip_path = PROJECT_ROOT / "output" / f"campaign_{job_id[:8]}.zip"
    shutil.move(str(tmp_zip_base) + ".zip", str(final_zip_path))
    return str(final_zip_path)


def _build_result(zip_path, timing, content_plan, stopped_at=None):
    result = {
        "clips_path": str(PROJECT_ROOT / "output" / "clips.json"),
        "shorts_folder": str(PROJECT_ROOT / "output" / "final_shorts"),
        "marketing_folder": str(PROJECT_ROOT / "output"),
        "content_bank": str(PROJECT_ROOT / "output" / "content_bank.json"),
        "campaign_calendar": str(PROJECT_ROOT / "output" / "campaign_calendar.md"),
        "campaign_summary": str(PROJECT_ROOT / "output" / "campaign_summary.json"),
        "strategy_brief": str(PROJECT_ROOT / "output" / "strategy_brief.txt"),
        "package_manifest": str(PROJECT_ROOT / "output" / "package_manifest.json"),
        "timing_report": str(PROJECT_ROOT / "output" / "timing_report.json"),
        "edit_quality": str(PROJECT_ROOT / "output" / "edit_quality.json"),
        "campaign_zip": zip_path,
        "studio_url": "/studio",
        "cost_report": generate_report(),
        "timing": timing,
        "elapsed_seconds": timing["total_seconds"],
        "elapsed_human": timing["total_human"],
        "plan_locked": plan_is_usable(content_plan),
    }
    if stopped_at:
        result["stopped_at_step"] = stopped_at
        result["partial"] = True
    return result


def _wind_down(job_id, stopped: JobStopped, content_plan, done_stages):
    """Publish what the run already produced instead of throwing it away."""
    shorts = _rendered_shorts()
    if stopped.mode == "now" or not shorts:
        reason = (
            "Stopped before any clip finished rendering, so there is nothing to publish."
            if not shorts else
            "Run cancelled. Nothing was published."
        )
        timing = finish(ok=False)
        job_manager.update(
            job_id,
            status="stopped",
            step=stopped.stage,
            stopped_at_step=stopped.stage,
            error=None,
            message=reason,
            timing=timing,
            finished_at=time.time(),
        )
        print(f"\n🛑 {reason}")
        return

    print(f"\n🛑 wrapping up with {len(shorts)} finished cut(s)")
    plan = _write_plan(_cap_plan_to_renders(content_plan))
    try:
        if "routing" not in done_stages:
            _timed(job_id, "routing", lambda: _run_script("scripts/ai/platform_router.py"))
        if "marketing" not in done_stages:
            _timed(job_id, "marketing", CreatorOS().marketing.run)
        if "planning" not in done_stages:
            _timed(job_id, "planning", lambda: (
                _run_script("scripts/ai/campaign_planner.py"),
                _run_script("scripts/ai/campaign_summary.py"),
                _run_script("scripts/ai/package_manifest.py"),
            ))
        zip_path = _timed(job_id, "packaging", lambda: _package(job_id))
        timing = finish(ok=True)
        result = _build_result(zip_path, timing, plan, stopped_at=stopped.stage)
        job_manager.update(
            job_id,
            status="stopped",
            step="done",
            stopped_at_step=stopped.stage,
            message=(
                f"Stopped early and packaged {len(shorts)} finished cut(s). "
                "Everything already rendered is in the campaign library."
            ),
            result=result,
            timing=timing,
            finished_at=time.time(),
        )
        print(f"\n🛑 stopped early — packaged {len(shorts)} cut(s)")
    except Exception as exc:
        timing = finish(ok=False)
        job_manager.update(
            job_id,
            status="stopped",
            step=stopped.stage,
            stopped_at_step=stopped.stage,
            message="Stopped early. Packaging the partial campaign failed.",
            error=_public_error(exc),
            timing=timing,
            finished_at=time.time(),
        )


def _worker():
    while True:
        job_id, source, content_plan, brand_context = task_queue.get()
        done_stages = set()
        try:
            reset_log()
            reset_timer()
            job_manager.clear_stop_flag()
            job_manager.update(job_id, started_at=time.time(), timing=snapshot())

            # Wipe scratch folders now. Keep last campaign's playable
            # Shorts/Reels until we are about to cut replacements.
            _wipe_output_dirs(INTERMEDIATE_DIRS)

            if brand_context:
                brand_file = PROJECT_ROOT / "brand_context.json"
                with open(brand_file, "w", encoding="utf-8") as f:
                    json.dump(brand_context, f, indent=2)

            content_plan = _write_plan(content_plan)

            creator = CreatorOS()

            job_manager.update(job_id, status="running", step="video")
            stages = [
                ("video", lambda: creator.video.run(source)),
                ("transcript", creator.transcript.run),
                ("highlight", creator.highlight.run),
                ("strategy", lambda: _run_script("scripts/ai/strategy_agent.py")),
                ("ranking", lambda: _run_script("scripts/ai/clip_ranker.py")),
                ("editing", creator.editor.run),
                ("routing", lambda: _run_script("scripts/ai/platform_router.py")),
                ("marketing", creator.marketing.run),
                ("planning", lambda: (
                    _run_script("scripts/ai/campaign_planner.py"),
                    _run_script("scripts/ai/campaign_summary.py"),
                    _run_script("scripts/ai/package_manifest.py"),
                )),
            ]

            for name, fn in stages:
                _checkpoint(job_id, name)
                content_plan = _apply_scope(job_id, content_plan)
                if name == "editing":
                    _wipe_output_dirs(RENDER_DIRS)
                _timed(job_id, name, fn)
                done_stages.add(name)

            _checkpoint(job_id, "packaging")
            zip_path = _timed(job_id, "packaging", lambda: _package(job_id))

            timing = finish(ok=True)
            _run_script("scripts/ai/campaign_summary.py")
            _run_script("scripts/ai/package_manifest.py")
            result = _build_result(zip_path, timing, content_plan)

            print(f"\n⏱  CAMPAIGN TOTAL: {timing['total_human']}")
            for step in timing["steps"]:
                print(f"    {step['step']}: {step['human']}")

            job_manager.update(
                job_id,
                status="completed",
                step="done",
                result=result,
                timing=timing,
                finished_at=time.time(),
            )

        except JobStopped as stopped:
            _wind_down(job_id, stopped, content_plan, done_stages)
        except Exception as e:
            timing = finish(ok=False)
            job_manager.update(
                job_id,
                status="failed",
                error=_public_error(e),
                timing=timing,
                finished_at=time.time(),
            )
        finally:
            task_queue.task_done()


def start_worker():
    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def enqueue_job(job_id: str, source: str, content_plan: dict = None, brand_context: dict = None):
    task_queue.put((job_id, source, content_plan, brand_context))
