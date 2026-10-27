"""Granular classification service: CLIP scoring + hierarchical taxonomy persistence."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from app.db.firebase import AsyncIOMotorDatabase

from app.config import Settings
from app.db.models import MongoDoc
from app.domain.enums import ModelRunStatus
from app.errors import NotFoundError, ValidationAppError
from app.inference.contracts import BoundingBoxPercent, ModelKey
from app.inference.registry import ModelRegistry
from app.logging import get_logger
from app.mcp.tools import classification as classification_tool
from app.storage.files import FileStorage

logger = get_logger(__name__)

_TAXONOMY_SEPARATORS = re.compile(r"[.>/]")
_DEFAULT_TAXONOMY_NAME = "default"


def _attribute_out(row: MongoDoc) -> dict[str, Any]:
    tax_path = row.get("taxonomy_path")
    return {
        "id": row.get("id"),
        "annotation_id": row.get("annotation_id"),
        "label": row.get("label"),
        "taxonomy_path": tax_path,
        "taxonomy_hierarchy": tax_path.split(".") if tax_path else [],
        "confidence": float(row.get("confidence", 0.0)),
        "attributes": row.get("attributes") or {},
        "model_id": row.get("model_id"),
        "model_key": row.get("model_key"),
        "source": row.get("source"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


class ClassificationService:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        settings: Settings,
        storage: FileStorage,
        registry: ModelRegistry,
    ) -> None:
        self.db = db
        self.settings = settings
        self.storage = storage
        self.registry = registry

    async def classify(
        self,
        project_id: str,
        asset_id: str,
        regions: list[dict[str, Any]],
        model: str = ModelKey.CLIP.value,
        threshold: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Runs CLIP over each region and persists multi-label results (idempotent)."""
        asset_doc = await self.db["assets"].find_one({"id": asset_id})
        if asset_doc is None or asset_doc.get("project_id") != project_id:
            raise NotFoundError("Asset not found", details={"asset_id": asset_id, "project_id": project_id})
        asset = MongoDoc(asset_doc)
        if not regions:
            raise ValidationAppError("At least one region is required", details={"asset_id": asset_id})
        image_path = self.storage.resolve(asset.get("storage_path"))

        annotation_ids: list[str | None] = []
        bboxes: list[BoundingBoxPercent] = []
        region_labels: list[list[str]] = []
        for region in regions:
            annotation_id = region.get("annotation_id")
            if annotation_id:
                ann_doc = await self.db["annotations"].find_one({"id": annotation_id})
                if ann_doc is None or ann_doc.get("asset_id") != asset_id:
                    raise ValidationAppError(
                        "annotation_id does not belong to asset",
                        details={"annotation_id": annotation_id, "asset_id": asset_id},
                    )
                ann = MongoDoc(ann_doc)
                bbox = BoundingBoxPercent(x=float(ann.x), y=float(ann.y), w=float(ann.w), h=float(ann.h))
            else:
                box = region.get("bbox") or {}
                bbox = BoundingBoxPercent(
                    x=float(box.get("x", 0.0)),
                    y=float(box.get("y", 0.0)),
                    w=float(box.get("w", 100.0)),
                    h=float(box.get("h", 100.0)),
                )
            annotation_ids.append(annotation_id)
            bboxes.append(bbox)
            region_labels.append(list(region.get("text_labels") or []))

        all_labels: list[str] = []
        seen: set[str] = set()
        for labels in region_labels:
            for lbl in labels:
                if lbl not in seen:
                    seen.add(lbl)
                    all_labels.append(lbl)
        if not all_labels:
            raise ValidationAppError("At least one region must include text_labels", details={"asset_id": asset_id})

        adapter_model_id = model
        try:
            adapter_model_id = getattr(self.registry.get(model), "model_id", model)
        except Exception:  # noqa: BLE001 - purely cosmetic fallback for the run record
            pass

        run_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        run = MongoDoc({
            "id": run_id,
            "asset_id": asset_id,
            "model_key": model,
            "model_id": adapter_model_id,
            "status": ModelRunStatus.RUNNING.value,
            "purpose": "classify_attributes",
            "started_at": now,
            "finished_at": None,
            "error_message": None,
            "detection_count": 0,
        })
        await self.db["model_runs"].insert_one(dict(run))

        result = classification_tool.classify_objects(
            self.registry,
            image_path,
            asset_id=asset_id,
            regions=list(zip(annotation_ids, bboxes, strict=True)),
            text_labels=all_labels,
            model=model,
        )
        if not result.success:
            message = result.error.message if result.error else "classification failed"
            await self.db["model_runs"].update_one(
                {"id": run_id},
                {"$set": {
                    "status": ModelRunStatus.FAILED.value,
                    "error_message": message,
                    "finished_at": datetime.now(UTC),
                }}
            )
            raise ValidationAppError(message, details=result.error.details if result.error else {})

        classifications = result.data or []
        out: list[dict[str, Any]] = []
        for cls_result, wanted_labels in zip(classifications, region_labels, strict=True):
            wanted = set(wanted_labels) or set(all_labels)
            candidates = [
                c for c in cls_result.attributes.get("candidates", []) if c["label"] in wanted
            ] or cls_result.attributes.get("candidates", [])
            if not candidates:
                continue
            candidates = sorted(candidates, key=lambda c: c["score"], reverse=True)
            # Multi-label: keep every candidate clearing the threshold; always keep the best one.
            selected = [c for c in candidates if c["score"] >= threshold] or candidates[:1]
            for candidate in selected:
                if cls_result.annotation_id:
                    saved = await self._persist_attribute(
                        project_id=project_id,
                        annotation_id=cls_result.annotation_id,
                        label=candidate["label"],
                        confidence=float(candidate["score"]),
                        candidates=candidates,
                        model=model,
                        model_id=cls_result.model_id,
                    )
                    out.append(saved)
                else:
                    out.append(
                        {
                            "annotation_id": None,
                            "label": candidate["label"],
                            "confidence": float(candidate["score"]),
                            "attributes": {"candidates": candidates},
                        }
                    )

        await self.db["model_runs"].update_one(
            {"id": run_id},
            {"$set": {
                "status": ModelRunStatus.SUCCEEDED.value,
                "detection_count": len(out),
                "finished_at": datetime.now(UTC),
            }}
        )
        return out

    async def _persist_attribute(
        self,
        *,
        project_id: str,
        annotation_id: str,
        label: str,
        confidence: float,
        candidates: list[dict[str, Any]],
        model: str,
        model_id: str,
    ) -> dict[str, Any]:
        taxonomy_node_id: str | None = None
        taxonomy_path: str | None = None
        if _TAXONOMY_SEPARATORS.search(label):
            node = await self._resolve_taxonomy_path(project_id, label)
            taxonomy_node_id = node.id
            taxonomy_path = node.path

        existing_doc = await self.db["annotation_attributes"].find_one({
            "annotation_id": annotation_id,
            "label": label,
        })

        attrs = {"candidates": candidates}
        now = datetime.now(UTC)
        if existing_doc is not None:
            existing = MongoDoc(existing_doc)
            updates = {
                "confidence": confidence,
                "attributes": attrs,
                "taxonomy_node_id": taxonomy_node_id,
                "taxonomy_path": taxonomy_path,
                "model_id": model_id,
                "model_key": model,
                "updated_at": now,
            }
            await self.db["annotation_attributes"].update_one({"id": existing.id}, {"$set": updates})
            existing.update(updates)
            row = existing
        else:
            row = MongoDoc({
                "id": str(uuid.uuid4()),
                "annotation_id": annotation_id,
                "taxonomy_node_id": taxonomy_node_id,
                "label": label,
                "taxonomy_path": taxonomy_path,
                "confidence": confidence,
                "attributes": attrs,
                "model_id": model_id,
                "model_key": model,
                "source": "model",
                "created_at": now,
                "updated_at": now,
            })
            await self.db["annotation_attributes"].insert_one(dict(row))
        return _attribute_out(row)

    async def _resolve_taxonomy_path(self, project_id: str, label: str) -> MongoDoc:
        parts = [p.strip().lower() for p in _TAXONOMY_SEPARATORS.split(label) if p.strip()]
        taxonomy_doc = await self.db["taxonomies"].find_one({
            "project_id": project_id,
            "name": _DEFAULT_TAXONOMY_NAME,
        })
        now = datetime.now(UTC)
        if taxonomy_doc is None:
            tax_row = MongoDoc({
                "id": str(uuid.uuid4()),
                "project_id": project_id,
                "name": _DEFAULT_TAXONOMY_NAME,
                "description": "Auto-created classification taxonomy",
                "created_at": now,
            })
            await self.db["taxonomies"].insert_one(dict(tax_row))
            taxonomy = tax_row
        else:
            taxonomy = MongoDoc(taxonomy_doc)

        parent: MongoDoc | None = None
        node: MongoDoc | None = None
        path_parts: list[str] = []
        for part in parts:
            path_parts.append(part)
            path = ".".join(path_parts)
            node_doc = await self.db["taxonomy_nodes"].find_one({
                "taxonomy_id": taxonomy.id,
                "path": path,
            })
            if node_doc is None:
                node = MongoDoc({
                    "id": str(uuid.uuid4()),
                    "taxonomy_id": taxonomy.id,
                    "parent_id": parent.id if parent else None,
                    "name": part,
                    "path": path,
                    "depth": len(path_parts) - 1,
                    "created_at": now,
                })
                await self.db["taxonomy_nodes"].insert_one(dict(node))
            else:
                node = MongoDoc(node_doc)
            parent = node
        assert node is not None
        return node

    async def get_annotations(self, project_id: str, asset_id: str) -> list[dict[str, Any]]:
        """Returns each annotation with its multi-label classification attributes and hierarchy."""
        asset_doc = await self.db["assets"].find_one({"id": asset_id})
        if asset_doc is None or asset_doc.get("project_id") != project_id:
            raise NotFoundError("Asset not found", details={"asset_id": asset_id, "project_id": project_id})

        ann_cursor = self.db["annotations"].find({"asset_id": asset_id})
        ann_rows = [MongoDoc(d) async for d in ann_cursor]
        ann_ids = [a.id for a in ann_rows]
        attr_rows: list[MongoDoc] = []
        if ann_ids:
            attr_cursor = self.db["annotation_attributes"].find({"annotation_id": {"$in": ann_ids}})
            attr_rows = [MongoDoc(d) async for d in attr_cursor]

        by_annotation: dict[str, list[MongoDoc]] = {}
        for row in attr_rows:
            by_annotation.setdefault(row.get("annotation_id"), []).append(row)

        out: list[dict[str, Any]] = []
        for ann in ann_rows:
            attrs = sorted(by_annotation.get(ann.id, []), key=lambda r: float(r.get("confidence", 0.0)), reverse=True)
            out.append(
                {
                    "annotation_id": ann.id,
                    "label": ann.get("label"),
                    "attributes": [_attribute_out(a) for a in attrs],
                }
            )
        return out

    async def save_attribute(
        self,
        annotation_id: str,
        label: str,
        attributes: dict[str, Any],
        confidence: float = 1.0,
        source: str = "human",
    ) -> dict[str, Any]:
        """Saves or updates a classification attribute / additional label for an annotation."""
        ann_doc = await self.db["annotations"].find_one({"id": annotation_id})
        if ann_doc is None:
            raise NotFoundError("Annotation not found", details={"annotation_id": annotation_id})

        existing_doc = await self.db["annotation_attributes"].find_one({
            "annotation_id": annotation_id,
            "label": label,
        })
        now = datetime.now(UTC)
        if existing_doc is not None:
            existing = MongoDoc(existing_doc)
            updates = {
                "attributes": attributes,
                "confidence": confidence,
                "source": source,
                "updated_at": now,
            }
            await self.db["annotation_attributes"].update_one({"id": existing.id}, {"$set": updates})
            existing.update(updates)
            row = existing
        else:
            row = MongoDoc({
                "id": str(uuid.uuid4()),
                "annotation_id": annotation_id,
                "label": label,
                "confidence": confidence,
                "attributes": attributes,
                "source": source,
                "created_at": now,
                "updated_at": now,
            })
            await self.db["annotation_attributes"].insert_one(dict(row))

        return _attribute_out(row)

    async def delete_attribute(self, annotation_id: str, label: str) -> None:
        """Deletes a classification attribute / additional label for an annotation."""
        await self.db["annotation_attributes"].delete_one({
            "annotation_id": annotation_id,
            "label": label,
        })

    async def upsert_classification(
        self,
        annotation_id: str,
        labels: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Batch-upsert granular classification labels for one annotation."""
        ann_doc = await self.db["annotations"].find_one({"id": annotation_id})
        if ann_doc is None:
            raise NotFoundError("Annotation not found", details={"annotation_id": annotation_id})
        ann = MongoDoc(ann_doc)
        asset_doc = await self.db["assets"].find_one({"id": ann.get("asset_id")})
        if asset_doc is None:
            raise NotFoundError("Asset not found for annotation", details={"annotation_id": annotation_id})
        project_id = asset_doc.get("project_id")

        out: list[dict[str, Any]] = []
        now = datetime.now(UTC)
        for entry in labels:
            label = entry["label"]
            user_attrs: dict[str, Any] = dict(entry.get("attributes") or {})
            confidence = float(entry.get("confidence") or 1.0)
            source = entry.get("source") or "human"
            review_status = entry.get("review_status")
            if review_status:
                user_attrs["review_status"] = review_status

            # Resolve taxonomy path when label contains separators
            taxonomy_node_id: str | None = None
            taxonomy_path: str | None = None
            if _TAXONOMY_SEPARATORS.search(label):
                node = await self._resolve_taxonomy_path(project_id, label)
                taxonomy_node_id = node.id
                taxonomy_path = node.path

            existing_doc = await self.db["annotation_attributes"].find_one({
                "annotation_id": annotation_id,
                "label": label,
            })

            if existing_doc is not None:
                existing = MongoDoc(existing_doc)
                updates = {
                    "confidence": confidence,
                    "attributes": user_attrs,
                    "source": source,
                    "taxonomy_node_id": taxonomy_node_id,
                    "taxonomy_path": taxonomy_path,
                    "updated_at": now,
                }
                await self.db["annotation_attributes"].update_one({"id": existing.id}, {"$set": updates})
                existing.update(updates)
                row = existing
            else:
                row = MongoDoc({
                    "id": str(uuid.uuid4()),
                    "annotation_id": annotation_id,
                    "taxonomy_node_id": taxonomy_node_id,
                    "label": label,
                    "taxonomy_path": taxonomy_path,
                    "confidence": confidence,
                    "attributes": user_attrs,
                    "source": source,
                    "model_key": "",
                    "model_id": "",
                    "created_at": now,
                    "updated_at": now,
                })
                await self.db["annotation_attributes"].insert_one(dict(row))

            out.append(_attribute_out(row))

        logger.info(
            "annotation_classification_upserted",
            annotation_id=annotation_id,
            label_count=len(labels),
        )
        return out

    async def classify_region(
        self,
        project_id: str,
        asset_id: str,
        annotation_id: str,
        text_labels: list[str],
        model: str = "clip",
        threshold: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Run CLIP on the cropped region of an existing annotation."""
        regions = [{"annotation_id": annotation_id, "text_labels": text_labels}]
        results = await self.classify(
            project_id=project_id,
            asset_id=asset_id,
            regions=regions,
            model=model,
            threshold=threshold,
        )
        # Stamp review_status=ai_proposed on newly created rows
        for result in results:
            if result.get("annotation_id"):
                existing_doc = await self.db["annotation_attributes"].find_one({
                    "annotation_id": result["annotation_id"],
                    "label": result["label"],
                })
                if existing_doc is not None:
                    existing = MongoDoc(existing_doc)
                    attrs = dict(existing.get("attributes") or {})
                    if "review_status" not in attrs:
                        attrs["review_status"] = "ai_proposed"
                        await self.db["annotation_attributes"].update_one(
                            {"id": existing.id},
                            {"$set": {"attributes": attrs, "updated_at": datetime.now(UTC)}}
                        )
                        existing["attributes"] = attrs
                        result.update(_attribute_out(existing))
        return results


