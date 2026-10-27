"""Migration utility: Migrate all collections and documents from SQLite to Firebase Firestore."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

from app.db.firebase import FirebaseDatabase
from app.logging import get_logger

logger = get_logger(__name__)


async def migrate_sqlite_to_firebase(
    sqlite_path: str | Path,
    firebase_db: FirebaseDatabase,
) -> dict[str, int]:
    """Extract all documents from SQLite and copy them into Firebase Firestore."""
    from app.db.firebase import verify_database_safety_guard
    verify_database_safety_guard(
        database_id=getattr(firebase_db, "database_id", ""),
        project_id=getattr(firebase_db, "project_id", ""),
    )

    path = Path(sqlite_path)
    if not path.exists():
        logger.info("migration_sqlite_file_not_found", path=str(path))
        return {}

    conn = sqlite3.connect(str(path))
    cursor = conn.cursor()

    # Check if documents table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents'")
    if not cursor.fetchone():
        logger.info("migration_documents_table_not_found")
        conn.close()
        return {}

    # Get distinct collections
    cursor.execute("SELECT DISTINCT collection FROM documents")
    collections = [row[0] for row in cursor.fetchall()]
    migration_summary: dict[str, int] = {}

    logger.info("migration_started", total_collections=len(collections), collections=collections)

    for col_name in collections:
        cursor.execute("SELECT doc_id, payload FROM documents WHERE collection = ?", (col_name,))
        rows = cursor.fetchall()
        migrated_count = 0
        firebase_col = firebase_db[col_name]

        for doc_id, payload in rows:
            try:
                data = json.loads(payload)
                data.setdefault("id", doc_id)
                await firebase_col.insert_one(data)
                migrated_count += 1
            except Exception as exc:
                logger.error(
                    "migration_document_failed",
                    collection=col_name,
                    doc_id=doc_id,
                    error=str(exc),
                )

        migration_summary[col_name] = migrated_count
        logger.info("migration_collection_complete", collection=col_name, count=migrated_count)

    conn.close()
    logger.info("migration_completed", summary=migration_summary)
    return migration_summary


if __name__ == "__main__":
    from app.config import get_settings
    from app.db.firebase import init_firebase

    async def main():
        settings = get_settings()
        fb_db = await init_firebase(
            project_id=settings.google_cloud_project or settings.firebase_project_id or "prod-y-in2300452",
            database_id=settings.firebase_database_id,
        )
        res = await migrate_sqlite_to_firebase(settings.sqlite_database_path, fb_db)
        print("Migration Summary:", res)

    asyncio.run(main())
