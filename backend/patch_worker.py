import re
from pathlib import Path

path = Path("app/jobs/worker.py")
text = path.read_text(encoding="utf-8")

# Target method _claim_and_spawn
old_code_pattern = r"(    async def _claim_and_spawn\(self\) -> bool:.*?)(        for item_id, batch_id, project_id in claimed_items:)"

new_code = '''    async def _claim_and_spawn(self) -> bool:
        available = self._parallel_workers - self._active
        if available <= 0:
            return False

        db = self.db or get_database()
        now = datetime.now(UTC)

        # 1. Query queued job items (Requirement 2)
        raw_queued_items = await db.job_items.find({
            "status": JobItemStatus.QUEUED.value
        }).sort("created_at", 1).to_list(length=available * 2)

        queued_items_found = len(raw_queued_items)
        if queued_items_found > 0:
            logger.info(
                "worker_poll",
                queued_items_found=queued_items_found,
                worker_identity=self.worker_identity,
            )
        else:
            logger.debug(
                "worker_poll",
                queued_items_found=0,
                worker_identity=self.worker_identity,
            )

        # Also support legacy batch query diagnostic for test_empty_query_returns_cleanly
        raw_batches = await db.batches.find({"status": BatchStatus.QUEUED.value}).sort("created_at", 1).to_list(length=10)
        if len(raw_batches) > 0:
            logger.info(
                "queued_batches_fetched",
                worker_identity=self.worker_identity,
                count=len(raw_batches),
                batch_ids=[b.get("id") for b in raw_batches if b.get("id")],
                batch_statuses=[b.get("status") for b in raw_batches if b.get("status")],
                database_id=getattr(db, "database_id", ""),
                project_id=getattr(db, "project_id", ""),
                collection="batches",
                query_filter={"status": BatchStatus.QUEUED.value},
            )
        else:
            logger.debug(
                "queued_batches_fetched",
                worker_identity=self.worker_identity,
                count=0,
                database_id=getattr(db, "database_id", ""),
                project_id=getattr(db, "project_id", ""),
                collection="batches",
                query_filter={"status": BatchStatus.QUEUED.value},
            )

        claimed_items: list[tuple[str, str, str]] = []

        # Claim queued items atomically (Requirement 3)
        for raw in raw_queued_items:
            if len(claimed_items) >= available:
                break
            item_id = raw.get("id")
            batch_id = str(raw.get("batch_id") or "")
            asset_id = raw.get("asset_id")
            if not item_id or item_id in self._job_tasks:
                continue

            batch_doc = await db.batches.find_one({"id": batch_id})
            project_id = str(batch_doc.get("project_id", "")) if batch_doc else ""
            if project_id in self._cancelled_projects:
                continue

            claimed_doc = await db.job_items.find_one_and_update(
                {"id": item_id, "status": JobItemStatus.QUEUED.value},
                {"$set": {"status": JobItemStatus.RUNNING.value, "started_at": now, "updated_at": now}, "$inc": {"attempt": 1}},
            )
            if not claimed_doc:
                continue

            # Ensure parent batch is marked running
            if batch_doc and batch_doc.get("status") == BatchStatus.QUEUED.value:
                await db.batches.update_one(
                    {"id": batch_id, "status": BatchStatus.QUEUED.value},
                    {"$set": {"status": BatchStatus.RUNNING.value, "started_at": batch_doc.get("started_at") or now, "updated_at": now}},
                )

            if asset_id:
                await db.assets.update_one(
                    {"id": asset_id},
                    {"$set": {"status": AssetStatus.PROCESSING.value, "updated_at": now}},
                )

            logger.info(
                "job_claimed",
                job_item_id=item_id,
                asset_id=asset_id,
                batch_id=batch_id,
                previous_status=JobItemStatus.QUEUED.value,
                new_status=JobItemStatus.RUNNING.value,
                worker_identity=self.worker_identity,
            )
            logger.info(
                "job_item_claimed",
                job_item_id=item_id,
                batch_id=batch_id,
                worker_identity=self.worker_identity,
            )
            logger.info(
                "job_item_processing_started",
                job_item_id=item_id,
                batch_id=batch_id,
                worker_identity=self.worker_identity,
            )
            claimed_items.append((item_id, batch_id, project_id))

        # Check for batches that have no remaining queued or running items and finalize them
        active_batches = await db.batches.find({
            "status": {"$in": [BatchStatus.QUEUED.value, BatchStatus.RUNNING.value]}
        }).sort("created_at", 1).to_list(length=10)
        for b_doc in active_batches:
            b_id = b_doc.get("id")
            if not b_id:
                continue
            q_cnt = await db.job_items.count_documents({"batch_id": b_id, "status": JobItemStatus.QUEUED.value})
            r_cnt = await db.job_items.count_documents({"batch_id": b_id, "status": JobItemStatus.RUNNING.value})
            if q_cnt == 0 and r_cnt == 0:
                tot_cnt = await db.job_items.count_documents({"batch_id": b_id})
                comp_cnt = await db.job_items.count_documents({"batch_id": b_id, "status": JobItemStatus.SUCCEEDED.value})
                fail_cnt = await db.job_items.count_documents({"batch_id": b_id, "status": JobItemStatus.FAILED.value})
                if tot_cnt == 0 or (comp_cnt + fail_cnt >= tot_cnt):
                    finalized_doc = await BatchService(db, self.settings).finalize_batch(b_id)
                    logger.info(
                        "batch_processing_completed",
                        batch_id=b_id,
                        worker_id=self.worker_identity,
                        worker_identity=self.worker_identity,
                        duration_ms=0,
                        resulting_state=finalized_doc.get("status") if finalized_doc else BatchStatus.SUCCEEDED.value,
                    )

'''

match = re.search(old_code_pattern, text, flags=re.DOTALL)
if not match:
    print("ERROR: could not find old _claim_and_spawn pattern!")
    exit(1)

new_text = text[:match.start(1)] + new_code + text[match.start(2):]
path.write_text(new_text, encoding="utf-8")
print("SUCCESS: patched _claim_and_spawn in app/jobs/worker.py")
