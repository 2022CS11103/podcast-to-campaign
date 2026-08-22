"""
Canonical rules for how long each piece of content should be,
which platforms it belongs on, and roughly what a job costs.

This is the source of truth the clip selector, ranker, router,
and cost estimator all read from — so duration / mix / pricing
decisions stay consistent instead of being hardcoded in scripts.
"""

# Platforms that require a rendered vertical video file.
VIDEO_PLATFORMS = ("youtube_shorts", "instagram_reels", "tiktok")

# Platforms that reuse clip insights as text (no extra video render).
TEXT_PLATFORMS = ("linkedin", "twitter", "blog", "newsletter")

# Always produced once per long-form source, not allocated per-clip.
PILLAR_OUTPUTS = ("blog", "newsletter")

PLATFORM_SPECS = {
    "youtube_shorts": {
        "label": "YouTube Shorts",
        "format": "vertical_video",
        "min_seconds": 30,
        "ideal_seconds": 45,
        "max_seconds": 60,
        "hook_seconds": 3,
        "why": "Retention drops after ~40s unless the payoff is a tutorial. Hook must land before the 3s replay button.",
        "posting_cadence_days": 3,
    },
    "instagram_reels": {
        "label": "Instagram Reels",
        "format": "vertical_video",
        "min_seconds": 15,
        "ideal_seconds": 30,
        "max_seconds": 45,
        "hook_seconds": 2,
        "why": "Reels distribution favors 15–30s. Longer only if the clip is a tight educational framework.",
        "posting_cadence_days": 3,
    },
    "tiktok": {
        "label": "TikTok",
        "format": "vertical_video",
        "min_seconds": 12,
        "ideal_seconds": 25,
        "max_seconds": 45,
        "hook_seconds": 1.5,
        "why": "First 1–2 seconds decide the loop. Prefer a question or bold claim on screen immediately.",
        "posting_cadence_days": 2,
    },
    "linkedin": {
        "label": "LinkedIn",
        "format": "text_post",
        "min_words": 500,
        "ideal_words": 800,
        "max_words": 1200,
        "why": "Thought-leadership posts in the 120–200 word range get more dwell time than dump-and-hashtag.",
        "posting_cadence_days": 7,
    },
    "twitter": {
        "label": "X / Twitter",
        "format": "thread",
        "min_tweets": 5,
        "ideal_tweets": 8,
        "max_tweets": 15,
        "why": "A 5–7 tweet thread from one insight outperforms a single clip dump. Lead tweet is the hook.",
        "posting_cadence_days": 4,
    },
    "blog": {
        "label": "SEO blog",
        "format": "article",
        "min_words": 900,
        "ideal_words": 1200,
        "max_words": 1500,
        "why": "One pillar article per talk, targeting a searchable course/topic keyword. Shorts do not rank; this does.",
        "posting_cadence_days": 30,
    },
    "newsletter": {
        "label": "Newsletter",
        "format": "email",
        "min_words": 220,
        "ideal_words": 320,
        "max_words": 450,
        "why": "One email per talk. Warm recap + one clip CTA + course link. Not a transcript dump.",
        "posting_cadence_days": 14,
    },
}

# Candidate windows the parser will try to cut on. Each talk is sliced
# toward these targets, then scored. Ranker maps windows onto platforms.
CANDIDATE_TARGET_SECONDS = (20, 35, 50)
CANDIDATE_MIN_SECONDS = 12
CANDIDATE_MAX_SECONDS = 60
# Hard cap on Gemini analysis calls per job (cost control).
MAX_ANALYZED_CANDIDATES = 12

# Scan stops once this many unique moments look "good enough".
# Ranker still takes the top unique renders even if some sit below this.
MIN_OVERALL_SCORE = 60

# Ranker will not keep a clip below this unless it is the only option.
USABLE_SCORE_FLOOR = 48

# Encode distinct moments for Shorts vs Reels when we can.
# 2 Shorts + 3 Reels → try 5 unique cuts, cap so a 1-hour talk stays cheap.
MAX_UNIQUE_RENDERS = 5

# Transcribe/score the talk in slices. Stop as soon as enough
# unique clips clear MIN_OVERALL_SCORE — no need to parse a full hour.
SCAN_WINDOW_SECONDS = 60
# Overlap so a sentence that straddles a chunk edge is not chopped in half.
SCAN_OVERLAP_SECONDS = 6
# Stop as soon as we have a package — but not if the opening was junk.
MAX_SCAN_SECONDS = 360
# Keep walking later chunks until we find usable moments, then quit.
HARD_MAX_SCAN_SECONDS = 360

# Picture energy is skipped during scan so Whisper can finish a chunk
# and score it immediately. Caption/zoom still use the transcript.
VIDEO_ANALYSIS_ENABLED = False
CANDIDATES_PER_WINDOW = 1

# A/B: three hook/caption variants per clip. Variant A ships first;
# B/C are held for tests or used if A underperforms.
AB_VARIANT_IDS = ("A", "B", "C")

# Repost a winner after this many days on a second platform or with
# the winning variant as the thumbnail/hook.
REPOST_AFTER_DAYS = 14
WINNER_MIN_VIEWS = 500
WINNER_MIN_ENGAGEMENT_RATE = 0.04  # likes+comments / views


def video_platform_keys(plan: dict) -> list:
    return [k for k in plan.keys() if k in VIDEO_PLATFORMS]


def text_platform_keys(plan: dict) -> list:
    return [k for k in plan.keys() if k in TEXT_PLATFORMS]


def video_slot_demand(plan: dict) -> int:
    """How many platform video files to copy (2 Reels + 1 Short = 3)."""
    total = 0
    for k in video_platform_keys(plan):
        try:
            total += int(plan[k].get("count", 0))
        except (TypeError, ValueError):
            pass
    return total


def video_clip_demand(plan: dict) -> int:
    """
    Unique ffmpeg renders. Shorts and Reels should be different moments
    when the talk has enough strong clips, so demand is the sum of video
    slots, capped — not max(platform).
    """
    return min(video_slot_demand(plan), MAX_UNIQUE_RENDERS) or 0


def largest_video_count(plan: dict) -> int:
    counts = []
    for k in video_platform_keys(plan):
        try:
            n = int(plan[k].get("count", 0))
        except (TypeError, ValueError):
            continue
        if n > 0:
            counts.append(n)
    return max(counts) if counts else 0


def duration_fit(duration_seconds: float, platform: str) -> float:
    """
    0–1 score of how well a clip length matches a platform.
    Used by the ranker so a 55s explainer is not sent to Reels.
    """
    spec = PLATFORM_SPECS.get(platform) or {}
    lo = spec.get("min_seconds")
    hi = spec.get("max_seconds")
    ideal = spec.get("ideal_seconds")
    if lo is None or hi is None or ideal is None:
        return 0.5
    if duration_seconds < lo or duration_seconds > hi:
        return 0.0
    # triangular peak at ideal
    span = max(ideal - lo, hi - ideal, 1)
    return max(0.0, 1.0 - abs(duration_seconds - ideal) / span)


def platforms_for_duration(duration_seconds: float) -> list:
    return [
        p
        for p in VIDEO_PLATFORMS
        if duration_fit(duration_seconds, p) > 0
    ]
