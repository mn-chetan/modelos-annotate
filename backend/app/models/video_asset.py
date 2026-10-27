"""Video Asset data model."""
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class VideoAsset(BaseModel):
    id: str
    name: str
    file_path: str
    fps: float = 30.0
    duration: float = 0.0
    width: int = 1920
    height: int = 1080
    total_frames: int = 0
    codec: Optional[str] = "h264"
    format: Optional[str] = "mp4"
    file_size_bytes: int = 0
    status: str = "uploaded"  # uploaded, processing, ready, error
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
