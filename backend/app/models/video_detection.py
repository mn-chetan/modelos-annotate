"""Video Detection data model."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class VideoDetection(BaseModel):
    id: str
    video_id: str
    frame_index: int
    bbox: List[float]  # [x, y, width, height] normalized or pixel coords
    label: str
    confidence: float = 1.0
    track_id: Optional[str] = None
    source: str = "manual"  # manual, yolo26, grounding_dino, etc.
    attributes: Dict[str, Any] = Field(default_factory=dict)
    review_status: str = "pending"  # pending, accepted, modified, rejected, rework
