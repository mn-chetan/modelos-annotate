"""Video Frame data model."""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class VideoFrame(BaseModel):
    video_id: str
    frame_index: int
    timestamp_ms: float
    timestamp_str: str  # HH:MM:SS:FF format
    is_keyframe: bool = False
    image_url: Optional[str] = None
    file_path: Optional[str] = None
    width: int = 1920
    height: int = 1080
    metadata: Dict[str, Any] = Field(default_factory=dict)
