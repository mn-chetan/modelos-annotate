"""Helpers for building ontology-agent requests (testable without Vertex)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AgentImagePart:
    asset_id: str
    data: bytes
    mime_type: str


_MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".avif": "image/avif",
}


def mime_for_path(path: Path, *, fallback: str = "image/jpeg") -> str:
    return _MIME_BY_SUFFIX.get(path.suffix.lower(), fallback)


def select_agent_image_ids(
    recon_context: dict[str, Any],
    *,
    max_images: int = 12,
) -> list[str]:
    """Bound visual evidence: cluster medoids first, then outliers, then sample fill."""
    ordered: list[str] = []
    seen: set[str] = set()

    def _add(aid: str | None) -> None:
        if not aid or aid in seen or len(ordered) >= max_images:
            return
        seen.add(aid)
        ordered.append(aid)

    for cluster in recon_context.get("clusters") or []:
        if not isinstance(cluster, dict):
            continue
        _add(cluster.get("medoid_asset_id"))
        if len(ordered) >= max_images:
            return ordered

    for aid in recon_context.get("outliers") or []:
        _add(str(aid) if aid else None)
        if len(ordered) >= max_images:
            return ordered

    for sample in recon_context.get("sample_images") or []:
        if isinstance(sample, dict):
            _add(sample.get("asset_id"))
        if len(ordered) >= max_images:
            break

    return ordered


def load_agent_images(
    asset_ids: list[str],
    image_paths: dict[str, Path],
) -> list[AgentImagePart]:
    """Load bytes for selected asset IDs; skip missing files quietly."""
    parts: list[AgentImagePart] = []
    for aid in asset_ids:
        path = image_paths.get(aid)
        if path is None or not path.exists():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if not data:
            continue
        parts.append(
            AgentImagePart(asset_id=aid, data=data, mime_type=mime_for_path(path))
        )
    return parts


def filter_workflow_steps(
    workflow: list[Any],
    *,
    florence_enabled: bool,
    sam2_enabled: bool,
    task_type: str,
) -> list[dict[str, Any]]:
    """Drop models that are disabled or not usable for the task."""
    out: list[dict[str, Any]] = []
    for step in workflow or []:
        if isinstance(step, dict):
            key = step.get("key") or step.get("model_key")
            payload = dict(step)
        else:
            key = getattr(step, "key", None)
            payload = (
                step.model_dump()
                if hasattr(step, "model_dump")
                else {"key": key, "purpose": "", "required": False}
            )
        if not key:
            continue
        if key == "florence" and not florence_enabled:
            continue
        if key == "sam2" and (not sam2_enabled or task_type != "segmentation"):
            continue
        out.append(payload)
    return out
