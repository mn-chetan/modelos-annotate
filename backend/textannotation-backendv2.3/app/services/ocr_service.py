from __future__ import annotations

from abc import ABC, abstractmethod
from io import BytesIO

from PIL import Image
import pytesseract

from app.core.exceptions import AppError


class OCRService(ABC):
    @abstractmethod
    async def extract_text(self, image_bytes: bytes) -> str:
        raise NotImplementedError


class TesseractOCRService(OCRService):
    async def extract_text(self, image_bytes: bytes) -> str:
        try:
            image = Image.open(BytesIO(image_bytes))
            text = pytesseract.image_to_string(image)
            return text.strip()
        except Exception as exc:  # pragma: no cover - environment dependent
            raise AppError("OCR_FAILURE", f"OCR failed: {exc}", status_code=422) from exc
