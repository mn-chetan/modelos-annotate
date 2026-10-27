"""Deterministic regression tests for per-asset batch reconciliation."""

from __future__ import annotations

import pytest
from types import SimpleNamespace

from app.config import Settings
from app.domain.enums import JobItemStatus
from app.services.batches import BatchService


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)

    async def to_list(self, length=None):
        return list(self.rows[:length] if length is not None else self.rows)

    def sort(self, key, direction=1):
        self.rows.sort(key=lambda row: row.get(key) or "", reverse=direction < 0)
        return self


class _Collection:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def find(self, query=None):
        query = query or {}
        return _Cursor([
            row for row in self.rows
            if all(
                row.get(key) in value["$in"] if isinstance(value, dict) and "$in" in value
                else row.get(key) == value
                for key, value in query.items()
            )
        ])

    async def find_one(self, query=None):
        rows = await self.find(query).to_list(1)
        return rows[0] if rows else None

    async def find_one_and_update(self, query, update, **kwargs):
        row = await self.find_one(query)
        if row is None:
            return None
        self._apply(row, update)
        return row

    async def update_one(self, query, update, **_kwargs):
        row = await self.find_one(query)
        if row is not None:
            self._apply(row, update)
        return None

    @staticmethod
    def _apply(row, update):
        for key, value in update.get("$set", {}).items():
            row[key] = value
        for key, value in update.get("$inc", {}).items():
            row[key] = row.get(key, 0) + value

    async def insert_many(self, rows):
        self.rows.extend(dict(row) for row in rows)

    async def update_many(self, *_args, **_kwargs):
        query, update = _args
        rows = await self.find(query).to_list(None)
        for row in rows:
            self._apply(row, update)
        return None

    async def count_documents(self, query=None):
        return len(await self.find(query).to_list(None))


class _Database:
    def __init__(self, job_items, batches=None):
        self.job_items = _Collection(job_items)
        self.assets = _Collection()
        self.batches = _Collection(batches)
        self.annotations = _Collection()


@pytest.mark.asyncio
async def test_active_batch_reuse_rejects_cross_modality():
    image_batch = {
        "id": "image-batch",
        "project_id": "project-1",
        "status": JobItemStatus.QUEUED.value,
        "execution_modality": "image",
        "execution_task": "OBJECT_DETECTION",
    }
    db = _Database([], batches=[image_batch])
    service = BatchService(db, Settings(DEBUG=False, SKIP_MODEL_LOAD=True))

    assert await service.find_active_compatible("project-1", "text", "NER") is None


@pytest.mark.asyncio
async def test_claim_rejects_item_execution_context_mismatch():
    batch = {
        "id": "image-batch",
        "project_id": "project-1",
        "asset_ids": ["asset-1"],
        "status": JobItemStatus.QUEUED.value,
        "explicit_ai_annotation_trigger": True,
        "execution_modality": "image",
        "execution_task": "OBJECT_DETECTION",
    }
    item = {
        "id": "job-1",
        "batch_id": "image-batch",
        "asset_id": "asset-1",
        "execution_modality": "text",
        "execution_task": "NER",
        "status": JobItemStatus.QUEUED.value,
    }
    db = _Database([item], batches=[batch])
    db.assets.rows.append({
        "id": "asset-1",
        "project_id": "project-1",
        "modality": "image",
        "content_type": "image/jpeg",
    })
    service = BatchService(db, Settings(DEBUG=False, SKIP_MODEL_LOAD=True))

    assert await service.claim_next_item() is None
    assert item["status"] == JobItemStatus.FAILED.value
    assert item["error_message"].startswith("EXECUTION_CONTEXT_MISMATCH")


@pytest.mark.asyncio
async def test_three_asset_batch_reconciliation_repairs_missing_job_item():
    db = _Database([
        {"id": "job-1", "batch_id": "batch-1", "asset_id": "asset-1", "status": JobItemStatus.SUCCEEDED.value},
        {"id": "job-2", "batch_id": "batch-1", "asset_id": "asset-2", "status": JobItemStatus.SUCCEEDED.value},
    ])
    service = BatchService(
        db,
        Settings(DEBUG=False, SKIP_MODEL_LOAD=True, recover_interrupted_batches=True),
    )
    batch = {
        "id": "batch-1",
        "asset_ids": ["asset-1", "asset-2", "asset-3"],
        "total": 3,
        "status": "running",
        "explicit_ai_annotation_trigger": True,
        "recovered_from_restart": True,
    }
    db.batches.rows.append(batch)

    items, missing, unexpected, non_terminal = await service._reconcile_batch_items(
        "batch-1", batch=batch
    )

    assert missing == ["asset-3"]
    assert unexpected == []
    assert {item["asset_id"] for item in items} == {"asset-1", "asset-2", "asset-3"}
    assert len(non_terminal) == 1
    assert non_terminal[0]["asset_id"] == "asset-3"


@pytest.mark.asyncio
async def test_reconciliation_blocks_missing_items_without_authorized_recovery():
    batch = {
        "id": "batch-unauthorized",
        "asset_ids": ["asset-1", "asset-2"],
        "total": 2,
        "status": "queued",
        "explicit_ai_annotation_trigger": False,
    }
    db = _Database([], batches=[batch])
    service = BatchService(db, Settings(DEBUG=False, SKIP_MODEL_LOAD=True))

    items, missing, unexpected, non_terminal = await service._reconcile_batch_items(
        "batch-unauthorized", batch=batch
    )

    assert items == []
    assert missing == ["asset-1", "asset-2"]
    assert unexpected == []
    assert non_terminal == []
    assert db.job_items.rows == []
    assert batch["status"] == "failed"
    assert batch["error_summary"].startswith("BATCH_RECONCILIATION_ERROR")


@pytest.mark.asyncio
async def test_reconciliation_repairs_only_opted_in_recovered_batch_without_starting_it():
    batch = {
        "id": "batch-recovery",
        "asset_ids": ["asset-1", "asset-2"],
        "total": 2,
        "status": "queued",
        "explicit_ai_annotation_trigger": True,
        "recovered_from_restart": True,
    }
    db = _Database([
        {"id": "job-1", "batch_id": "batch-recovery", "asset_id": "asset-1", "status": JobItemStatus.QUEUED.value}
    ], batches=[batch])
    service = BatchService(
        db,
        Settings(DEBUG=False, SKIP_MODEL_LOAD=True, recover_interrupted_batches=True),
    )

    items, missing, unexpected, non_terminal = await service._reconcile_batch_items(
        "batch-recovery", batch=batch
    )

    assert missing == ["asset-2"]
    assert unexpected == []
    assert len(items) == 2
    assert len(non_terminal) == 2
    assert batch["status"] == "queued"


@pytest.mark.asyncio
async def test_claim_next_item_requires_explicit_batch_trigger():
    batch = {
        "id": "batch-unauthorized",
        "project_id": "project-1",
        "asset_ids": ["asset-1"],
        "status": "queued",
        "explicit_ai_annotation_trigger": False,
    }
    item = {
        "id": "job-1",
        "batch_id": "batch-unauthorized",
        "asset_id": "asset-1",
        "status": JobItemStatus.QUEUED.value,
    }
    db = _Database([item], batches=[batch])
    service = BatchService(db, Settings(DEBUG=False, SKIP_MODEL_LOAD=True))

    claimed = await service.claim_next_item()

    assert claimed is None
    assert item["status"] == JobItemStatus.FAILED.value
    assert "explicit AI annotation trigger" in item["error_message"]
    assert batch["status"] == "queued"


@pytest.mark.asyncio
async def test_claim_next_item_rejects_asset_outside_batch_identity():
    batch = {
        "id": "batch-1",
        "project_id": "project-1",
        "asset_ids": ["asset-1"],
        "status": "queued",
        "explicit_ai_annotation_trigger": True,
    }
    item = {
        "id": "job-1",
        "batch_id": "batch-1",
        "asset_id": "asset-unrelated",
        "status": JobItemStatus.QUEUED.value,
    }
    db = _Database([item], batches=[batch])
    service = BatchService(db, Settings(DEBUG=False, SKIP_MODEL_LOAD=True))

    claimed = await service.claim_next_item()

    assert claimed is None
    assert item["status"] == JobItemStatus.FAILED.value
    assert item["error_message"].startswith("JOB_ITEM_IDENTITY_MISMATCH")
    assert batch["status"] == "queued"


@pytest.mark.asyncio
async def test_claim_next_item_atomically_transitions_authorized_batch():
    batch = {
        "id": "batch-1",
        "project_id": "project-1",
        "asset_ids": ["asset-1"],
        "status": "queued",
        "explicit_ai_annotation_trigger": True,
        "running": 0,
    }
    item = {
        "id": "job-1",
        "batch_id": "batch-1",
        "asset_id": "asset-1",
        "status": JobItemStatus.QUEUED.value,
    }
    db = _Database([item], batches=[batch])
    db.assets.rows.append({
        "id": "asset-1",
        "project_id": "project-1",
        "modality": "image",
        "content_type": "image/jpeg",
    })
    service = BatchService(db, Settings(DEBUG=False, SKIP_MODEL_LOAD=True))

    claimed = await service.claim_next_item()

    assert claimed is not None
    assert claimed["status"] == JobItemStatus.RUNNING.value
    assert claimed["attempt"] == 1
    assert batch["status"] == "running"
    assert batch["running"] == 1


@pytest.mark.asyncio
async def test_startup_does_not_requeue_running_job_without_recovery_opt_in():
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    batch = {
        "id": "batch-1",
        "project_id": "project-1",
        "asset_ids": ["asset-1"],
        "total": 1,
        "status": "running",
        "explicit_ai_annotation_trigger": True,
        "created_at": now,
        "updated_at": now,
    }
    item = {
        "id": "job-1",
        "batch_id": "batch-1",
        "asset_id": "asset-1",
        "status": JobItemStatus.RUNNING.value,
        "created_at": now,
        "updated_at": now,
    }
    db = _Database([item], batches=[batch])
    service = BatchService(db, Settings(DEBUG=False, SKIP_MODEL_LOAD=True))

    await service.reconcile_interrupted()

    assert item["status"] == JobItemStatus.FAILED.value
    assert "not resumed" in item["error_message"]
    assert batch["status"] == "failed"


@pytest.mark.asyncio
async def test_startup_never_requeues_running_job_even_with_recovery_opt_in():
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    batch = {
        "id": "batch-1",
        "project_id": "project-1",
        "asset_ids": ["asset-1"],
        "total": 1,
        "status": "running",
        "explicit_ai_annotation_trigger": True,
        "created_at": now,
        "updated_at": now,
    }
    item = {
        "id": "job-1",
        "batch_id": "batch-1",
        "asset_id": "asset-1",
        "status": JobItemStatus.RUNNING.value,
        "created_at": now,
        "updated_at": now,
    }
    db = _Database([item], batches=[batch])
    service = BatchService(
        db,
        Settings(DEBUG=False, SKIP_MODEL_LOAD=True, recover_interrupted_batches=True),
    )

    await service.reconcile_interrupted()

    assert item["status"] == JobItemStatus.FAILED.value
    assert batch["status"] == "failed"
    assert "not resumed" in item["error_message"]


def test_human_review_is_a_terminal_batch_item():
    items = [
        {"status": JobItemStatus.SUCCEEDED.value},
        {"status": JobItemStatus.HUMAN_REVIEW.value},
    ]

    counts = BatchService._item_counts(items)

    assert counts["completed"] == 1
    assert counts["review"] == 1
    assert counts["running"] == 0


@pytest.mark.asyncio
async def test_terminal_asset_ids_excludes_assets_from_other_projects():
    job_items = [
        {"id": "job-a", "batch_id": "batch-a", "asset_id": "asset-a", "status": JobItemStatus.SUCCEEDED.value},
        {"id": "job-b", "batch_id": "batch-b", "asset_id": "asset-b", "status": JobItemStatus.HUMAN_REVIEW.value},
        {"id": "job-c", "batch_id": "batch-c", "asset_id": "asset-c", "status": JobItemStatus.SUCCEEDED.value},
    ]
    batches = [
        {"id": "batch-a", "project_id": "project-1"},
        {"id": "batch-b", "project_id": "project-1"},
        {"id": "batch-c", "project_id": "project-2"},
    ]

    db = SimpleNamespace(
        job_items=SimpleNamespace(find=lambda _query: _Cursor(job_items)),
        batches=SimpleNamespace(find=lambda _query: _Cursor([batch for batch in batches if batch["project_id"] == "project-1"])),
    )
    service = BatchService(db, Settings(DEBUG=False, SKIP_MODEL_LOAD=True))

    assert await service.terminal_asset_ids("project-1", ["asset-a", "asset-b", "asset-c"]) == {"asset-a", "asset-b"}


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [JobItemStatus.FAILED.value, JobItemStatus.CANCELLED.value, "failed_final"])
async def test_failed_or_cancelled_terminal_attempt_remains_eligible(status):
    db = _Database(
        [{"id": "job-a", "batch_id": "batch-a", "asset_id": "asset-a", "status": status, "finished_at": "2026-01-02T00:00:00+00:00"}],
        [{"id": "batch-a", "project_id": "project-1"}],
    )
    service = BatchService(db, Settings(DEBUG=False, SKIP_MODEL_LOAD=True))

    assert await service.terminal_asset_ids("project-1", ["asset-a"]) == set()


@pytest.mark.asyncio
async def test_successful_zero_detection_result_is_idempotently_processed():
    db = _Database(
        [{"id": "job-a", "batch_id": "batch-a", "asset_id": "asset-a", "status": JobItemStatus.SUCCEEDED.value, "detection_count": 0}],
        [{"id": "batch-a", "project_id": "project-1"}],
    )
    service = BatchService(db, Settings(DEBUG=False, SKIP_MODEL_LOAD=True))

    assert await service.terminal_asset_ids("project-1", ["asset-a"]) == {"asset-a"}


@pytest.mark.asyncio
async def test_explicit_trigger_reprocesses_human_review_and_zero_annotation_assets():
    db = _Database(
        [
            {"id": "job-review", "batch_id": "batch-review", "asset_id": "asset-review", "status": JobItemStatus.HUMAN_REVIEW.value},
            {"id": "job-zero", "batch_id": "batch-zero", "asset_id": "asset-zero", "status": JobItemStatus.SUCCEEDED.value},
            {"id": "job-done", "batch_id": "batch-done", "asset_id": "asset-done", "status": JobItemStatus.SUCCEEDED.value},
        ],
        [
            {"id": "batch-review", "project_id": "project-1"},
            {"id": "batch-zero", "project_id": "project-1"},
            {"id": "batch-done", "project_id": "project-1"},
        ],
    )
    db.annotations.rows.append({"id": "annotation-1", "asset_id": "asset-done"})
    service = BatchService(db, Settings(DEBUG=False, SKIP_MODEL_LOAD=True))

    assert await service.terminal_asset_ids(
        "project-1",
        ["asset-review", "asset-zero", "asset-done"],
        explicit_ai_annotation_trigger=True,
    ) == {"asset-done"}


@pytest.mark.asyncio
async def test_latest_failed_attempt_overrides_older_success_and_is_asset_scoped():
    db = _Database(
        [
            {"id": "job-old", "batch_id": "batch-old", "asset_id": "asset-a", "status": JobItemStatus.SUCCEEDED.value, "finished_at": "2026-01-01T00:00:00+00:00"},
            {"id": "job-new", "batch_id": "batch-new", "asset_id": "asset-a", "status": JobItemStatus.FAILED.value, "finished_at": "2026-01-02T00:00:00+00:00"},
            {"id": "job-other", "batch_id": "batch-old", "asset_id": "asset-b", "status": JobItemStatus.SUCCEEDED.value, "finished_at": "2026-01-01T00:00:00+00:00"},
        ],
        [
            {"id": "batch-old", "project_id": "project-1"},
            {"id": "batch-new", "project_id": "project-1"},
        ],
    )
    service = BatchService(db, Settings(DEBUG=False, SKIP_MODEL_LOAD=True))

    assert await service.terminal_asset_ids("project-1", ["asset-a", "asset-b"]) == {"asset-b"}
