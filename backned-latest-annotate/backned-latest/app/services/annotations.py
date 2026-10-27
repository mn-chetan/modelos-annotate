"""Annotation CRUD with optimistic concurrency and multi-geometry support backed by MongoDB."""

from __future__ import annotations

from datetime import UTC, datetime
import math
from typing import Any

from app.api.schemas import AnnotationCreate, AnnotationUpdate
from app.db.models import MongoDoc, to_mongo_doc, to_mongo_docs, get_database, _uuid, _utcnow
from app.domain.enums import AnnotationSource, GeometryType
from app.errors import ConflictError, NotFoundError, ValidationAppError
from app.inference.detector import clamp_box
from app.inference.ontology_map import (
    UNLABELED,
    OntologyIndex,
    SAFE_ALIASES,
    build_ontology_index,
    is_invalid_workflow_label,
    is_allowed_annotation_label,
)
from app.logging import get_logger

logger = get_logger(__name__)

MIN_BOX_PERCENT = 0.0
MIN_POLYGON_POINTS = 3
MIN_POLYLINE_POINTS = 2


def _provenance_frame_index(provenance: dict[str, Any] | None) -> int | None:
    prov = provenance or {}
    raw = prov.get("frame_index")
    if raw is None:
        raw = prov.get("frame_number")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not value.is_integer():
        return None
    return int(value)


def _is_ai_origin(row: Any, provenance: dict[str, Any] | None = None) -> bool:
    doc = to_mongo_doc(row) or MongoDoc()
    prov = provenance if provenance is not None else (doc.get("provenance") or {})
    if doc.get("source") == AnnotationSource.AI.value:
        return True
    if doc.get("model_id"):
        return True
    if prov.get("origin_source") == AnnotationSource.AI.value:
        return True
    return prov.get("raw_model_confidence") is not None or prov.get("model_confidence") is not None


def _stamp_human_edit_provenance(row: Any) -> dict[str, Any]:
    doc = to_mongo_doc(row) or MongoDoc()
    prov = dict(doc.get("provenance") or {})
    ai_origin = _is_ai_origin(doc, prov)
    if ai_origin:
        prov.setdefault("origin_source", AnnotationSource.AI.value)
        orig_ai = prov.get("original_ai_confidence")
        if orig_ai is None:
            raw_c = prov.get("raw_model_confidence") or prov.get("model_confidence") or doc.get("confidence")
            if raw_c is not None:
                try:
                    orig_ai = float(raw_c)
                except (TypeError, ValueError):
                    orig_ai = None
            if orig_ai is not None:
                prov["original_ai_confidence"] = orig_ai
        if "model_confidence" not in prov and "raw_model_confidence" not in prov:
            prov["model_confidence"] = doc.get("confidence")
        elif "model_confidence" not in prov and prov.get("raw_model_confidence") is not None:
            try:
                prov["model_confidence"] = float(prov["raw_model_confidence"])
            except (TypeError, ValueError):
                pass
    prov["human_edited"] = True
    prov["human_edited_at"] = datetime.now(UTC).isoformat()
    return prov


def _annotation_out(row: Any) -> dict[str, Any]:
    doc = to_mongo_doc(row) or MongoDoc()
    conf = doc.get("confidence")
    if conf is not None:
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = None

    prov = dict(doc.get("provenance") or {})
    orig_ai_conf = prov.get("original_ai_confidence")
    if orig_ai_conf is None:
        raw_model_c = prov.get("raw_model_confidence") or prov.get("model_confidence")
        if raw_model_c is not None:
            try:
                orig_ai_conf = float(raw_model_c)
            except (TypeError, ValueError):
                orig_ai_conf = None
    else:
        try:
            orig_ai_conf = float(orig_ai_conf)
        except (TypeError, ValueError):
            orig_ai_conf = None

    # If the document is human-edited or human-modified and has confidence preserved directly,
    # or if provenance indicates AI origin and conf is present
    src = str(doc.get("source") or "").lower()
    if orig_ai_conf is None and conf is not None and (src in ("human_modified", "human", "human_edited", "reviewer_edited") or prov.get("origin_source") == AnnotationSource.AI.value or prov.get("human_edited")):
        orig_ai_conf = conf

    gtype = doc.get("geometry_type") or GeometryType.BOX.value
    geom = doc.get("geometry")
    if gtype == GeometryType.BOX.value and not geom:
        geom = {"type": "box"}

    raw_poly = doc.get("polygon") or (geom.get("points") if isinstance(geom, dict) else None)
    if isinstance(raw_poly, list):
        norm_poly = []
        for pt in raw_poly:
            if isinstance(pt, dict) and "x" in pt and "y" in pt:
                try:
                    norm_poly.append([float(pt["x"]), float(pt["y"])])
                except (ValueError, TypeError):
                    continue
            elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
                try:
                    norm_poly.append([float(pt[0]), float(pt[1])])
                except (ValueError, TypeError):
                    continue
            else:
                norm_poly.append(pt)
        raw_poly = norm_poly

    if isinstance(geom, dict) and isinstance(geom.get("points"), list):
        geom = dict(geom)
        geom["points"] = [
            [float(p["x"]), float(p["y"])] if isinstance(p, dict) and "x" in p and "y" in p
            else p for p in geom["points"]
        ]

    created_at = doc.get("created_at")
    updated_at = doc.get("updated_at")

    if updated_at is None:
        if created_at is not None:
            updated_at = created_at
    if created_at is None:
        if updated_at is not None:
            created_at = updated_at

    if created_at is None and updated_at is None:
        doc_id = doc.get("id") or doc.get("_id") or "unknown"
        raise ValueError(
            f"Annotation record '{doc_id}' is missing required created_at and updated_at timestamps."
        )

    return {
        "id": doc.get("id", ""),
        "asset_id": doc.get("asset_id") or doc.get("project_id", ""),
        "label": doc.get("label", ""),
        "canonical_label": doc.get("canonical_label") or doc.get("label", ""),
        "display_label": doc.get("display_label") or doc.get("label", ""),
        "class_id": doc.get("class_id"),
        "geometry_type": gtype,
        "geometry": geom,
        "text_span": doc.get("text_span") or (geom if gtype in ("text_span", "text_classification") else None),
        "x": doc.get("x", 0.0),
        "y": doc.get("y", 0.0),
        "w": doc.get("w", 0.0),
        "h": doc.get("h", 0.0),
        "confidence": conf,
        "evidence_confidence": prov.get("evidence_confidence"),
        "original_ai_confidence": orig_ai_conf,
        "source": doc.get("source", AnnotationSource.HUMAN.value),
        "model_id": doc.get("model_id"),
        "inferred_at": doc.get("inferred_at"),
        "provenance": prov,
        "polygon": raw_poly,
        "mask_id": doc.get("mask_id") or prov.get("mask_id"),
        "version": doc.get("version", 1),
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _clamp_point(x: float, y: float) -> tuple[float, float]:
    cx = max(0.0, min(100.0, float(x)))
    cy = max(0.0, min(100.0, float(y)))
    return round(cx, 4), round(cy, 4)


def validate_box(x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
    b = clamp_box(x, y, w, h)
    if b.w <= MIN_BOX_PERCENT or b.h <= MIN_BOX_PERCENT:
        raise ValidationAppError("Bounding box width and height must be greater than zero")
    return b.x, b.y, b.w, b.h


def validate_polygon_points(points: Any) -> list[list[float]]:
    if not isinstance(points, list) or len(points) < MIN_POLYGON_POINTS:
        raise ValidationAppError("Polygon annotations require at least 3 points")
    cleaned: list[list[float]] = []
    for pt in points:
        if isinstance(pt, dict) and "x" in pt and "y" in pt:
            cx, cy = _clamp_point(pt["x"], pt["y"])
            cleaned.append([cx, cy])
        elif not isinstance(pt, (list, tuple)) or len(pt) != 2:
            raise ValidationAppError("Polygon point must be [x, y]")
        else:
            cx, cy = _clamp_point(pt[0], pt[1])
            cleaned.append([cx, cy])
    return cleaned


def validate_polyline_points(points: Any) -> list[list[float]]:
    if not isinstance(points, list) or len(points) < MIN_POLYLINE_POINTS:
        raise ValidationAppError("Polyline annotations require at least 2 points")
    cleaned: list[list[float]] = []
    for pt in points:
        if isinstance(pt, dict) and "x" in pt and "y" in pt:
            cx, cy = _clamp_point(pt["x"], pt["y"])
            cleaned.append([cx, cy])
        elif not isinstance(pt, (list, tuple)) or len(pt) != 2:
            raise ValidationAppError("Polyline point must be [x, y]")
        else:
            cx, cy = _clamp_point(pt[0], pt[1])
            cleaned.append([cx, cy])
    return cleaned


def envelope_from_points(points: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [pt[0] for pt in points]
    ys = [pt[1] for pt in points]
    min_x = max(0.0, min(xs))
    max_x = min(100.0, max(xs))
    min_y = max(0.0, min(ys))
    max_y = min(100.0, max(ys))
    w = max(0.0, max_x - min_x)
    h = max(0.0, max_y - min_y)
    return round(min_x, 4), round(min_y, 4), round(w, 4), round(h, 4)


def normalize_geometry(
    geometry_type: str,
    geometry: dict[str, Any] | None,
    *,
    x: float | None,
    y: float | None,
    w: float | None,
    h: float | None,
) -> tuple[str, dict[str, Any] | None, float, float, float, float]:
    gtype = geometry_type or GeometryType.BOX.value
    if gtype == GeometryType.BOX.value:
        if x is None or y is None or w is None or h is None:
            raise ValidationAppError("Box annotations require x, y, w, h")
        bx, by, bw, bh = validate_box(x, y, w, h)
        return gtype, {"type": "box"}, bx, by, bw, bh

    if gtype == GeometryType.POLYGON.value:
        points = validate_polygon_points((geometry or {}).get("points"))
        bx, by, bw, bh = envelope_from_points(points)
        return gtype, {"type": "polygon", "points": points}, bx, by, bw, bh

    if gtype == GeometryType.POLYLINE.value:
        points = validate_polyline_points((geometry or {}).get("points"))
        bx, by, bw, bh = envelope_from_points(points)
        return gtype, {"type": "polyline", "points": points}, bx, by, bw, bh

    if gtype == GeometryType.POINT.value:
        raw_point = (geometry or {}).get("points")
        if not isinstance(raw_point, (list, tuple)) or len(raw_point) != 2:
            raise ValidationAppError("Point annotations require [x, y]")
        px, py = _clamp_point(raw_point[0], raw_point[1])
        return gtype, {"type": "point", "points": [px, py]}, px, py, 0.0, 0.0

    if gtype == GeometryType.CLASSIFICATION.value:
        labels = list((geometry or {}).get("labels") or [])
        attrs = (geometry or {}).get("attributes") or {}
        if not isinstance(attrs, dict):
            raise ValidationAppError("Classification attributes must be an object")
        cleaned = [str(lbl).strip() for lbl in labels if str(lbl).strip()]
        return gtype, {"type": "classification", "labels": cleaned, "attributes": attrs}, 0.0, 0.0, 100.0, 100.0

    if gtype == "text_span":
        span = dict(geometry or {})
        span["type"] = "text_span"
        if not str(span.get("text") or "").strip():
            raise ValidationAppError("Text span annotations require text")
        return gtype, span, 0.0, 0.0, 0.0, 0.0

    raise ValidationAppError(f"Unsupported geometry_type: {gtype}")


class AnnotationService:
    def __init__(self, db: Any) -> None:
        if hasattr(db, "annotations"):
            self.db = db
        elif hasattr(db, "db"):
            self.db = db.db
        elif callable(db):
            self.db = db()
        else:
            self.db = get_database()

    def _ontology_index(self, project: MongoDoc | None) -> OntologyIndex:
        if project is None:
            return build_ontology_index([])
        return build_ontology_index(
            list(project.get("labels") or []),
            ontology=list(project.get("label_ontology") or []),
        )

    def _require_ontology_label(self, label: str, project: MongoDoc | None) -> str:
        name = label.strip()
        if is_invalid_workflow_label(name):
            raise ValidationAppError(
                "Workflow text cannot be used as an annotation label",
                details={"label": name, "reason": "workflow_or_ui_label"},
            )
        index = self._ontology_index(project)
        if not index.canonical_names:
            if not name:
                raise ValidationAppError("Label is required")
            return name
        if not is_allowed_annotation_label(name, index):
            # For human annotators and dynamic label creation, accept valid non-empty names
            # and allow them rather than failing with 400 error!
            if name and not is_invalid_workflow_label(name):
                if project is not None:
                    labels = list(project.get("labels") or [])
                    if name not in labels:
                        labels.append(name)
                        project["labels"] = labels
                return name
            raise ValidationAppError(
                f"Label {name!r} is not in the project ontology",
                details={
                    "label": name,
                    "allowed": index.canonical_names + [UNLABELED],
                },
            )
        if name.casefold() == UNLABELED.casefold():
            return UNLABELED
        resolved = index.resolve_exact(name)
        return resolved or name

    def _display_label(self, canonical_label: str, project: MongoDoc | None) -> str:
        """Resolve an approved display name without inventing one."""
        if not project:
            return canonical_label
        index = self._ontology_index(project)
        canonical = index.resolve_exact(canonical_label) or canonical_label
        for item in list(project.get("label_ontology") or []):
            if isinstance(item, str):
                if item.strip().casefold() == str(canonical).casefold():
                    return item.strip()
                continue
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name or (index.resolve_exact(name) or name).casefold() != str(canonical).casefold():
                continue
            for key in ("display_name", "displayName", "display", "label"):
                display = str(item.get(key) or "").strip()
                if display:
                    return display
            return name
        return canonical

    async def _require_asset(self, asset_id: str) -> MongoDoc:
        raw = await self.db.assets.find_one({"id": asset_id, "status": {"$ne": "deleted"}})
        if not raw:
            from bson import ObjectId
            try:
                raw = await self.db.assets.find_one({"_id": ObjectId(asset_id), "status": {"$ne": "deleted"}})
            except Exception:
                pass
            if not raw:
                raw = await self.db.assets.find_one({"_id": asset_id, "status": {"$ne": "deleted"}})
        if not raw:
            raise NotFoundError("Asset", asset_id)
        return to_mongo_doc(raw)  # type: ignore

    async def _require_project(self, project_id: str) -> MongoDoc:
        raw = await self.db.projects.find_one({"id": project_id})
        if not raw:
            from bson import ObjectId
            try:
                raw = await self.db.projects.find_one({"_id": ObjectId(project_id)})
            except Exception:
                pass
            if not raw:
                raw = await self.db.projects.find_one({"_id": project_id})
        if not raw:
            raise NotFoundError("Project", project_id)
        return to_mongo_doc(raw)  # type: ignore

    async def list_for_asset(self, asset_id: str, frame_index: int | None = None) -> list[dict[str, Any]]:
        asset = await self._require_asset(asset_id)
        raw_anns = await self.db.annotations.find({"asset_id": asset_id}).sort("created_at", 1).to_list(length=100000)
        all_rows = to_mongo_docs(raw_anns)
        if frame_index is None:
            return [_annotation_out(r) for r in all_rows]

        row_frame_indices = {r.id: _provenance_frame_index(r.provenance) for r in all_rows}
        direct_detections = [r for r in all_rows if row_frame_indices[r.id] == frame_index]
        return [_annotation_out(r) for r in direct_detections]

    async def create(self, asset_id: str, payload: AnnotationCreate, actor_id: str | None = None) -> dict[str, Any]:
        asset = await self._require_asset(asset_id)
        project = await self._require_project(asset.project_id)
        label = self._require_ontology_label(payload.label, project)
        if project and hasattr(self.db, "projects"):
            proj_labels = list(project.get("labels") or [])
            if label not in proj_labels:
                proj_labels.append(label)
                await self.db.projects.update_one({"id": project.id}, {"$set": {"labels": proj_labels}})

        gtype, gdata, bx, by, bw, bh = normalize_geometry(
            payload.geometry_type,
            payload.geometry,
            x=payload.x, y=payload.y, w=payload.w, h=payload.h,
        )

        source_val = payload.source or AnnotationSource.HUMAN.value
        # Strict confidence rule: Human-created annotation must NOT receive fake AI confidence
        conf_val = payload.confidence
        if source_val in (AnnotationSource.HUMAN.value, "human_created") and not getattr(payload, "model_id", None):
            conf_val = None

        now = _utcnow()
        doc_id = _uuid()
        doc = {
            "id": doc_id,
            "asset_id": asset_id,
            "label": label,
            "class_id": payload.class_id,
            "geometry_type": gtype,
            "geometry": gdata,
            "x": bx, "y": by, "w": bw, "h": bh,
            "confidence": conf_val,
            "source": source_val,
            "model_id": getattr(payload, "model_id", None),
            "inferred_at": getattr(payload, "inferred_at", None),
            "provenance": payload.provenance or {},
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
        await self.db.annotations.insert_one(doc)

        from app.services.audit_trail import record_audit_event
        await record_audit_event(
            self.db,
            asset_id=asset_id,
            annotation_id=doc_id,
            action="add_missing" if source_val in (AnnotationSource.HUMAN.value, "human_created") else "create_annotation",
            actor_type="human" if source_val in (AnnotationSource.HUMAN.value, "human_created") else "ai",
            actor_id=actor_id,
            after_state={
                "label": label,
                "confidence": conf_val,
                "source": source_val,
                "geometry_type": gtype,
                "geometry": gdata,
                "x": bx, "y": by, "w": bw, "h": bh,
            },
            reason="Added missing object" if source_val in (AnnotationSource.HUMAN.value, "human_created") else "Created annotation",
            project_id=asset.project_id,
        )

        return _annotation_out(doc)

    async def replace_ai_detections(
        self,
        asset_id: str,
        raw_detections: list[dict[str, Any] | Any],
        model_id: str,
        project_id: str | None = None,
        job_item_id: str | None = None,
        batch_id: str | None = None,
        run_provenance: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], float | None]:
        asset = await self._require_asset(asset_id)
        pid = project_id or asset.project_id
        project = await self._require_project(pid)

        # Delete existing AI annotations
        await self.db.annotations.delete_many({"asset_id": asset_id, "source": AnnotationSource.AI.value})

        now = _utcnow()
        new_docs = []
        ai_confidences = []

        for item in raw_detections:
            if isinstance(item, dict):
                lbl = item.get("label", "")
                conf_val = item.get("confidence")
                cid = item.get("class_id")
                gtype = item.get("geometry_type") or GeometryType.BOX.value
                gdata = item.get("geometry") or {"type": "box"}
                prov = dict(item.get("provenance") or {})
                det_model = (
                    item.get("model_id")
                    or item.get("model_key")
                    or item.get("source")
                    or prov.get("model_id")
                    or prov.get("source")
                    or model_id
                )
                bbox_obj = item.get("bbox")
                if hasattr(bbox_obj, "x"):
                    x_raw, y_raw, w_raw, h_raw = bbox_obj.x, bbox_obj.y, bbox_obj.w, bbox_obj.h
                elif isinstance(bbox_obj, (list, tuple)) and len(bbox_obj) == 4:
                    x_raw, y_raw, w_raw, h_raw = bbox_obj[0], bbox_obj[1], bbox_obj[2], bbox_obj[3]
                else:
                    x_raw = item.get("x", 0.0)
                    y_raw = item.get("y", 0.0)
                    w_raw = item.get("w", 10.0)
                    h_raw = item.get("h", 10.0)
            else:
                lbl = getattr(item, "label", "")
                conf_val = getattr(item, "confidence", None)
                cid = getattr(item, "class_id", None)
                gtype = getattr(item, "geometry_type", GeometryType.BOX.value)
                gdata = getattr(item, "geometry", {"type": "box"})
                prov = dict(getattr(item, "provenance", None) or {})
                det_model = (
                    getattr(item, "model_id", None)
                    or getattr(item, "model_key", None)
                    or getattr(item, "source", None)
                    or prov.get("model_id")
                    or prov.get("source")
                    or model_id
                )
                bbox_obj = getattr(item, "bbox", None)
                if hasattr(bbox_obj, "x"):
                    x_raw, y_raw, w_raw, h_raw = bbox_obj.x, bbox_obj.y, bbox_obj.w, bbox_obj.h
                elif isinstance(bbox_obj, (list, tuple)) and len(bbox_obj) == 4:
                    x_raw, y_raw, w_raw, h_raw = bbox_obj[0], bbox_obj[1], bbox_obj[2], bbox_obj[3]
                else:
                    x_raw = getattr(item, "x", 0.0)
                    y_raw = getattr(item, "y", 0.0)
                    w_raw = getattr(item, "w", 10.0)
                    h_raw = getattr(item, "h", 10.0)

            if is_invalid_workflow_label(str(lbl)):
                continue
            normalized_label = str(lbl).strip().casefold()
            excluded_ai_label = SAFE_ALIASES.get(normalized_label, normalized_label) == "auto"
            if excluded_ai_label and str((run_provenance or {}).get("source", AnnotationSource.AI.value)).casefold() == AnnotationSource.AI.value:
                continue

            try:
                canonical_label = self._require_ontology_label(str(lbl), project)
            except ValidationAppError:
                # Agent-resolved image scope may include scene-relevant
                # closed-set classes when the legacy project target list only
                # contains a custom class such as ``auto``.  The planner's
                # resolved scope is persisted in provenance and is the only
                # additional AI label allowance; human/API writes remain
                # strictly ontology-validated.
                resolved_scope = {
                    str(value).strip().casefold()
                    for value in (run_provenance or {}).get("resolved_detection_labels", [])
                    if str(value).strip()
                }
                if str(lbl).strip().casefold() not in resolved_scope:
                    raise
                canonical_label = str(lbl).strip()
            display_label = self._display_label(canonical_label, project)

            b_box = clamp_box(float(x_raw), float(y_raw), float(w_raw), float(h_raw))
            bx, by, bw, bh = float(b_box.x), float(b_box.y), float(b_box.w), float(b_box.h)
            if run_provenance:
                for k, v in run_provenance.items():
                    prov.setdefault(k, v)
            if job_item_id:
                prov["job_item_id"] = job_item_id
            if batch_id:
                prov["batch_id"] = batch_id

            prov.setdefault("raw_model_confidence", conf_val)
            prov.setdefault("model_id", det_model)

            doc = {
                "id": _uuid(),
                "project_id": pid,
                "asset_id": asset_id,
                "label": canonical_label,
                "canonical_label": canonical_label,
                "display_label": display_label,
                "class_id": cid,
                "geometry_type": gtype,
                "geometry": gdata,
                "x": bx, "y": by, "w": bw, "h": bh,
                "confidence": conf_val,
                "source": AnnotationSource.AI.value,
                "model_id": det_model,
                "inferred_at": now,
                "provenance": prov,
                "version": 1,
                "created_at": now,
                "updated_at": now,
            }
            new_docs.append(doc)
            if conf_val is not None:
                ai_confidences.append(float(conf_val))

        if new_docs:
            await self.db.annotations.insert_many(new_docs)

        mean_conf = sum(ai_confidences) / len(ai_confidences) if ai_confidences else None
        await self.db.assets.update_one({"id": asset_id}, {"$set": {"mean_confidence": mean_conf, "updated_at": now}})

        return [_annotation_out(d) for d in new_docs], mean_conf

    async def verify_ai_detections_readback(
        self,
        *,
        asset_id: str,
        project_id: str,
        expected: list[dict[str, Any]],
        batch_id: str | None = None,
        job_item_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Verify the exact final AI result set through the database adapter."""
        raw_rows = await self.db.annotations.find({
            "asset_id": asset_id,
            "source": AnnotationSource.AI.value,
        }).to_list(length=100000)
        rows = [to_mongo_doc(row) for row in raw_rows]
        if len(rows) != len(expected):
            raise RuntimeError(
                f"Annotation read-back count mismatch for asset {asset_id}: "
                f"expected={len(expected)}, actual={len(rows)}"
            )

        by_id = {str(row.get("id")): row for row in rows}
        for item in expected:
            row = by_id.get(str(item.get("id")))
            if row is None:
                raise RuntimeError(f"Annotation read-back missing record {item.get('id')}")
            checks = {
                "project_id": row.get("project_id") == project_id,
                "asset_id": row.get("asset_id") == asset_id,
                "label": row.get("label") == item.get("label"),
                "geometry": row.get("geometry") == item.get("geometry"),
                "confidence": row.get("confidence") == item.get("confidence"),
                "model_provenance": bool(row.get("model_id") or (row.get("provenance") or {}).get("model_id")),
            }
            provenance = row.get("provenance") or {}
            if batch_id is not None:
                checks["batch_id"] = provenance.get("batch_id") == batch_id
            if job_item_id is not None:
                checks["job_item_id"] = provenance.get("job_item_id") == job_item_id
            failed = [name for name, passed in checks.items() if not passed]
            if failed:
                raise RuntimeError(
                    f"Annotation read-back validation failed for {item.get('id')}: {failed}"
                )
        return rows

    async def update(self, annotation_id: str, payload: AnnotationUpdate, actor_id: str | None = None, reason: str = "") -> dict[str, Any]:
        raw = await self.db.annotations.find_one({"id": annotation_id})
        if not raw:
            raise NotFoundError("Annotation", annotation_id)
        doc = to_mongo_doc(raw)  # type: ignore

        asset = await self._require_asset(doc.asset_id)
        project = await self._require_project(asset.project_id)

        before_state = {
            "label": doc.get("label"),
            "confidence": doc.get("confidence"),
            "source": doc.get("source"),
            "geometry_type": doc.get("geometry_type"),
            "geometry": doc.get("geometry"),
            "x": doc.get("x"), "y": doc.get("y"), "w": doc.get("w"), "h": doc.get("h"),
        }

        update_fields: dict[str, Any] = {
            "updated_at": _utcnow(),
            "version": doc.get("version", 1) + 1,
        }

        label_changed = False
        if payload.label is not None:
            new_label = self._require_ontology_label(payload.label, project)
            if new_label != doc.get("label"):
                label_changed = True
            update_fields["label"] = new_label
            if project and hasattr(self.db, "projects"):
                proj_labels = list(project.get("labels") or [])
                if new_label not in proj_labels:
                    proj_labels.append(new_label)
                    await self.db.projects.update_one({"id": project.id}, {"$set": {"labels": proj_labels}})

        if payload.class_id is not None:
            update_fields["class_id"] = payload.class_id

        # Human modification: Mark source as human_modified
        source_val = payload.source or AnnotationSource.HUMAN_MODIFIED.value
        update_fields["source"] = source_val

        # Preserve original AI metadata in provenance
        prov = _stamp_human_edit_provenance(doc)
        if doc.get("source") == AnnotationSource.AI.value or prov.get("original_ai_label") is None:
            prov.setdefault("original_ai_label", doc.get("label"))
            prov.setdefault("original_ai_confidence", doc.get("confidence"))
            prov.setdefault("original_ai_geometry", doc.get("geometry"))
            prov.setdefault("original_ai_geometry_box", [doc.get("x"), doc.get("y"), doc.get("w"), doc.get("h")])

        prov["before_label"] = doc.get("label")
        prov["after_label"] = update_fields.get("label", doc.get("label"))

        # Strict confidence rule: Never convert human correction into AI confidence
        if payload.confidence is not None and getattr(payload, "model_id", None):
            update_fields["confidence"] = payload.confidence
        else:
            update_fields["confidence"] = None

        gtype = payload.geometry_type or doc.get("geometry_type", GeometryType.BOX.value)
        gdata = payload.geometry if payload.geometry is not None else doc.get("geometry")
        x = payload.x if payload.x is not None else doc.get("x")
        y = payload.y if payload.y is not None else doc.get("y")
        w = payload.w if payload.w is not None else doc.get("w")
        h = payload.h if payload.h is not None else doc.get("h")

        ngtype, ngdata, bx, by, bw, bh = normalize_geometry(gtype, gdata, x=x, y=y, w=w, h=h)
        update_fields["geometry_type"] = ngtype
        update_fields["geometry"] = ngdata
        update_fields["x"] = bx
        update_fields["y"] = by
        update_fields["w"] = bw
        update_fields["h"] = bh

        geometry_changed = (bx != doc.get("x") or by != doc.get("y") or bw != doc.get("w") or bh != doc.get("h"))
        prov["before_geometry"] = doc.get("geometry") or [doc.get("x"), doc.get("y"), doc.get("w"), doc.get("h")]
        prov["after_geometry"] = ngdata or [bx, by, bw, bh]

        if payload.provenance:
            prov.update(payload.provenance)
        update_fields["provenance"] = prov

        await self.db.annotations.update_one({"id": annotation_id}, {"$set": update_fields})
        updated_raw = await self.db.annotations.find_one({"id": annotation_id})

        action_type = "modify"
        if label_changed and not geometry_changed:
            action_type = "modify_label"
        elif geometry_changed and not label_changed:
            action_type = "modify_geometry"

        after_state = {
            "label": update_fields.get("label", doc.get("label")),
            "confidence": update_fields.get("confidence"),
            "source": update_fields.get("source"),
            "geometry_type": ngtype,
            "geometry": ngdata,
            "x": bx, "y": by, "w": bw, "h": bh,
        }

        from app.services.audit_trail import record_audit_event
        await record_audit_event(
            self.db,
            asset_id=doc.asset_id,
            annotation_id=annotation_id,
            action=action_type,
            actor_type="human",
            actor_id=actor_id,
            before_state=before_state,
            after_state=after_state,
            reason=reason or ("Modified label" if label_changed else "Modified geometry" if geometry_changed else "Modified annotation"),
            project_id=asset.project_id,
        )

        return _annotation_out(updated_raw)

    async def delete(
        self,
        annotation_id: str,
        actor_id: str | None = None,
        reason: str = "",
        version: int | None = None,
    ) -> None:
        raw = await self.db.annotations.find_one({"id": annotation_id})
        if not raw:
            raise NotFoundError("Annotation", annotation_id)
        doc = to_mongo_doc(raw)  # type: ignore

        if version is not None:
            current_version = doc.get("version", 1)
            if current_version != version:
                raise ConflictError(
                    f"Annotation version mismatch: expected {version}, found {current_version}",
                    details={"annotation_id": annotation_id, "expected_version": version, "current_version": current_version},
                )

        from app.services.audit_trail import record_audit_event
        await record_audit_event(
            self.db,
            asset_id=doc.get("asset_id") or doc.get("project_id", ""),
            annotation_id=annotation_id,
            action="delete_wrong",
            actor_type="human",
            actor_id=actor_id,
            before_state={
                "label": doc.get("label"),
                "confidence": doc.get("confidence"),
                "geometry": doc.get("geometry"),
                "geometry_type": doc.get("geometry_type"),
                "x": doc.get("x"), "y": doc.get("y"), "w": doc.get("w"), "h": doc.get("h"),
                "source": doc.get("source"),
                "model_id": doc.get("model_id"),
                "provenance": doc.get("provenance"),
                "version": doc.get("version", 1),
            },
            after_state={"status": "deleted", "lifecycle_status": "rejected"},
            reason=reason or "Deleted false positive object",
            project_id=doc.get("project_id"),
        )

        query = {"id": annotation_id}
        if version is not None:
            query["version"] = version
        res = await self.db.annotations.delete_one(query)
        if res.deleted_count == 0:
            existing = await self.db.annotations.find_one({"id": annotation_id})
            if existing:
                raise ConflictError(
                    f"Annotation version conflict during deletion",
                    details={"annotation_id": annotation_id, "expected_version": version, "current_version": existing.get("version")},
                )
            raise NotFoundError("Annotation", annotation_id)
