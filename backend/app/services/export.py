"""Production-quality dataset export: YOLO, YOLO Seg, COCO, COCO Seg, Pascal VOC, LabelMe, CreateML, Ingenii JSON, and CSV."""

from __future__ import annotations

import io
import csv
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np
from PIL import Image
from app.db.models import AnnotationRow, AssetRow, MaskRow, ProjectRow, MongoDoc, to_mongo_doc, to_mongo_docs
from app.domain.enums import AnnotationSource, GeometryType
from app.errors import NotFoundError, ValidationAppError
from app.storage.files import FileStorage

def _format_dt(val: Any) -> str | None:
    if val is None:
        return None
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


ExportFormat = Literal[
    "yolo",
    "yolo_seg",
    "coco",
    "coco_seg",
    "pascal_voc",
    "labelme",
    "createml",
    "ingenii_json",
    "json",
    "csv",
]

AnnotationSourceFilter = Literal["all", "ai", "human", "approved"]

FORMAT_ALIASES: dict[str, ExportFormat] = {
    "coco json": "coco",
    "coco": "coco",
    "coco_json": "coco",
    "coco_seg": "coco_seg",
    "yolo": "yolo",
    "yolo txt": "yolo",
    "yolo_txt": "yolo",
    "yolo_seg": "yolo_seg",
    "pascal voc": "pascal_voc",
    "pascal voc xml": "pascal_voc",
    "pascal_voc": "pascal_voc",
    "pascal_voc_xml": "pascal_voc",
    "voc": "pascal_voc",
    "labelme": "labelme",
    "labelme json": "labelme",
    "labelme_json": "labelme",
    "createml": "createml",
    "createml json": "createml",
    "createml_json": "createml",
    "csv": "csv",
    "json": "json",
    "custom json": "json",
    "ingenii_json": "json",
    "custom_json": "json",
}


def normalize_export_format(fmt: str | None, default: ExportFormat = "coco") -> ExportFormat:
    """Normalize any user-facing or API export format string to a canonical ExportFormat."""
    if not fmt:
        return default
    clean = str(fmt).strip().lower()
    return FORMAT_ALIASES.get(clean, clean)  # type: ignore[return-value]


def _label_map(project: ProjectRow, annotations: list[AnnotationRow]) -> dict[str, int]:
    """Canonical ontology class list mapping — deterministic across exports for a project.
    Uses project.labels or project.label_ontology ordering first, then appends any unseen active annotation labels.
    """
    ordered: list[str] = []
    
    # 1. Add labels from project.labels
    project_labels = project.get("labels") or []
    for item in project_labels:
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict) and "name" in item:
            name = str(item["name"]).strip()
        else:
            name = str(item).strip()
        if name and name not in ordered:
            ordered.append(name)
            
    # 2. Add labels from project.label_ontology if present
    ontology_items = project.get("label_ontology") or []
    for item in ontology_items:
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict) and "name" in item:
            name = str(item["name"]).strip()
        else:
            name = str(item).strip()
        if name and name not in ordered:
            ordered.append(name)

    # 3. Append any additional active labels from annotations in deterministic order
    ann_labels = sorted({str(ann.label or "").strip() for ann in annotations if ann.label and str(ann.label).strip()})
    for name in ann_labels:
        if name not in ordered:
            ordered.append(name)

    return {name: idx for idx, name in enumerate(ordered)}


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._")
    return cleaned or "project"


def _percent_to_abs(box: tuple[float, float, float, float], width: int, height: int) -> list[float]:
    x, y, w, h = box
    w_val = float(width or 1)
    h_val = float(height or 1)
    abs_x = max(0.0, min(w_val, (float(x) / 100.0) * w_val))
    abs_y = max(0.0, min(h_val, (float(y) / 100.0) * h_val))
    abs_w = max(0.0, min(w_val - abs_x, (float(w) / 100.0) * w_val))
    abs_h = max(0.0, min(h_val - abs_y, (float(h) / 100.0) * h_val))
    return [abs_x, abs_y, abs_w, abs_h]


def _polygon_abs(points: Any, width: int, height: int) -> list[float]:
    flat: list[float] = []
    w_val = float(width or 1)
    h_val = float(height or 1)
    if isinstance(points, list) and points:
        if isinstance(points[0], (int, float)):
            for i in range(0, len(points), 2):
                if i + 1 < len(points):
                    flat.append((float(points[i]) / 100.0) * w_val)
                    flat.append((float(points[i + 1]) / 100.0) * h_val)
        else:
            for pt in points:
                if isinstance(pt, dict) and "x" in pt and "y" in pt:
                    flat.append((float(pt["x"]) / 100.0) * w_val)
                    flat.append((float(pt["y"]) / 100.0) * h_val)
                elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    flat.append((float(pt[0]) / 100.0) * w_val)
                    flat.append((float(pt[1]) / 100.0) * h_val)
    return flat


def _polygon_area(flat_points: list[float]) -> float:
    """Calculate polygon area in pixels using the Shoelace formula."""
    if len(flat_points) < 6:
        return 0.0
    n = len(flat_points) // 2
    x = [flat_points[2 * i] for i in range(n)]
    y = [flat_points[2 * i + 1] for i in range(n)]
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += x[i] * y[j]
        area -= x[j] * y[i]
    return abs(area) / 2.0


def _mask_to_polygon_pts(path: Path, width: int, height: int) -> list[tuple[float, float]]:
    """Convert binary PNG mask to normalized polygon points (0.0 to 1.0)."""
    if not path.exists():
        return []
    try:
        mask_img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if mask_img is None:
            return []
        if mask_img.shape[:2] != (height, width):
            mask_img = cv2.resize(mask_img, (width, height), interpolation=cv2.INTER_NEAREST)
        contours, _ = cv2.findContours(mask_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return []
        largest = max(contours, key=cv2.contourArea)
        peri = cv2.arcLength(largest, True)
        approx = cv2.approxPolyDP(largest, 0.005 * peri, True)
        pts: list[tuple[float, float]] = []
        for pt in approx:
            px, py = pt[0]
            pts.append((max(0.0, min(1.0, float(px) / float(width))), max(0.0, min(1.0, float(py) / float(height)))))
        if len(pts) >= 3:
            return pts
        return []
    except Exception:
        return []


def _mask_to_coco_rle(path: Path, width: int, height: int) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with Image.open(path) as img:
            mask = img.convert("L").resize((width, height)) if img.size != (width, height) else img.convert("L")
            flat = list(mask.get_flattened_data() if hasattr(mask, "get_flattened_data") else mask.getdata())
        counts: list[int] = []
        if not flat:
            return {"counts": [], "size": [height, width]}
        prev = int(flat[0] > 0)
        if prev == 1:
            counts.append(0)
        run = 1
        for v in flat[1:]:
            cur = int(v > 0)
            if cur == prev:
                run += 1
            else:
                counts.append(run)
                prev = cur
                run = 1
        counts.append(run)
        return {"counts": counts, "size": [height, width]}
    except Exception:
        return None


class ExportService:
    def __init__(self, db: Any, storage: FileStorage) -> None:
        if hasattr(db, "projects"):
            self.db = db
        elif callable(db):
            self.db = db()
        else:
            try:
                from app.db.models import get_database
                self.db = get_database()
            except Exception:
                self.db = db
        self.storage = storage

    def _read_asset_bytes(self, asset: Any) -> bytes | None:
        doc = to_mongo_doc(asset) or MongoDoc()
        path = doc.get("storage_path")
        if not path:
            return None
        try:
            resolved = self.storage.resolve(path)
            if resolved.exists():
                return resolved.read_bytes()
        except Exception:
            pass
        return None

    def _filter_annotations(
        self, annotations: list[Any], source_filter: AnnotationSourceFilter, assets: list[Any]
    ) -> list[Any]:
        # Filter active annotations strictly
        active: list[Any] = []
        for ann in annotations:
            doc = to_mongo_doc(ann) or MongoDoc()
            if getattr(doc, "status", None) == "deleted":
                continue
            rev_stat = str(getattr(doc, "review_status", "") or "").lower()
            if rev_stat in {"rejected", "human_rejected", "deleted"}:
                continue
            active.append(doc)

        if source_filter == "all":
            return active

        approved_statuses = {
            "approved",
            "submitted",
            "reviewed",
            "auto_approved",
            "human_approved",
            "human_modified_approved",
            "accepted",
        }
        approved_asset_ids = {
            a.id for a in assets if str(a.get("review_status") or "").lower() in approved_statuses
        }

        filtered = []
        for ann in active:
            src = str(ann.get("source") or "").lower()
            if source_filter == "ai":
                if src in {AnnotationSource.AI.value, "model_proposed", "ai"}:
                    filtered.append(ann)
            elif source_filter == "human":
                if src in {
                    AnnotationSource.HUMAN.value,
                    AnnotationSource.HUMAN_MODIFIED.value,
                    "human_created",
                    "human_edited",
                    "human_modified",
                    "reviewer_edited",
                    "decision_applied",
                    "human",
                }:
                    filtered.append(ann)
            elif source_filter == "approved":
                ann_rev = str(getattr(ann, "review_status", "") or "").lower()
                if ann_rev in approved_statuses or ann.get("asset_id") in approved_asset_ids:
                    filtered.append(ann)

        return filtered

    async def export_project(
        self,
        project_id: str,
        fmt: str | None = None,
        annotation_source: AnnotationSourceFilter = "approved",
        include_images: bool = True,
    ) -> tuple[bytes, str, str, dict[str, Any]]:
        raw_project = await self.db.projects.find_one({"id": project_id})
        if not raw_project:
            raw_project = await self.db.projects.find_one({"name": project_id})
        if not raw_project:
            raise NotFoundError("Project not found", details={"project_id": project_id})
        
        project = to_mongo_doc(raw_project)  # type: ignore
        project_id = project.id

        # Authoritative Expected Output Format resolution:
        # If no explicit format supplied, resolve from project's persisted Expected Output Format
        if not fmt:
            proj_expected = getattr(project, "expected_output_format", None) or raw_project.get("expected_output_format")
            resolved_fmt: ExportFormat = normalize_export_format(proj_expected, default="coco")
        else:
            resolved_fmt = normalize_export_format(fmt, default="coco")

        # Fetch all non-deleted, relevant assets for this project via single equality query
        # avoiding Firestore multi-field inequality and unsupported $nin operator errors
        raw_assets_list = await self.db.assets.find({"project_id": project_id}).to_list(length=100000)
        excluded_review_statuses = {"rejected", "human_rejected", "flagged"}
        all_assets = [
            a for a in to_mongo_docs(raw_assets_list)
            if getattr(a, "relevance_status", None) != "not_relevant"
            and getattr(a, "status", None) != "deleted"
            and str(getattr(a, "review_status", "") or "").lower() not in excluded_review_statuses
        ]
        # Sort by created_at in memory
        all_assets.sort(key=lambda a: getattr(a, "created_at", None) or "")
        all_asset_ids = [a.id for a in all_assets]

        # Fetch all active annotations for these assets
        raw_ann_list = await self.db.annotations.find({"project_id": project_id}).to_list(length=100000)
        if not raw_ann_list and all_asset_ids:
            # Fallback by asset_id in chunks of 30
            for i in range(0, len(all_asset_ids), 30):
                chunk = all_asset_ids[i:i + 30]
                chunk_docs = await self.db.annotations.find({"asset_id": {"$in": chunk}}).to_list(length=10000)
                raw_ann_list.extend(chunk_docs)

        raw_annotations = [
            ann for ann in to_mongo_docs(raw_ann_list)
            if getattr(ann, "status", None) != "deleted"
            and (not all_asset_ids or ann.get("asset_id") in set(all_asset_ids))
        ]
        raw_annotations.sort(key=lambda a: getattr(a, "created_at", None) or "")

        final_approved_statuses = {
            "final_approved",
            "approved",
            "auto_approved",
            "human_approved",
            "human_modified_approved",
            "accepted",
        }

        # Identify FINAL_APPROVED assets (per project locking/QC rules)
        approved_assets = [
            a for a in all_assets
            if str(a.get("review_status") or "").lower() in final_approved_statuses
            or str(a.get("workflow_status") or "").upper() == "FINAL_APPROVED"
            or str(a.get("current_real_status") or "").upper() == "FINAL_APPROVED"
            or bool(a.get("is_locked"))
        ]
        approved_asset_ids = {a.id for a in approved_assets}

        # Filter strictly to FINAL_APPROVED annotations (Rule 10)
        filtered_annotations: list[Any] = []
        for ann in raw_annotations:
            doc = to_mongo_doc(ann) or MongoDoc()
            if getattr(doc, "status", None) == "deleted":
                continue
            rev_stat = str(getattr(doc, "review_status", "") or "").lower()
            if rev_stat in {"rejected", "human_rejected", "deleted"}:
                continue

            is_final_approved = (
                doc.get("asset_id") in approved_asset_ids
                or rev_stat in final_approved_statuses
            )
            # Image boxes are exported only after the parent image is approved.
            # An individual saved label decision does not approve the image.
            if str(project.get("modality") or "image") == "image" and doc.get("asset_id") not in approved_asset_ids:
                continue
            if not is_final_approved:
                continue

            src = str(doc.get("source") or "").lower()
            if annotation_source == "ai":
                if src in {AnnotationSource.AI.value, "model_proposed", "ai"}:
                    filtered_annotations.append(doc)
            elif annotation_source == "human":
                if src in {
                    AnnotationSource.HUMAN.value,
                    AnnotationSource.HUMAN_MODIFIED.value,
                    "human_created",
                    "human_edited",
                    "human_modified",
                    "reviewer_edited",
                    "decision_applied",
                    "human",
                }:
                    filtered_annotations.append(doc)
            else:
                filtered_annotations.append(doc)

        # Assets exported are strictly final approved assets (or assets associated with final approved annotations)
        ann_asset_ids = {ann.get("asset_id") for ann in filtered_annotations if ann.get("asset_id")}
        export_asset_ids = approved_asset_ids | ann_asset_ids
        assets = [a for a in all_assets if a.id in export_asset_ids]
        annotations = filtered_annotations

        masks = (
            to_mongo_docs(
                await self.db.masks.find({"asset_id": {"$in": list(export_asset_ids)}}).to_list(length=100000)
            )
            if export_asset_ids
            else []
        )

        label_map = _label_map(project, annotations)
        proj_slug = _safe_filename(project.name or "project").lower()

        summary_meta = {
            "format": resolved_fmt.upper(),
            "image_count": len(assets),
            "annotation_count": len(annotations),
            "class_count": len(label_map),
            "labels": list(label_map.keys()),
            "project_name": project.name,
            "exported_at": datetime.now(UTC).isoformat(),
        }

        if resolved_fmt in {"ingenii_json", "json"}:
            payload = self._ingenii_json(project, assets, annotations, masks)
            data = json.dumps(payload, indent=2, default=str).encode("utf-8")
            return data, "application/json", f"{proj_slug}-annotations.json", summary_meta

        if resolved_fmt == "csv":
            data = self._csv(project, assets, annotations, label_map)
            return data, "text/csv", f"{proj_slug}-annotations.csv", summary_meta

        if resolved_fmt in {"coco", "coco_seg"}:
            data = self._coco_zip(project, assets, annotations, masks, label_map, is_seg=(resolved_fmt == "coco_seg"), include_images=include_images)
            return data, "application/zip", f"{proj_slug}-{resolved_fmt}.zip", summary_meta

        if resolved_fmt in {"yolo", "yolo_seg"}:
            data = self._yolo_zip(project, assets, annotations, masks, label_map, is_seg=(resolved_fmt == "yolo_seg"), include_images=include_images)
            return data, "application/zip", f"{proj_slug}-{resolved_fmt}.zip", summary_meta

        if resolved_fmt == "pascal_voc":
            data = self._pascal_voc_zip(project, assets, annotations, label_map, include_images=include_images)
            return data, "application/zip", f"{proj_slug}-voc.zip", summary_meta

        if resolved_fmt == "labelme":
            data = self._labelme_zip(project, assets, annotations, label_map, include_images=include_images)
            return data, "application/zip", f"{proj_slug}-labelme.zip", summary_meta

        if resolved_fmt == "createml":
            data = self._createml_zip(project, assets, annotations, label_map, include_images=include_images)
            return data, "application/zip", f"{proj_slug}-createml.zip", summary_meta

        raise ValidationAppError(f"Unsupported export format: {resolved_fmt}")

    def _ingenii_json(
        self,
        project: ProjectRow,
        assets: list[AssetRow],
        annotations: list[AnnotationRow],
        masks: list[MaskRow],
    ) -> dict[str, Any]:
        ontology = project.get("label_ontology") or []
        label_map = _label_map(project, annotations)
        return {
            "format": "ingenii_annotate",
            "format_version": "1.0",
            "exported_at": datetime.now(UTC).isoformat(),
            "project": {
                "id": project.get("id"),
                "name": project.get("name"),
                "goal": project.get("goal"),
                "task_type": project.get("task_type"),
                "labels": project.get("labels") or [],
                "label_ontology": ontology,
                "status": project.get("status"),
            },
            "images": [
                {
                    "id": a.id,
                    "filename": a.filename,
                    "width": a.width,
                    "height": a.height,
                    "content_type": getattr(a, "content_type", None),
                    "review_status": getattr(a, "review_status", None),
                    "created_at": _format_dt(getattr(a, "created_at", None)),
                    "updated_at": _format_dt(getattr(a, "updated_at", None)),
                }
                for a in assets
            ],
            "categories": [
                {"id": idx, "name": name}
                for name, idx in sorted(label_map.items(), key=lambda item: item[1])
            ],
            "annotations": [
                {
                    "annotation_id": ann.id,
                    "asset_id": ann.asset_id,
                    "label": ann.label,
                    "class_id": label_map.get(ann.label, getattr(ann, "class_id", None)),
                    "type": getattr(ann, "geometry_type", None) or GeometryType.BOX.value,
                    "bbox": [ann.x, ann.y, ann.w, ann.h],
                    "geometry": ann.get("geometry") if hasattr(ann, "get") else getattr(ann, "geometry", None),
                    "confidence": ann.get("confidence") if hasattr(ann, "get") else getattr(ann, "confidence", None),
                    "source": ann.get("source") if hasattr(ann, "get") else getattr(ann, "source", None),
                    "provenance": getattr(ann, "provenance", None),
                    "review_status": getattr(ann, "review_status", None) or "active",
                    "created_at": _format_dt(getattr(ann, "created_at", None)),
                    "updated_at": _format_dt(getattr(ann, "updated_at", None)),
                }
                for ann in annotations
            ],
        }

    def _coco(
        self,
        project: ProjectRow,
        assets: list[AssetRow],
        annotations: list[AnnotationRow],
        masks: list[MaskRow],
        label_map: dict[str, int],
        is_seg: bool = False,
    ) -> dict[str, Any]:
        categories = [
            {"id": idx + 1, "name": name, "supercategory": "object"}
            for name, idx in sorted(label_map.items(), key=lambda kv: kv[1])
        ]
        images = []
        for i, asset in enumerate(assets, start=1):
            images.append(
                {
                    "id": i,
                    "file_name": asset.filename,
                    "width": asset.width or 1,
                    "height": asset.height or 1,
                    "ingenii_asset_id": asset.id,
                }
            )
        asset_index = {a.id: i for i, a in enumerate(assets, start=1)}
        masks_by_ann = {m.annotation_id: m for m in masks if m.annotation_id}

        coco_anns: list[dict[str, Any]] = []
        ann_id = 1
        for ann in annotations:
            gtype = getattr(ann, "geometry_type", None) or GeometryType.BOX.value
            if gtype == GeometryType.CLASSIFICATION.value or ann.asset_id not in asset_index:
                continue
            asset = next(a for a in assets if a.id == ann.asset_id)
            cat_id = label_map.get(ann.label)
            if cat_id is None:
                continue
            cat_id = cat_id + 1
            w_img = asset.width or 1
            h_img = asset.height or 1
            abs_box = _percent_to_abs((ann.x, ann.y, ann.w, ann.h), w_img, h_img)
            
            # Default area to bbox area
            seg_area = round(abs_box[2] * abs_box[3], 2)
            
            entry: dict[str, Any] = {
                "id": ann_id,
                "image_id": asset_index[ann.asset_id],
                "category_id": cat_id,
                "bbox": abs_box,
                "area": seg_area,
                "iscrowd": 0,
                "ingenii_annotation_id": ann.id,
                "source": ann.get("source") if hasattr(ann, "get") else getattr(ann, "source", None),
            }
            
            # Polygon geometry check
            has_polygon = False
            geometry = ann.get("geometry") if hasattr(ann, "get") else getattr(ann, "geometry", None)
            if isinstance(geometry, dict) and "points" in geometry:
                points = geometry.get("points") or []
                flat = _polygon_abs(points, w_img, h_img)
                if len(flat) >= 6:
                    entry["segmentation"] = [flat]
                    calc_area = _polygon_area(flat)
                    if calc_area > 0.0:
                        entry["area"] = round(calc_area, 2)
                    has_polygon = True
                    
            mask = masks_by_ann.get(ann.id)
            if not has_polygon and mask and mask.storage_path:
                try:
                    path = self.storage.resolve(mask.storage_path)
                except Exception:
                    path = Path(mask.storage_path)
                rle = _mask_to_coco_rle(path, w_img, h_img)
                if rle:
                    entry["segmentation"] = rle
                    has_polygon = True

            if "segmentation" not in entry:
                x, y, w, h = abs_box
                entry["segmentation"] = [[x, y, x + w, y, x + w, y + h, x, y + h]]
            coco_anns.append(entry)
            ann_id += 1

        return {
            "info": {
                "description": project.name,
                "version": "1.0",
                "year": datetime.now(UTC).year,
                "contributor": "Ingenii Annotate",
                "date_created": datetime.now(UTC).isoformat(),
            },
            "licenses": [],
            "images": images,
            "annotations": coco_anns,
            "categories": categories,
        }

    def _coco_zip(
        self,
        project: ProjectRow,
        assets: list[AssetRow],
        annotations: list[AnnotationRow],
        masks: list[MaskRow],
        label_map: dict[str, int],
        is_seg: bool = False,
        include_images: bool = True,
    ) -> bytes:
        coco_payload = self._coco(project, assets, annotations, masks, label_map, is_seg=is_seg)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("annotations/instances.json", json.dumps(coco_payload, indent=2))
            if include_images:
                for asset in assets:
                    img_bytes = self._read_asset_bytes(asset)
                    if img_bytes:
                        zf.writestr(f"images/{asset.filename}", img_bytes)
            readme = f"Format: {'COCO Instance Segmentation' if is_seg else 'COCO JSON'}\nProject: {project.name}\nExported At: {datetime.now(UTC).isoformat()}\nImages: {len(assets)}\nAnnotations: {len(annotations)}\nClasses: {len(label_map)}\n"
            zf.writestr("README.txt", readme)

        return buffer.getvalue()

    def _yolo_zip(
        self,
        project: ProjectRow,
        assets: list[AssetRow],
        annotations: list[AnnotationRow],
        masks: list[MaskRow],
        label_map: dict[str, int],
        is_seg: bool = False,
        include_images: bool = True,
    ) -> bytes:
        names = [name for name, _ in sorted(label_map.items(), key=lambda kv: kv[1])]
        masks_by_ann = {m.annotation_id: m for m in masks if m.annotation_id}
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("classes.txt", "\n".join(names) + ("\n" if names else ""))
            by_asset: dict[str, list[AnnotationRow]] = {a.id: [] for a in assets}
            for ann in annotations:
                if ann.asset_id in by_asset:
                    by_asset[ann.asset_id].append(ann)

            for asset in assets:
                lines: list[str] = []
                w_img = asset.width or 1
                h_img = asset.height or 1

                for ann in by_asset.get(asset.id, []):
                    class_id = label_map.get(ann.label)
                    if class_id is None:
                        continue
                    if getattr(ann, "geometry_type", None) == GeometryType.POINT.value:
                        raise ValidationAppError(
                            "YOLO export cannot represent point annotations without losing geometry.",
                            details={"annotation_id": ann.id, "asset_id": ann.asset_id},
                        )

                    if is_seg:
                        points: list[tuple[float, float]] = []
                        geometry = ann.get("geometry") if hasattr(ann, "get") else getattr(ann, "geometry", None)
                        if isinstance(geometry, dict) and "points" in geometry:
                            raw_pts = geometry.get("points") or []
                            if raw_pts and isinstance(raw_pts[0], (int, float)):
                                for i in range(0, len(raw_pts), 2):
                                    if i + 1 < len(raw_pts):
                                        points.append((
                                            max(0.0, min(1.0, float(raw_pts[i]) / 100.0)),
                                            max(0.0, min(1.0, float(raw_pts[i + 1]) / 100.0)),
                                        ))
                            else:
                                for pt in raw_pts:
                                    if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                                        points.append((
                                            max(0.0, min(1.0, float(pt[0]) / 100.0)),
                                            max(0.0, min(1.0, float(pt[1]) / 100.0)),
                                        ))

                        # If points missing, check mask
                        mask = masks_by_ann.get(ann.id)
                        if not points and mask and mask.storage_path:
                            try:
                                mpath = self.storage.resolve(mask.storage_path)
                            except Exception:
                                mpath = Path(mask.storage_path)
                            points = _mask_to_polygon_pts(mpath, w_img, h_img)

                        if not points:
                            x, y, w, h = ann.x / 100.0, ann.y / 100.0, ann.w / 100.0, ann.h / 100.0
                            points = [
                                (max(0.0, min(1.0, x)), max(0.0, min(1.0, y))),
                                (max(0.0, min(1.0, x + w)), max(0.0, min(1.0, y))),
                                (max(0.0, min(1.0, x + w)), max(0.0, min(1.0, y + h))),
                                (max(0.0, min(1.0, x)), max(0.0, min(1.0, y + h))),
                            ]

                        pts_str = " ".join(f"{px:.6f} {py:.6f}" for px, py in points)
                        lines.append(f"{class_id} {pts_str}")
                    else:
                        cx = max(0.0, min(1.0, (ann.x + ann.w / 2.0) / 100.0))
                        cy = max(0.0, min(1.0, (ann.y + ann.h / 2.0) / 100.0))
                        nw = max(0.0, min(1.0, ann.w / 100.0))
                        nh = max(0.0, min(1.0, ann.h / 100.0))
                        lines.append(f"{class_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

                stem = Path(asset.filename).stem or asset.id
                zf.writestr(f"labels/{stem}.txt", "\n".join(lines) + ("\n" if lines else ""))

                if include_images:
                    img_bytes = self._read_asset_bytes(asset)
                    if img_bytes:
                        zf.writestr(f"images/{asset.filename}", img_bytes)

            data_yaml = (
                "path: .\ntrain: images\nval: images\nnames:\n"
                + "".join(f"  {i}: {n}\n" for i, n in enumerate(names))
            )
            zf.writestr("data.yaml", data_yaml)
            readme = f"Format: {'YOLO Segmentation' if is_seg else 'YOLO Object Detection'}\nProject: {project.name}\nExported At: {datetime.now(UTC).isoformat()}\nImages: {len(assets)}\nAnnotations: {len(annotations)}\nClasses: {len(names)}\n"
            zf.writestr("README.txt", readme)

        return buffer.getvalue()

    def _csv(
        self,
        project: ProjectRow,
        assets: list[AssetRow],
        annotations: list[AnnotationRow],
        label_map: dict[str, int],
    ) -> bytes:
        asset_by_id = {asset.id: asset for asset in assets}
        output = io.StringIO(newline="")
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "project_id", "asset_id", "image_name", "annotation_id", "label", "class_id",
                "annotation_type", "x1", "y1", "x2", "y2", "confidence", "source", "review_status", "polygon_points",
            ],
        )
        writer.writeheader()
        for ann in annotations:
            asset = asset_by_id.get(ann.asset_id)
            if asset is None:
                continue
            w_img = asset.width or 1
            h_img = asset.height or 1
            geometry_type = getattr(ann, "geometry_type", None) or GeometryType.BOX.value
            geometry = ann.get("geometry") if hasattr(ann, "get") else getattr(ann, "geometry", None)
            points = geometry.get("points", []) if isinstance(geometry, dict) else []
            abs_box = _percent_to_abs((ann.x, ann.y, ann.w, ann.h), w_img, h_img)
            
            writer.writerow({
                "project_id": project.get("id"),
                "asset_id": asset.id,
                "image_name": asset.filename,
                "annotation_id": ann.id,
                "label": ann.label,
                "class_id": label_map.get(ann.label, getattr(ann, "class_id", None) or 0),
                "annotation_type": geometry_type,
                "x1": round(abs_box[0], 2),
                "y1": round(abs_box[1], 2),
                "x2": round(abs_box[0] + abs_box[2], 2),
                "y2": round(abs_box[1] + abs_box[3], 2),
                "confidence": round(ann.confidence, 4) if getattr(ann, "confidence", None) is not None else "",
                "source": ann.get("source") if hasattr(ann, "get") else getattr(ann, "source", None),
                "review_status": getattr(ann, "review_status", None) or "active",
                "polygon_points": json.dumps(points, separators=(",", ":")) if points else "",
            })
        return output.getvalue().encode("utf-8")

    def _pascal_voc_zip(
        self,
        project: ProjectRow,
        assets: list[AssetRow],
        annotations: list[AnnotationRow],
        label_map: dict[str, int],
        include_images: bool = True,
    ) -> bytes:
        by_asset: dict[str, list[AnnotationRow]] = {a.id: [] for a in assets}
        for ann in annotations:
            if ann.asset_id in by_asset:
                by_asset[ann.asset_id].append(ann)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for asset in assets:
                root = ET.Element("annotation")
                ET.SubElement(root, "folder").text = "images"
                ET.SubElement(root, "filename").text = asset.filename
                ET.SubElement(root, "path").text = f"images/{asset.filename}"

                source_el = ET.SubElement(root, "source")
                ET.SubElement(source_el, "database").text = "Ingenii Annotate"

                size_el = ET.SubElement(root, "size")
                w_img = asset.width or 1
                h_img = asset.height or 1
                ET.SubElement(size_el, "width").text = str(w_img)
                ET.SubElement(size_el, "height").text = str(h_img)
                ET.SubElement(size_el, "depth").text = "3"

                ET.SubElement(root, "segmented").text = "0"

                for ann in by_asset.get(asset.id, []):
                    if not ann.label:
                        continue
                    if getattr(ann, "geometry_type", None) == GeometryType.POINT.value:
                        raise ValidationAppError(
                            "Pascal VOC cannot represent point annotations without losing geometry.",
                            details={"annotation_id": ann.id, "asset_id": ann.asset_id},
                        )
                    abs_box = _percent_to_abs((ann.x, ann.y, ann.w, ann.h), w_img, h_img)
                    xmin = int(round(abs_box[0]))
                    ymin = int(round(abs_box[1]))
                    xmax = max(xmin + 1, int(round(abs_box[0] + abs_box[2])))
                    ymax = max(ymin + 1, int(round(abs_box[1] + abs_box[3])))

                    obj_el = ET.SubElement(root, "object")
                    ET.SubElement(obj_el, "name").text = ann.label
                    ET.SubElement(obj_el, "pose").text = "Unspecified"
                    ET.SubElement(obj_el, "truncated").text = "0"
                    ET.SubElement(obj_el, "difficult").text = "0"

                    bnd_el = ET.SubElement(obj_el, "bndbox")
                    ET.SubElement(bnd_el, "xmin").text = str(xmin)
                    ET.SubElement(bnd_el, "ymin").text = str(ymin)
                    ET.SubElement(bnd_el, "xmax").text = str(xmax)
                    ET.SubElement(bnd_el, "ymax").text = str(ymax)

                # The tree is generated locally from validated annotation
                # fields. Avoid reparsing it with xml.dom.minidom: this keeps
                # export independent of minidom's nested-node complexity and
                # avoids treating generated XML as untrusted input.
                ET.indent(root, space="  ")
                pretty_xml = ET.tostring(root, encoding="unicode", xml_declaration=True)

                stem = Path(asset.filename).stem or asset.id
                zf.writestr(f"annotations/{stem}.xml", pretty_xml)

                if include_images:
                    img_bytes = self._read_asset_bytes(asset)
                    if img_bytes:
                        zf.writestr(f"images/{asset.filename}", img_bytes)

            readme = f"Format: Pascal VOC XML\nProject: {project.name}\nExported At: {datetime.now(UTC).isoformat()}\nImages: {len(assets)}\nAnnotations: {len(annotations)}\nClasses: {len(label_map)}\n"
            zf.writestr("README.txt", readme)

        return buffer.getvalue()

    def _labelme_zip(
        self,
        project: ProjectRow,
        assets: list[AssetRow],
        annotations: list[AnnotationRow],
        label_map: dict[str, int],
        include_images: bool = True,
    ) -> bytes:
        by_asset: dict[str, list[AnnotationRow]] = {a.id: [] for a in assets}
        for ann in annotations:
            if ann.asset_id in by_asset:
                by_asset[ann.asset_id].append(ann)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for asset in assets:
                w_img = asset.width or 1
                h_img = asset.height or 1
                shapes = []
                for ann in by_asset.get(asset.id, []):
                    if not ann.label:
                        continue
                    gtype = getattr(ann, "geometry_type", None) or GeometryType.BOX.value
                    geometry = ann.get("geometry") if hasattr(ann, "get") else getattr(ann, "geometry", None)
                    if gtype == GeometryType.POLYGON.value and isinstance(geometry, dict) and "points" in geometry:
                        pts = _polygon_abs(geometry["points"], w_img, h_img)
                        pts_pairs = [[pts[i], pts[i + 1]] for i in range(0, len(pts), 2)]
                        shapes.append({
                            "label": ann.label,
                            "points": pts_pairs,
                            "group_id": None,
                            "shape_type": "polygon",
                            "flags": {},
                        })
                    elif gtype == GeometryType.POINT.value:
                        points = geometry.get("points", []) if isinstance(geometry, dict) else []
                        point = points[0] if points and isinstance(points[0], (list, tuple)) else [ann.x, ann.y]
                        shapes.append({
                            "label": ann.label,
                            "points": [[float(point[0]) / 100.0 * w_img, float(point[1]) / 100.0 * h_img]],
                            "group_id": None,
                            "shape_type": "point",
                            "flags": {},
                        })
                    elif gtype in {"polyline", "instance_mask"}:
                        raise ValidationAppError(
                            "LabelMe cannot represent this persisted geometry without losing information.",
                            details={"annotation_id": ann.id, "asset_id": ann.asset_id, "geometry_type": gtype},
                        )
                    else:
                        abs_box = _percent_to_abs((ann.x, ann.y, ann.w, ann.h), w_img, h_img)
                        shapes.append({
                            "label": ann.label,
                            "points": [
                                [abs_box[0], abs_box[1]],
                                [abs_box[0] + abs_box[2], abs_box[1] + abs_box[3]],
                            ],
                            "group_id": None,
                            "shape_type": "rectangle",
                            "flags": {},
                        })

                stem = Path(asset.filename).stem or asset.id
                labelme_doc = {
                    "version": "5.0.1",
                    "flags": {},
                    "shapes": shapes,
                    "imagePath": f"../images/{asset.filename}",
                    "imageData": None,
                    "imageHeight": h_img,
                    "imageWidth": w_img,
                }
                zf.writestr(f"annotations/{stem}.json", json.dumps(labelme_doc, indent=2))

                if include_images:
                    img_bytes = self._read_asset_bytes(asset)
                    if img_bytes:
                        zf.writestr(f"images/{asset.filename}", img_bytes)

            readme = f"Format: LabelMe JSON\nProject: {project.name}\nExported At: {datetime.now(UTC).isoformat()}\nImages: {len(assets)}\nAnnotations: {len(annotations)}\nClasses: {len(label_map)}\n"
            zf.writestr("README.txt", readme)

        return buffer.getvalue()

    def _createml_zip(
        self,
        project: ProjectRow,
        assets: list[AssetRow],
        annotations: list[AnnotationRow],
        label_map: dict[str, int],
        include_images: bool = True,
    ) -> bytes:
        by_asset: dict[str, list[AnnotationRow]] = {a.id: [] for a in assets}
        for ann in annotations:
            if ann.asset_id in by_asset:
                by_asset[ann.asset_id].append(ann)

        createml_items = []
        for asset in assets:
            w_img = asset.width or 1
            h_img = asset.height or 1
            ann_list = []
            for ann in by_asset.get(asset.id, []):
                if not ann.label:
                    continue
                abs_box = _percent_to_abs((ann.x, ann.y, ann.w, ann.h), w_img, h_img)
                cx = abs_box[0] + abs_box[2] / 2.0
                cy = abs_box[1] + abs_box[3] / 2.0
                ann_list.append({
                    "label": ann.label,
                    "coordinates": {
                        "x": round(cx, 2),
                        "y": round(cy, 2),
                        "width": round(abs_box[2], 2),
                        "height": round(abs_box[3], 2),
                    },
                })
            createml_items.append({
                "image": asset.filename,
                "annotations": ann_list,
            })

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("annotations.json", json.dumps(createml_items, indent=2))
            if include_images:
                for asset in assets:
                    img_bytes = self._read_asset_bytes(asset)
                    if img_bytes:
                        zf.writestr(f"images/{asset.filename}", img_bytes)

            readme = f"Format: CreateML JSON\nProject: {project.name}\nExported At: {datetime.now(UTC).isoformat()}\nImages: {len(assets)}\nAnnotations: {len(annotations)}\nClasses: {len(label_map)}\n"
            zf.writestr("README.txt", readme)

        return buffer.getvalue()
