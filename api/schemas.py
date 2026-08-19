from pydantic import BaseModel, ConfigDict, model_validator
from typing import Optional, Dict, Any, Literal


def _pick(data: dict, *keys):
    for key in keys:
        val = data.get(key)
        if val not in (None, ""):
            return val
    return None


class ProcessRequest(BaseModel):
    """Lovable wizard payload. Extra keys are ignored, not rejected."""
    model_config = ConfigDict(extra="allow")

    source: str
    content_plan: Optional[Dict[str, Any]] = None
    brand_context: Optional[Dict[str, Any]] = None
    campaign_start_date: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def coerce_frontend_fields(cls, data):
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if not data.get("source"):
            source = _pick(data, "url", "youtube_url", "video_url", "podcast_url", "file_path")
            if source:
                data["source"] = source
        brand = dict(data.get("brand_context") or {})
        for src, dest in (
            ("brand_name", "brand_name"),
            ("website", "website"),
            ("goal", "goal"),
            ("primary_goal", "goal"),
            ("audience", "audience"),
            ("target_audience", "audience"),
            ("tone", "tone"),
            ("campaign_duration_days", "campaign_duration_days"),
            ("posting_duration_days", "campaign_duration_days"),
            ("campaign_start_date", "campaign_start_date"),
        ):
            if data.get(src) not in (None, "") and dest not in brand:
                brand[dest] = data[src]
        if brand:
            data["brand_context"] = brand
        return data


class ProcessResponse(BaseModel):
    job_id: str
    status: str
    studio_url: Optional[str] = "/studio"


class StatusResponse(BaseModel):
    job_id: str
    status: str
    step: Optional[str] = None
    step_index: Optional[int] = None
    step_label: Optional[str] = None
    progress_percent: Optional[int] = None
    steps: Optional[list] = None
    error: Optional[str] = None
    result: Optional[dict] = None
    elapsed_seconds: Optional[float] = None
    elapsed_human: Optional[str] = None
    timing: Optional[dict] = None


class PerformanceRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    impressions: Optional[int] = None
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    ctr: Optional[float] = None
    variant_id: Optional[str] = None


class RepostRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    platform: Optional[str] = None
    days: Optional[int] = None


class YouTubeUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: Optional[str] = None
    privacy_status: Literal["private", "unlisted", "public"] = "private"
    made_for_kids: bool = False


class RecommendPlanRequest(BaseModel):
    """Accept either a wrapped body or the brand fields at the top level."""
    model_config = ConfigDict(extra="allow")
    brand_context: Optional[Dict[str, Any]] = None
    brand_name: Optional[str] = None
    website: Optional[str] = None
    goal: Optional[str] = None
    audience: Optional[str] = None
    tone: Optional[str] = None
    campaign_duration_days: Optional[int] = None
    campaign_start_date: Optional[str] = None

    def as_brand_context(self) -> dict:
        ctx = dict(self.brand_context or {})
        dump = self.model_dump(exclude_none=True) if hasattr(self, "model_dump") else self.dict(exclude_none=True)
        dump.pop("brand_context", None)
        for k, v in dump.items():
            ctx.setdefault(k, v)
        extras = getattr(self, "model_extra", None) or {}
        for k, v in extras.items():
            if k != "brand_context" and v not in (None, ""):
                ctx.setdefault(k, v)
        return ctx
