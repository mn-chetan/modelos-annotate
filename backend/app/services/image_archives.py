"""Safe expansion of image archives for Image Annotation uploads."""

from __future__ import annotations

import io
import stat
import zipfile
from pathlib import PurePosixPath, PureWindowsPath
from typing import Iterator

from PIL import Image, UnidentifiedImageError

from app.errors import ValidationAppError
from app.services.images import ALLOWED_EXTENSIONS
from app.storage.files import normalize_filename


MAX_ARCHIVE_ENTRIES = 10_000
ARCHIVE_EXPANSION_FACTOR = 10
_FORMAT_TO_SUFFIX = {
    "AVIF": ".avif",
    "BMP": ".bmp",
    "JPEG": ".jpg",
    "PNG": ".png",
    "TIFF": ".tiff",
    "WEBP": ".webp",
}


def _image_suffix(data: bytes, filename: str) -> str | None:
    """Return a supported suffix, falling back to the actual image format.

    ZIP producers occasionally omit extensions or use names such as ``.bin``.
    The normal asset pipeline still validates the decoded bytes; this only
    gives it a usable filename when Pillow can identify a supported format.
    """
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix in ALLOWED_EXTENSIONS:
        return suffix
    try:
        with Image.open(io.BytesIO(data)) as image:
            return _FORMAT_TO_SUFFIX.get((image.format or "").upper())
    except (UnidentifiedImageError, OSError):
        return None


def iter_image_members(
    archive_data: bytes,
    *,
    max_member_bytes: int,
) -> Iterator[tuple[str, bytes]]:
    """Yield valid image members without extracting an archive to disk.

    Archive paths are validated before reading. Image bytes are subsequently
    validated by the existing ProjectService asset pipeline.
    """
    if not zipfile.is_zipfile(io.BytesIO(archive_data)):
        raise ValidationAppError("Invalid ZIP archive.")

    expanded_limit = max_member_bytes * ARCHIVE_EXPANSION_FACTOR
    expanded_bytes = 0
    with zipfile.ZipFile(io.BytesIO(archive_data), "r") as archive:
        members = archive.infolist()
        if len(members) > MAX_ARCHIVE_ENTRIES:
            raise ValidationAppError(
                "ZIP archive contains too many files.",
                details={"max_entries": MAX_ARCHIVE_ENTRIES},
            )

        for info in members:
            member_name = str(info.filename or "")
            if info.is_dir():
                continue

            # Reject absolute paths, backslash traversal, and symlink entries
            # instead of relying on filename normalization to make them safe.
            normalized_path = member_name.replace("\\", "/")
            path = PurePosixPath(normalized_path)
            windows_path = PureWindowsPath(member_name)
            if (
                path.is_absolute()
                or windows_path.is_absolute()
                or bool(windows_path.drive)
                or ".." in path.parts
                or ".." in windows_path.parts
            ):
                raise ValidationAppError(
                    "Unsafe path in ZIP archive.",
                    details={"filename": member_name},
                )
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise ValidationAppError(
                    "Symlink entries are not allowed in ZIP archives.",
                    details={"filename": member_name},
                )

            if info.file_size <= 0 or info.file_size > max_member_bytes:
                continue
            expanded_bytes += info.file_size
            if expanded_bytes > expanded_limit:
                raise ValidationAppError("ZIP archive expanded size exceeds the upload limit.")

            data = archive.read(info)
            if len(data) > max_member_bytes:
                continue
            safe_name = normalize_filename(path.name)
            suffix = _image_suffix(data, safe_name)
            if suffix is None:
                continue
            if "." not in safe_name or "." + safe_name.rsplit(".", 1)[-1].lower() not in ALLOWED_EXTENSIONS:
                safe_name = f"{safe_name}{suffix}"
            yield safe_name, data
