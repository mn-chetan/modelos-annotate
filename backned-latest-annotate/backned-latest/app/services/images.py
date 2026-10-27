"""Image validation helpers."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from os import PathLike
from pathlib import Path

from PIL import Image, ImageFile, ImageOps, UnidentifiedImageError

from app.errors import ValidationAppError

# Mitigate decompression bombs
Image.MAX_IMAGE_PIXELS = 40_000_000
ImageFile.LOAD_TRUNCATED_IMAGES = False

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".avif"}

FMT_TO_TYPE = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
    "AVIF": "image/avif",
}


@dataclass(frozen=True)
class DecodedImage:
    width: int
    height: int
    content_type: str
    data: bytes
    format: str
    orientation: int
    aspect_ratio: float
    content_hash: str
    perceptual_hash: str


def _average_hash(img: Image.Image, hash_size: int = 8) -> str:
    gray = img.convert("L").resize((hash_size, hash_size), Image.Resampling.LANCZOS)
    pixels = [int(gray.getpixel((x, y))) for y in range(hash_size) for x in range(hash_size)]
    avg = sum(pixels) / len(pixels)
    bits = "".join("1" if p >= avg else "0" for p in pixels)
    return f"{int(bits, 2):016x}"


def decode_and_validate_image(
    data: bytes,
    *,
    filename: str,
    content_type: str | None,
    max_bytes: int,
    allowed_types: set[str],
) -> DecodedImage:
    if len(data) > max_bytes:
        raise ValidationAppError(
            f"File exceeds max upload size of {max_bytes} bytes",
            details={"filename": filename, "size": len(data)},
        )
    if len(data) == 0:
        raise ValidationAppError("Empty upload rejected", details={"filename": filename})

    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValidationAppError(
            f"Unsupported file extension {suffix!r}",
            details={"filename": filename, "allowed": sorted(ALLOWED_EXTENSIONS)},
        )

    content_hash = hashlib.sha256(data).hexdigest()
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            orientation = 1
            try:
                exif = img.getexif()
                if exif:
                    orientation = int(exif.get(274, 1) or 1)
            except Exception:  # noqa: BLE001
                orientation = 1
            transposed = ImageOps.exif_transpose(img)
            working = transposed if transposed is not None else img
            width, height = working.size
            fmt = (img.format or "").upper()
            perceptual_hash = _average_hash(working)
            aspect_ratio = float(width) / float(height) if height else 0.0
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationAppError(
            "Unable to decode image; file may be corrupt or unsupported",
            details={"filename": filename, "reason": str(exc)},
        ) from exc

    detected = FMT_TO_TYPE.get(fmt)
    if detected is None or detected not in allowed_types:
        raise ValidationAppError(
            f"Unsupported image format {fmt!r}",
            details={"filename": filename, "format": fmt},
        )
    if content_type and content_type not in allowed_types and content_type != "application/octet-stream":
        # Prefer detected type; soft-check client content-type
        pass

    return DecodedImage(
        width=width,
        height=height,
        content_type=detected,
        data=data,
        format=fmt,
        orientation=orientation,
        aspect_ratio=aspect_ratio,
        content_hash=content_hash,
        perceptual_hash=perceptual_hash,
    )


def write_jpeg_preview(
    source: PathLike[str] | str | bytes,
    dest_path: PathLike[str] | str,
    *,
    max_edge: int = 512,
) -> None:
    """Write a JPEG preview suitable for queue thumbnails across formats including AVIF."""
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(source, (bytes, bytearray)):
        opener: io.BytesIO | Path = io.BytesIO(source)
    else:
        opener = Path(source)
    with Image.open(opener) as img:
        img = ImageOps.exif_transpose(img) or img
        img = img.convert("RGB")
        img.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        img.save(dest, format="JPEG", quality=85, optimize=True)
