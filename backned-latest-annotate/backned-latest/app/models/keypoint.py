"""Keypoint Detection data model."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class KeypointItem(BaseModel):
    name: str
    x: float
    y: float
    visibility: int = 2  # 0: invisible, 1: occluded, 2: visible
    confidence: float = 1.0


class KeypointAnnotation(BaseModel):
    id: str
    video_id: str
    frame_index: int
    track_id: Optional[str] = None
    label: str = "person"
    skeleton_type: str = "coco_17"  # coco_17, hand_21, face_68
    keypoints: List[KeypointItem] = Field(default_factory=list)
    confidence: float = 1.0
    source: str = "pose_tracker"
    review_status: str = "pending"  # pending, accepted, modified, rejected, rework
    metadata: Dict[str, Any] = Field(default_factory=dict)
