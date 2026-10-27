"""Event Detection data model."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class Event(BaseModel):
    id: str
    video_id: str
    event_type: str  # e.g., "entry", "exit", "interaction", "collision", "state_change"
    frame_index: int
    timestamp_ms: float
    duration_ms: float = 0.0  # 0 for instant events
    track_ids: List[str] = Field(default_factory=list)
    confidence: float = 1.0
    description: Optional[str] = None
    source: str = "event_detector"
    review_status: str = "pending"  # pending, accepted, modified, rejected, rework
    metadata: Dict[str, Any] = Field(default_factory=dict)
