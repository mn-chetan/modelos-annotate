"""Activity Recognition data model."""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class Activity(BaseModel):
    id: str
    video_id: str
    track_id: Optional[str] = None  # May be linked to a specific track or scene-level
    label: str  # e.g., "walking", "running", "interacting_with_object"
    start_frame: int
    end_frame: int
    start_timestamp_ms: float
    end_timestamp_ms: float
    confidence: float = 1.0
    source: str = "activity_recognizer"
    review_status: str = "pending"  # pending, accepted, modified, rejected, rework
    attributes: Dict[str, Any] = Field(default_factory=dict)
