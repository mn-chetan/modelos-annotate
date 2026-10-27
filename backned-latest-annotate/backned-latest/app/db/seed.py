"""Database seed logic.

PRODUCTION SAFETY:
    Demo/test project creation is gated behind the ``SEED_DEMO_DATA`` environment
    variable (or Settings.seed_demo_data).  The default value is ``False``, so
    production deployments NEVER create automatic mock/demo projects.

    To enable seeding in a local dev environment set::

        SEED_DEMO_DATA=true

    The function ``seed_database_if_empty`` is called on every startup.  When
    seeding is disabled it:

      * performs NO writes to the database,
      * logs ``production_mock_data_disabled=true``,
      * returns immediately so the projects collection stays empty.

    A real project is created ONLY when an authorised user explicitly calls the
    project-creation API.
"""

import asyncio
import hashlib
from datetime import datetime, UTC
from pathlib import Path

from app.domain.enums import ProjectStatus, AssetStatus, ReviewStatus
from app.services.images import write_jpeg_preview
from app.logging import get_logger

logger = get_logger(__name__)

# Seed-state idempotency key - only used when seeding is explicitly enabled.
DEMO_SEED_KEY = "demo-project-v1"


# ---------------------------------------------------------------------------
# Image source helper (only called when SEED_DEMO_DATA=true)
# ---------------------------------------------------------------------------

def load_seed_image_data() -> bytes:
    paths = [
        Path("c:/Users/TNADMIN/Downloads/ingenii-annotate-v2-codebase-v5-2026-08-22/ingenii-annotate-v2/public/fruit-inspection.png"),
        Path("c:/Users/TNADMIN/Downloads/ingenii-annotate-v2-codebase-v5-2026-08-22/ingenii-annotate-v2/public/og.png"),
    ]
    for p in paths:
        if p.exists() and p.stat().st_size > 0:
            return p.read_bytes()

    for candidate_dir in [
        Path("/app/frontend_dist/assets"),
        Path("Annotate-ui/Annotate-ui/dist/assets"),
        Path("Annotate-ui/Annotate-ui/src/assets/images"),
    ]:
        if candidate_dir.exists():
            for ext in ("*.jpg", "*.png", "*.jpeg"):
                for f in sorted(candidate_dir.glob(ext)):
                    if f.is_file() and f.stat().st_size > 0:
                        try:
                            return f.read_bytes()
                        except Exception:
                            pass

    zip_candidates = [
        (Path("C:/Users/TNADMIN/Downloads/ingenii-annotate-v2-codebase-v5-2026-08-22.zip"), "ingenii-annotate-v2/public/fruit-inspection.png"),
        (Path("C:/Users/TNADMIN/Downloads/ingenii-annotate-v2-codebase-v5-2026-08-22.zip"), "ingenii-annotate-v2/public/og.png"),
    ]
    for zp, inner in zip_candidates:
        if zp.exists():
            try:
                import zipfile
                with zipfile.ZipFile(zp) as z:
                    data = z.read(inner)
                    if data:
                        try:
                            disk_target = Path("c:/Users/TNADMIN/Downloads/ingenii-annotate-v2-codebase-v5-2026-08-22/ingenii-annotate-v2/public") / Path(inner).name
                            disk_target.parent.mkdir(parents=True, exist_ok=True)
                            disk_target.write_bytes(data)
                        except Exception:
                            pass
                        return data
            except Exception:
                pass
    return b""


# ---------------------------------------------------------------------------
# Asset file reconciliation (only called when SEED_DEMO_DATA=true)
# ---------------------------------------------------------------------------

async def ensure_orchard_assets_persisted(db, image_data: bytes) -> None:
    """Ensures existing orchard quality assets have physical files on disk."""
    if not image_data:
        return
    content_hash = hashlib.sha256(image_data).hexdigest()
    storage_root = Path("./storage")
    cursor = db.assets.find({"project_id": "prj_orchard_quality", "status": {"$ne": "deleted"}})
    assets = await cursor.to_list(100)
    for a in assets:
        asset_id = a.get("id")
        filename = a.get("filename") or f"{asset_id}.jpg"
        storage_path = a.get("storage_path") or f"prj_orchard_quality/{asset_id}/{filename}"
        target_file = storage_root / storage_path
        target_file.parent.mkdir(parents=True, exist_ok=True)
        if not target_file.exists() or target_file.stat().st_size == 0:
            target_file.write_bytes(image_data)
            preview_file = target_file.parent / "preview.jpg"
            preview_rel = None
            try:
                write_jpeg_preview(image_data, preview_file)
                if preview_file.exists() and preview_file.stat().st_size > 0:
                    preview_rel = f"prj_orchard_quality/{asset_id}/preview.jpg"
            except Exception:
                pass
            await db.assets.update_one(
                {"id": asset_id},
                {"$set": {
                    "storage_path": storage_path,
                    "preview_path": preview_rel,
                    "byte_size": len(image_data),
                    "content_hash": content_hash,
                }}
            )


# ---------------------------------------------------------------------------
# Public entry-point called from app startup
# ---------------------------------------------------------------------------

async def seed_database_if_empty(db, settings=None) -> None:
    """Called once during application startup.

    Production (default, SEED_DEMO_DATA=false / unset):
        - Does NOT create any projects, assets, or decisions.
        - Logs ``production_mock_data_disabled=true``.
        - Returns immediately; projects collection stays empty.

    Dev/test (SEED_DEMO_DATA=true):
        - Creates the demo "Orchard quality" project if the projects
          collection is empty.
        - Idempotent: skips if seed_state already records completion.
    """
    # ------------------------------------------------------------------
    # 1. Resolve whether seeding is enabled
    # ------------------------------------------------------------------
    if settings is None:
        try:
            from app.config import get_settings
            settings = get_settings()
        except Exception:
            settings = None

    from app.db.firebase import verify_database_safety_guard
    verify_database_safety_guard(
        is_production=getattr(settings, "is_production", False),
        database_id=getattr(db, "database_id", ""),
        project_id=getattr(db, "project_id", ""),
    )

    seed_enabled: bool = getattr(settings, "seed_demo_data", False)

    if not seed_enabled:
        # Production path - do nothing, emit diagnostic logs.
        logger.info(
            "production_mock_data_disabled",
            seed_demo_data=False,
            message="Demo/test project seeding is disabled. Projects collection starts empty.",
        )
        logger.info(
            "seed_completed",
            created_projects=0,
            created_assets=0,
            seed_demo_data=False,
        )
        return

    # ------------------------------------------------------------------
    # 2. Dev/test path - seeding explicitly enabled via SEED_DEMO_DATA=true
    # ------------------------------------------------------------------
    if not getattr(db, "is_healthy", False) and not getattr(db, "allow_memory_fallback", False):
        logger.error(
            "startup_database_unhealthy",
            provider=getattr(db, "provider", "firebase"),
            project=getattr(db, "project_id", ""),
            database=getattr(db, "database_id", ""),
            error=getattr(db, "last_error", "unhealthy"),
        )
        raise RuntimeError("Database seed aborted: configured database is unhealthy.")

    image_data = load_seed_image_data()

    # Reconcile any existing assets that lack physical files on disk
    await ensure_orchard_assets_persisted(db, image_data)

    has_projects = await db.projects.find_one({}, {"_id": 1})
    if has_projects is not None:
        logger.info(
            "seed_skipped_projects_exist",
            seed_demo_data=True,
            message="Projects collection is non-empty; skipping demo seed.",
        )
        return

    # Clear any stale seed_state so seeding proceeds cleanly
    await db.seed_state.delete_many({"key": DEMO_SEED_KEY})

    project_id = "prj_orchard_quality"
    now = datetime.now(UTC)

    logger.info("seed_demo_data_starting", project_id=project_id, seed_demo_data=True)
    print("Seeding Firebase database (SEED_DEMO_DATA=true)...")

    # 1. Create Project
    project_doc = {
        "id": project_id,
        "name": "Orchard quality â€” Harvest 14",
        "name_normalized": "orchard quality â€” harvest 14",
        "goal": "Separate market-ready fruit from visible rot, mold, and major bruising using instance masks.",
        "task_type": "segmentation",
        "classification_mode": "single",
        "labels": ["Good fruit", "Rotten fruit", "Uncertain"],
        "label_ontology": [
            {
                "id": "cpt_good_fruit",
                "name": "Good fruit",
                "description": "Market-ready fruit with no visible decay or major damage.",
                "geometry": ["instance_mask", "polygon"],
                "examples": ["Natural color variation", "Minor superficial speckling"],
                "exclusions": ["Visible mold", "Open lesions", "Major bruising"],
                "status": "approved",
            },
            {
                "id": "cpt_rotten_fruit",
                "name": "Rotten fruit",
                "description": "Fruit with visible rot, mold, open lesions, or major bruising.",
                "geometry": ["instance_mask", "polygon"],
                "examples": ["Soft dark decay", "Fuzzy mold", "Open lesion"],
                "exclusions": ["Stem shadow", "Minor surface blemish"],
                "status": "approved",
            },
            {
                "id": "cpt_uncertain",
                "name": "Uncertain",
                "description": "Borderline visual state requiring reviewer judgment.",
                "geometry": ["instance_mask", "polygon"],
                "examples": ["Ambiguous discoloration"],
                "exclusions": ["Clearly healthy", "Clearly rotten"],
                "status": "warning",
            }
        ],
        "ontology_revision": 0,
        "ontology_changes": [],
        "ontology_recommendations": [],
        "label_strategy": "detailed",
        "status": "active",
        "color_map": {
            "Good fruit": {"color": "#2CB67D", "manual": False},
            "Rotten fruit": {"color": "#EF5B67", "manual": False},
            "Uncertain": {"color": "#F2B84B", "manual": False}
        },
        "quality_policy": {
            "auto_approve_threshold": 0.92,
            "sample_rate": 0.05,
            "notes": "Default quality policy"
        },
        "created_at": now,
        "updated_at": now
    }
    await db.projects.insert_one(project_doc)

    # 2. Create asset image files
    if not image_data:
        print("Seed image source not found. Skipping demo asset seeding.")
        await db.seed_state.insert_one({"key": DEMO_SEED_KEY, "completed_at": now})
        logger.info(
            "seed_completed",
            project_id=project_id,
            created_projects=1,
            created_assets=0,
            seed_demo_data=True,
            database=getattr(db, "database_id", "engenii-annotate-native"),
        )
        return

    content_hash = hashlib.sha256(image_data).hexdigest()

    assets = []
    for i in range(18):
        asset_idx = i + 1
        asset_id = f"ast_h14_{asset_idx:04d}"
        filename = f"harvest14_lane-b_{240 + asset_idx:04d}.jpg"

        storage_dir = Path("./storage") / project_id / asset_id
        storage_dir.mkdir(parents=True, exist_ok=True)
        storage_file = storage_dir / filename

        storage_file.write_bytes(image_data)
        if not storage_file.exists() or storage_file.stat().st_size == 0:
            raise RuntimeError(f"Physical file persistence failed for {storage_file}")

        preview_file = storage_dir / "preview.jpg"
        preview_path = None
        try:
            write_jpeg_preview(image_data, preview_file)
            if preview_file.exists() and preview_file.stat().st_size > 0:
                preview_path = f"{project_id}/{asset_id}/preview.jpg"
        except Exception as exc:
            print(f"Failed to generate preview for asset {asset_id}: {exc}")
            preview_path = None

        review_state = ReviewStatus.PENDING.value
        if i < 3:
            review_state = ReviewStatus.REVIEW.value
        elif i < 8:
            review_state = ReviewStatus.PENDING.value
        else:
            review_state = ReviewStatus.APPROVED.value

        asset_doc = {
            "id": asset_id,
            "project_id": project_id,
            "filename": filename,
            "content_type": "image/png",
            "width": 2048,
            "height": 1365,
            "storage_path": f"{project_id}/{asset_id}/{filename}",
            "preview_path": preview_path,
            "byte_size": len(image_data),
            "status": AssetStatus.UPLOADED.value,
            "review_status": review_state,
            "review_reason": "",
            "mean_confidence": None,
            "content_hash": content_hash,
            "perceptual_hash": None,
            "aspect_ratio": 2048 / 1365,
            "orientation": 1,
            "image_format": "PNG",
            "cluster_id": 1 if i < 9 else 2,
            "is_outlier": 0,
            "is_duplicate": 0,
            "review_priority": 1.5 if i < 3 else 0.0,
            "created_at": now,
            "updated_at": now
        }
        assets.append(asset_doc)

    if assets:
        await db.assets.insert_many(assets)

    # 3. Create a Decision candidate
    decision_doc = {
        "id": "dec_rot_bruise_01",
        "project_id": project_id,
        "status": "open",
        "decision_type": "boundary",
        "question": "Surface bruising repeatedly labeled as rot",
        "options": ["Good fruit", "Rotten fruit", "Uncertain"],
        "proposed_default": "Uncertain",
        "rationale": "12 reviewer corrections across one visually coherent slice",
        "affects_count": 42,
        "example_asset_ids": ["ast_h14_0001", "ast_h14_0002", "ast_h14_0003", "ast_h14_0004", "ast_h14_0005", "ast_h14_0006", "ast_h14_0007", "ast_h14_0008"],
        "affected_asset_ids": ["ast_h14_0001"],
        "created_at": now,
        "updated_at": now
    }
    await db.decisions.insert_one(decision_doc)

    await db.seed_state.insert_one({"key": DEMO_SEED_KEY, "completed_at": now})
    logger.info(
        "seed_completed",
        project_id=project_id,
        created_projects=1,
        created_assets=len(assets),
        seed_demo_data=True,
        database=getattr(db, "database_id", "engenii-annotate-native"),
    )
    print("Database seed completed (SEED_DEMO_DATA=true).")


if __name__ == "__main__":
    from app.db.models import init_database
    from app.config import get_settings
    async def _main():
        s = get_settings()
        db = await init_database(settings=s)
        await db.seed_state.delete_one({"key": DEMO_SEED_KEY})
        await seed_database_if_empty(db, settings=s)
    asyncio.run(_main())
