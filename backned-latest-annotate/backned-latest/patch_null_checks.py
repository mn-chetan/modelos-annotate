from pathlib import Path

path = Path("app/jobs/worker.py")
text = path.read_text(encoding="utf-8")

old_code = """            if item is None or batch is None:
                return"""

new_code = """            if item is None:
                logger.error("job_item_not_found", job_id=item_id, batch_id=batch_id)
                return
            if batch is None:
                logger.error("batch_not_found_for_job_item", job_id=item_id, batch_id=batch_id)
                db = self.db or get_database()
                await BatchService(db, self.settings).complete_item(
                    item_id=item_id,
                    status=JobItemStatus.FAILED.value,
                    error_message=f"BATCH_NOT_FOUND: batch {batch_id} not found",
                )
                return"""

if old_code not in text:
    print("Pattern not found!")
else:
    text = text.replace(old_code, new_code, 1)
    path.write_text(text, encoding="utf-8")
    print("SUCCESS: patched item and batch null checks")
