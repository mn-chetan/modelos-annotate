"""Inference model adapters."""

from app.inference.adapters.dino import GroundingDinoAdapter
from app.inference.adapters.fake import (
    FakeDinoAdapter,
    FakeFlorenceAdapter,
    FakeSam2Adapter,
    FakeYoloAdapter,
)
from app.inference.adapters.faster_rcnn import FasterRCNNAdapter
from app.inference.adapters.florence import FlorenceAdapter
from app.inference.adapters.sam2 import Sam2Adapter
from app.inference.adapters.yolo26 import Yolo26Adapter

__all__ = [
    "FakeDinoAdapter",
    "FakeFlorenceAdapter",
    "FakeSam2Adapter",
    "FakeYoloAdapter",
    "FasterRCNNAdapter",
    "FlorenceAdapter",
    "GroundingDinoAdapter",
    "Sam2Adapter",
    "Yolo26Adapter",
]
