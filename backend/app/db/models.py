"""Firestore database initialization and the existing document/session surface."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.db.firebase import FirebaseDatabase, init_firebase, AsyncIOMotorDatabase
from app.logging import get_logger

logger = get_logger(__name__)

_firebase_db: FirebaseDatabase | None = None
_active_db: FirebaseDatabase | None = None


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return str(uuid4())


class MongoDoc(dict):
    """Dict subclass that allows attribute access (doc.id, doc.name) for document fields."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'MongoDoc' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    def __delattr__(self, name: str) -> None:
        try:
            del self[name]
        except KeyError:
            raise AttributeError(f"'MongoDoc' object has no attribute '{name}'")


def _normalize_points_in_structure(val: Any) -> Any:
    if isinstance(val, dict):
        return {k: _normalize_points_in_structure(v) for k, v in val.items()}
    if isinstance(val, list):
        res: list[Any] = []
        for item in val:
            if isinstance(item, dict) and "x" in item and "y" in item and len(item) == 2:
                try:
                    res.append([float(item["x"]), float(item["y"])])
                except (ValueError, TypeError):
                    res.append(_normalize_points_in_structure(item))
            else:
                res.append(_normalize_points_in_structure(item))
        return res
    return val


def to_mongo_doc(doc: dict[str, Any] | None) -> MongoDoc | None:
    if doc is None:
        return None
    d = dict(doc)
    d.pop("_id", None)
    d = _normalize_points_in_structure(d)
    return MongoDoc(d)


def to_mongo_docs(docs: list[dict[str, Any]]) -> list[MongoDoc]:
    return [to_mongo_doc(d) for d in docs if d is not None]  # type: ignore


class MongoSession:
    """Async session wrapper mapping persistence calls directly to MongoDB collections."""

    def __init__(self, db: FirebaseDatabase | None = None) -> None:
        self.db = db if db is not None else get_database()
        self.is_active = True
        self._pending_adds: list[tuple[str, dict[str, Any]]] = []

    async def __aenter__(self) -> MongoSession:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.flush()

    def _resolve_collection(self, model_cls_or_inst: Any) -> str:
        col_name = getattr(model_cls_or_inst, "__tablename__", None)
        if col_name:
            return col_name

        cls = model_cls_or_inst if isinstance(model_cls_or_inst, type) else type(model_cls_or_inst)
        cls_name = getattr(cls, "__name__", str(cls)).lower()
        if cls_name.endswith("row"):
            cls_name = cls_name[:-3]

        mapping = {
            "batch": "batches",
            "jobitem": "job_items",
            "job_item": "job_items",
            "asset": "assets",
            "project": "projects",
            "annotation": "annotations",
            "decision": "decisions",
            "taxonomy": "taxonomies",
            "taxonomynode": "taxonomy_nodes",
            "taxonomy_node": "taxonomy_nodes",
            "annotationattribute": "annotation_attributes",
            "annotationattributes": "annotation_attributes",
            "annotation_attributes": "annotation_attributes",
            "cloudconnection": "cloud_connections",
            "dataconnection": "cloud_connections",
            "cloud_connection": "cloud_connections",
            "data_connection": "cloud_connections",
            "projectrecon": "project_recons",
            "project_recon": "project_recons",
            "usageevent": "usage_events",
            "usage_event": "usage_events",
            "agentrequest": "agent_requests",
            "agent_request": "agent_requests",
            "projectplan": "project_plans",
            "project_plan": "project_plans",
            "reviewnote": "review_notes",
            "review_note": "review_notes",
            "mask": "masks",
            "modelrun": "model_runs",
            "model_run": "model_runs",
            "seedstate": "seed_state",
            "seed_state": "seed_state",
        }
        if cls_name in mapping:
            return mapping[cls_name]

        if isinstance(model_cls_or_inst, (dict, MongoDoc)):
            d = model_cls_or_inst
            if "annotation_id" in d and "attributes" in d:
                return "annotation_attributes"
            if "asset_id" in d and ("geometry" in d or "geometry_type" in d):
                return "annotations"
            if "batch_id" in d and "asset_id" in d:
                return "job_items"
            if "model_id" in d and ("asset_id" in d or "purpose" in d):
                return "model_runs"
            if "project_id" in d and "batch_type" in d:
                return "batches"
            if "project_id" in d and "review_status" in d:
                return "assets"
            if "task_type" in d and ("labels" in d or "goal" in d):
                return "projects"
            if "key" in d:
                return "seed_state"

        if not cls_name.endswith("s") and cls_name not in {"seed_state", "data_connection"}:
            cls_name = f"{cls_name}s"
        return cls_name

    async def get(self, model_cls: Any, entity_id: Any) -> MongoDoc | None:
        if not entity_id:
            return None
        col_name = self._resolve_collection(model_cls)
        query = {"key": str(entity_id)} if col_name == "seed_state" else {"id": str(entity_id)}
        doc = await self.db[col_name].find_one(query)
        return to_mongo_doc(doc)

    async def scalar(self, statement: Any) -> Any:
        return None

    async def execute(self, statement: Any) -> Any:
        class MongoResult:
            def scalars(self):
                return self
            def first(self):
                return None
            def all(self):
                return []
        return MongoResult()

    def add(self, instance: Any) -> None:
        if instance is None:
            return
        doc = dict(instance) if isinstance(instance, (dict, MongoDoc)) else getattr(instance, "__dict__", {})
        doc = dict(doc)
        doc.pop("_id", None)
        doc.pop("_sa_instance_state", None)
        col_name = self._resolve_collection(instance)
        self._pending_adds.append((col_name, doc))

    def add_all(self, instances: list[Any]) -> None:
        for inst in instances:
            self.add(inst)

    async def flush(self) -> None:
        if not self._pending_adds:
            return
        to_process = list(self._pending_adds)
        self._pending_adds.clear()
        for col_name, doc in to_process:
            if "id" in doc:
                await self.db[col_name].update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)
            elif "key" in doc:
                await self.db[col_name].update_one({"key": doc["key"]}, {"$set": doc}, upsert=True)

    async def commit(self) -> None:
        await self.flush()

    async def rollback(self) -> None:
        self._pending_adds.clear()

    async def refresh(self, instance: Any) -> MongoDoc | None:
        if instance is None:
            return None
        doc = dict(instance) if isinstance(instance, (dict, MongoDoc)) else getattr(instance, "__dict__", {})
        entity_id = doc.get("id") or doc.get("key")
        if not entity_id:
            return to_mongo_doc(doc)
        col_name = self._resolve_collection(instance)
        query = {"key": str(entity_id)} if col_name == "seed_state" else {"id": str(entity_id)}
        refreshed = await self.db[col_name].find_one(query)
        if refreshed and isinstance(instance, MongoDoc):
            instance.clear()
            instance.update(to_mongo_doc(refreshed))
        return to_mongo_doc(refreshed or doc)

    async def close(self) -> None:
        await self.flush()

    def in_transaction(self) -> bool:
        return False


async def create_indexes(db: FirebaseDatabase) -> None:
    """Ensure indexes exist for all collections."""
    try:
        # projects
        await db.projects.create_index("id", unique=True)
        await db.projects.create_index("name_normalized")

        # assets
        await db.assets.create_index("id", unique=True)
        await db.assets.create_index("project_id")
        await db.assets.create_index("review_status")
        await db.assets.create_index("review_priority")
        await db.assets.create_index("cluster_id")
        await db.assets.create_index("content_hash")
        await db.assets.create_index("source_connection_id")

        # annotations
        await db.annotations.create_index("id", unique=True)
        await db.annotations.create_index("asset_id")
        await db.annotations.create_index("label")

        # cloud_connections
        await db.cloud_connections.create_index("id", unique=True)
        await db.cloud_connections.create_index("name")

        # project_recons
        await db.project_recons.create_index("id", unique=True)
        await db.project_recons.create_index("project_id", unique=True)

        # decisions
        await db.decisions.create_index("id", unique=True)
        await db.decisions.create_index("project_id")
        await db.decisions.create_index("status")

        # taxonomies
        await db.taxonomies.create_index("id", unique=True)
        await db.taxonomies.create_index("project_id")

        # taxonomy_nodes
        await db.taxonomy_nodes.create_index("id", unique=True)
        await db.taxonomy_nodes.create_index("taxonomy_id")
        await db.taxonomy_nodes.create_index("parent_id")

        # annotation_attributes
        await db.annotation_attributes.create_index("id", unique=True)
        await db.annotation_attributes.create_index("annotation_id")

        # batches
        await db.batches.create_index("id", unique=True)
        await db.batches.create_index("project_id")

        # job_items
        await db.job_items.create_index("id", unique=True)
        await db.job_items.create_index("batch_id")
        await db.job_items.create_index("asset_id")
        await db.job_items.create_index("status")

        # usage_events
        await db.usage_events.create_index("id", unique=True)
        await db.usage_events.create_index("project_id")

        # agent_requests
        await db.agent_requests.create_index("id", unique=True)
        await db.agent_requests.create_index("project_id")

        # project_plans
        await db.project_plans.create_index("id", unique=True)
        await db.project_plans.create_index("project_id", unique=True)

        # masks
        await db.masks.create_index("id", unique=True)
        await db.masks.create_index("asset_id")

        # review_notes
        await db.review_notes.create_index("id", unique=True)
        await db.review_notes.create_index("asset_id")

        # model_runs
        await db.model_runs.create_index("id", unique=True)
        await db.model_runs.create_index("asset_id")

        # seed_state
        await db.seed_state.create_index("key", unique=True)

        # Repair any invalid project timestamps
        await repair_project_timestamps(db)

        # Repair any missing physical asset files from legacy storage
        await repair_asset_storage_paths(db)

        logger.info("mongodb_indexes_created")
    except Exception as exc:
        logger.warning("mongodb_indexes_creation_warning", error=str(exc))


async def repair_project_timestamps(db: FirebaseDatabase) -> int:
    """Repair project documents that have missing or null created_at / updated_at timestamps.

    Rules:
    1. created_at: if null/missing/invalid, set from:
       - existing valid ISO timestamp string in created_at / updated_at / timestamp / date
       - earliest created_at from related assets or batches
       - safely fallback to current UTC datetime (_utcnow()) if no historical timestamp exists.
    2. updated_at: if null/missing/invalid, set from:
    - repaired created_at
    3. Guarantees created_at and updated_at are stored as UTC datetime objects in BSON.
    Returns the count of repaired project documents.
    """
    repaired_count = 0
    cursor = db.projects.find({
        "$or": [
            {"created_at": None},
            {"created_at": {"$exists": False}},
            {"updated_at": None},
            {"updated_at": {"$exists": False}},
        ]
    })
    docs = await cursor.to_list(length=10000)

    for doc in docs:
        pid = doc.get("id")
        created_at = doc.get("created_at")
        updated_at = doc.get("updated_at")

        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except Exception:
                created_at = None

        if isinstance(updated_at, str):
            try:
                updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            except Exception:
                updated_at = None

        if not isinstance(created_at, datetime):
            for alt_field in ["timestamp", "date", "created"]:
                alt_val = doc.get(alt_field)
                if isinstance(alt_val, datetime):
                    created_at = alt_val
                    break
                elif isinstance(alt_val, str):
                    try:
                        created_at = datetime.fromisoformat(alt_val.replace("Z", "+00:00"))
                        break
                    except Exception:
                        pass

        if not isinstance(created_at, datetime) and pid:
            try:
                asset = await db.assets.find_one(
                    {"project_id": pid, "created_at": {"$ne": None}},
                    sort=[("created_at", 1)]
                )
                if asset and isinstance(asset.get("created_at"), datetime):
                    created_at = asset["created_at"]
                elif asset and isinstance(asset.get("created_at"), str):
                    try:
                        created_at = datetime.fromisoformat(asset["created_at"].replace("Z", "+00:00"))
                    except Exception:
                        pass
            except Exception:
                pass

        if not isinstance(created_at, datetime) and pid:
            try:
                batch = await db.batches.find_one(
                    {"project_id": pid, "created_at": {"$ne": None}},
                    sort=[("created_at", 1)]
                )
                if batch and isinstance(batch.get("created_at"), datetime):
                    created_at = batch["created_at"]
                elif batch and isinstance(batch.get("created_at"), str):
                    try:
                        created_at = datetime.fromisoformat(batch["created_at"].replace("Z", "+00:00"))
                    except Exception:
                        pass
            except Exception:
                pass

        if not isinstance(created_at, datetime) and isinstance(updated_at, datetime):
            created_at = updated_at

        if not isinstance(created_at, datetime):
            created_at = _utcnow()

        if not isinstance(updated_at, datetime):
            updated_at = created_at

        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)

        await db.projects.update_one(
            {"_id": doc["_id"]},
            {"$set": {"created_at": created_at, "updated_at": updated_at}}
        )
        repaired_count += 1

    if repaired_count > 0:
        logger.info("repaired_project_timestamps", count=repaired_count)

    return repaired_count


async def repair_asset_storage_paths(db: FirebaseDatabase, storage: Any = None) -> int:
    """Repair missing physical files for MongoDB assets by copying from legacy storage locations if available."""
    import shutil
    from pathlib import Path
    from app.config import get_settings
    from app.storage.files import FileStorage

    if storage is None:
        try:
            settings = get_settings()
            storage = FileStorage(settings.storage_dir)
        except Exception:
            return 0

    legacy_storage_dirs = [
        Path(r"C:\Users\TNADMIN\Pictures\backend\storage"),
        storage.root.parent / "backend" / "storage",
    ]

    cursor = db.assets.find({"storage_path": {"$ne": None}})
    assets = await cursor.to_list(length=10000)
    repaired_count = 0

    for asset in assets:
        sp = asset.get("storage_path")
        if not sp:
            continue
        try:
            resolved = storage.resolve(sp)
        except Exception:
            continue

        if not resolved.exists():
            filename = asset.get("filename") or asset.get("original_filename")
            if not filename:
                continue

            for leg_dir in legacy_storage_dirs:
                if not leg_dir.exists():
                    continue
                matches = list(leg_dir.rglob(filename))
                if matches:
                    src = matches[0]
                    resolved.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, resolved)
                    repaired_count += 1
                    break

    if repaired_count > 0:
        logger.info("repaired_asset_storage_files", count=repaired_count)

    return repaired_count




async def close_database() -> None:
    global _active_db, _firebase_db
    if _active_db is not None:
        await _active_db.close()
        _active_db = None
    if _firebase_db is not None:
        await _firebase_db.close()
        _firebase_db = None


async def close_sqlite() -> None:
    await close_database()


def get_database() -> FirebaseDatabase:
    global _active_db, _firebase_db
    if _active_db is not None:
        return _active_db
    if _firebase_db is not None:
        return _firebase_db
    _firebase_db = FirebaseDatabase()
    _active_db = _firebase_db
    return _active_db


async def init_database(
    settings: Any = None,
    project_id: str | None = None,
    database_id: str = "engenii-annotate-native",
    credentials_path: str | None = None,
    allow_memory_fallback: bool | None = None,
    mongodb_uri: str | None = None,
) -> FirebaseDatabase:
    global _active_db, _firebase_db
    if settings is not None and getattr(settings, "database_provider", "firebase") != "firebase":
        raise ValueError("Only the Firebase Firestore database provider is supported.")
    if allow_memory_fallback:
        raise ValueError("In-memory database fallback is not supported.")
    pid = (
        project_id
        or getattr(settings, "effective_firebase_project_id", None)
        or getattr(settings, "firebase_project_id", "")
        or getattr(settings, "google_cloud_project", "")
        or "prod-y-in2300452"
    )
    raw_db_id = (
        getattr(settings, "effective_firebase_database_id", None)
        or getattr(settings, "firebase_database_id", None)
        or database_id
    )
    db_id = "engenii-annotate-native" if raw_db_id in ("", None) else str(raw_db_id).strip()
    if not db_id or db_id == "(default)":
        raise ValueError("A named Firestore database is required.")
    cred_path = credentials_path or getattr(settings, "firebase_credentials_path", "")
    _firebase_db = await init_firebase(
        project_id=pid or None,
        database_id=db_id,
        credentials_path=cred_path or None,
        allow_memory_fallback=False,
    )
    _active_db = _firebase_db

    return _active_db


async def init_sqlite(path: Any = None) -> FirebaseDatabase:
    return get_database()


def get_session_factory() -> Any:
    return lambda: MongoSession(get_database())


async def init_db(database_path: str) -> Any:
    await init_sqlite(database_path)
    return get_session_factory()


async def close_db() -> None:
    await close_database()


async def session_scope() -> Any:
    yield MongoSession(get_database())


# Subclass compatibility for Row imports so class.__name__ maps to exact collections
class ProjectRow(MongoDoc): pass
class AssetRow(MongoDoc): pass
class AnnotationRow(MongoDoc): pass
class BatchRow(MongoDoc): pass
class JobItemRow(MongoDoc): pass
class DecisionRow(MongoDoc): pass
class SeedStateRow(MongoDoc): pass
class CloudConnectionRow(MongoDoc): pass
class DataConnectionRow(MongoDoc): pass
class ProjectReconRow(MongoDoc): pass
class TaxonomyRow(MongoDoc): pass
class TaxonomyNodeRow(MongoDoc): pass
class AnnotationAttributesRow(MongoDoc): pass
class UsageEventRow(MongoDoc): pass
class AgentRequestRow(MongoDoc): pass
class ProjectPlanRow(MongoDoc): pass
class MaskRow(MongoDoc): pass
class ReviewNoteRow(MongoDoc): pass
class ModelRunRow(MongoDoc): pass
