"""Canonical human-review action to asset-status mapping."""

from app.domain.enums import ReviewAction, ReviewStatus


def resolve_human_review(action: str, reason: str = "") -> tuple[str, str]:
    """Return the canonical persisted status and reason for a review action."""
    normalized = (action or "approve").lower().strip()
    if normalized in {"accept", "approve", "approved", "human_approved", "final_approve", ReviewAction.APPROVE.value}:
        return ReviewStatus.HUMAN_APPROVED.value, reason or "Human review approved"
    if normalized in {"modify", "edited", "human_modified_approved", ReviewAction.MODIFY.value}:
        return ReviewStatus.HUMAN_MODIFIED_APPROVED.value, reason or "Human modified annotations"
    if normalized in {"add_missing", "add_object", ReviewAction.ADD_MISSING.value}:
        return ReviewStatus.HUMAN_MODIFIED_APPROVED.value, reason or "Human added missing object"
    if normalized in {"delete_wrong", "delete_object", ReviewAction.DELETE_WRONG.value}:
        return ReviewStatus.HUMAN_MODIFIED_APPROVED.value, reason or "Human deleted false positive object"
    if normalized in {"reject", "rejected", "flagged", "human_rejected", "final_reject", ReviewAction.REJECT.value}:
        return ReviewStatus.HUMAN_REJECTED.value, reason or "Human review rejected"
    if normalized in {"reprocess", "retry", "reprocess_required", "request_reprocess", ReviewAction.REPROCESS.value}:
        return ReviewStatus.REPROCESS_REQUIRED.value, reason or "Queued for reprocessing"
    if normalized in {"escalate", "second_review", "escalated", ReviewAction.ESCALATE.value}:
        return ReviewStatus.ESCALATED.value, reason or "Escalated to SME for resolution"
    if normalized in {"rework", "request_rework"}:
        return "rework", reason or "Sent back to annotator for rework"
    if normalized in {"submit", "submit_for_review", "needs_review"}:
        return "needs_review", reason or "Submitted for review"
    if normalized in {"override", "sme_override", "resolve_conflict", "close_case"}:
        return "human_approved", reason or "SME override final decision approved"
    return normalized, reason
