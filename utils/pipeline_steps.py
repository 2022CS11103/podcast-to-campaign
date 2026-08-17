"""Maps backend job.step names to the 9-step Lovable processing UI."""

UI_STEPS = [
    {"id": "video", "index": 1, "label": "Ingesting the talk"},
    {"id": "transcript", "index": 2, "label": "Listening for standout moments"},
    {"id": "highlight", "index": 3, "label": "Editor scoring hooks"},
    {"id": "ranking", "index": 4, "label": "Picking distinct Shorts vs Reels"},
    {"id": "editing", "index": 5, "label": "Cutting vertical edits"},
    {"id": "routing", "index": 6, "label": "Routing to each platform"},
    {"id": "marketing", "index": 7, "label": "Writing captions like a strategist"},
    {"id": "planning", "index": 8, "label": "Building the posting calendar"},
    {"id": "packaging", "index": 9, "label": "Packaging the campaign kit"},
]

# strategy/ranking both sit on UI step 4 (Highlight Detection)
STEP_TO_INDEX = {
    "video": 1,
    "transcript": 2,
    "highlight": 3,
    "strategy": 4,
    "ranking": 4,
    "editing": 5,
    "routing": 6,
    "marketing": 7,
    "planning": 8,
    "packaging": 9,
    "done": 9,
}


def describe_step(step: str, status: str):
    if status == "queued" or not step:
        active = 0
    elif status == "completed" or step == "done":
        active = 9
    else:
        active = STEP_TO_INDEX.get(step, 1)

    if status == "completed":
        percent = 100
    elif active <= 0:
        percent = 0
    else:
        percent = int(round((active - 1) / 9 * 100 + (100 / 9) * 0.45))

    steps = []
    for item in UI_STEPS:
        idx = item["index"]
        if status == "failed" and idx == max(active, 1):
            state = "error"
        elif status == "completed" or idx < active:
            state = "done"
        elif idx == active:
            state = "active"
        else:
            state = "pending"
        steps.append({**item, "status": state})

    active_meta = next((s for s in UI_STEPS if s["index"] == active), None)
    return {
        "step_index": active,
        "step_label": (active_meta or {}).get("label"),
        "progress_percent": min(percent, 100 if status == "completed" else 99),
        "steps": steps,
    }
