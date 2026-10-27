"""Segmentation Mask data model."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class SegmentationMask(BaseModel):
    id: str
    video_id: str
    frame_index: int
    track_id: Optional[str] = None
    label: str
    polygon: List[List[float]] = Field(default_factory=list)  # [[x1, y1], [x2, y2], ...]
    mask_rle: Optional[Dict[str, Any]] = None  # COCO RLE format or counts
    color: str = "#10B981"
    confidence: float = 1.0
    source: str = "sam2"  # manual, sam2, etc.
    review_status: str = "pending"  # pending, accepted, modified, rejected, rework
    attributes: Dict[str, Any] = Field(default_factory=dict)
