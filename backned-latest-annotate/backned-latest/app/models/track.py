"""Track data model for persistent multi-object tracking."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from app.models.video_detection import VideoDetection


class TrackWaypoint(BaseModel):
    frame_index: int
    bbox: List[float]  # [x, y, w, h]
    confidence: float = 1.0
    interpolated: bool = False
    attributes: Dict[str, Any] = Field(default_factory=dict)


class Track(BaseModel):
    id: str
    video_id: str
    track_id: str  # Human readable or sequential ID e.g. "track_1"
    label: str
    color: str = "#3B82F6"
    start_frame: int
    end_frame: int
    state: str = "active"  # active, lost, terminated
    confidence: float = 1.0
    source: str = "tracker"
    review_status: str = "pending"  # pending, accepted, modified, rejected, rework
    waypoints: List[TrackWaypoint] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
