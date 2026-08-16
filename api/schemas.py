from pydantic import BaseModel
from typing import Optional, Dict, Any


class ProcessRequest(BaseModel):
    source: str
    content_plan: Optional[Dict[str, Any]] = None
    brand_context: Optional[Dict[str, Any]] = None


class ProcessResponse(BaseModel):
    job_id: str
    status: str


class StatusResponse(BaseModel):
    job_id: str
    status: str
    step: Optional[str] = None
    error: Optional[str] = None
    result: Optional[dict] = None


class PerformanceRequest(BaseModel):
    impressions: Optional[int] = None
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    ctr: Optional[float] = None
    variant_id: Optional[str] = None


class RepostRequest(BaseModel):
    platform: Optional[str] = None
    days: Optional[int] = None
