"""Role-Based Access Control (RBAC) service for HITL workflow."""

from typing import Any

# Standard HITL Permissions
PERMISSION_ANNOTATION_VIEW = "ANNOTATION_VIEW"
PERMISSION_ANNOTATION_EDIT = "ANNOTATION_EDIT"
PERMISSION_ANNOTATION_CREATE = "ANNOTATION_CREATE"
PERMISSION_ANNOTATION_DELETE = "ANNOTATION_DELETE"
PERMISSION_COMMENT_ADD = "COMMENT_ADD"
PERMISSION_HITL_SUBMIT = "HITL_SUBMIT"
PERMISSION_HITL_APPROVE = "HITL_APPROVE"
PERMISSION_HITL_REJECT = "HITL_REJECT"
PERMISSION_HITL_REWORK = "HITL_REWORK"
PERMISSION_HITL_ESCALATE = "HITL_ESCALATE"
PERMISSION_HITL_OVERRIDE = "HITL_OVERRIDE"
PERMISSION_TASK_ASSIGN = "TASK_ASSIGN"
PERMISSION_TASK_REASSIGN = "TASK_REASSIGN"
PERMISSION_USER_MANAGE = "USER_MANAGE"
PERMISSION_ROLE_MANAGE = "ROLE_MANAGE"
PERMISSION_PERMISSION_MANAGE = "PERMISSION_MANAGE"
PERMISSION_AUDIT_VIEW = "AUDIT_VIEW"

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "HUMAN_ANNOTATOR": {
        PERMISSION_ANNOTATION_VIEW,
        PERMISSION_ANNOTATION_EDIT,
        PERMISSION_ANNOTATION_CREATE,
        PERMISSION_ANNOTATION_DELETE,
        PERMISSION_COMMENT_ADD,
        PERMISSION_HITL_SUBMIT,
        PERMISSION_HITL_APPROVE,
        PERMISSION_HITL_REJECT,
        PERMISSION_HITL_REWORK,
        PERMISSION_HITL_ESCALATE,
    },
    "QUALITY_AUDITOR": {
        PERMISSION_ANNOTATION_VIEW,
        PERMISSION_ANNOTATION_EDIT,
        PERMISSION_ANNOTATION_CREATE,
        PERMISSION_ANNOTATION_DELETE,
        PERMISSION_COMMENT_ADD,
        PERMISSION_HITL_SUBMIT,
        PERMISSION_HITL_APPROVE,
        PERMISSION_HITL_REJECT,
        PERMISSION_HITL_REWORK,
        PERMISSION_HITL_ESCALATE,
        PERMISSION_HITL_OVERRIDE,
    },
    "PROJECT_MANAGER": {
        PERMISSION_ANNOTATION_VIEW,
        PERMISSION_ANNOTATION_EDIT,
        PERMISSION_ANNOTATION_CREATE,
        PERMISSION_ANNOTATION_DELETE,
        PERMISSION_COMMENT_ADD,
        PERMISSION_HITL_SUBMIT,
        PERMISSION_HITL_APPROVE,
        PERMISSION_HITL_REJECT,
        PERMISSION_HITL_REWORK,
        PERMISSION_HITL_ESCALATE,
        PERMISSION_HITL_OVERRIDE,
        PERMISSION_USER_MANAGE,
        PERMISSION_ROLE_MANAGE,
        PERMISSION_PERMISSION_MANAGE,
        PERMISSION_TASK_ASSIGN,
        PERMISSION_TASK_REASSIGN,
        PERMISSION_AUDIT_VIEW,
    },
}

ACTION_PERMISSIONS: dict[str, str] = {
    "submit": PERMISSION_HITL_SUBMIT,
    "submit_for_review": PERMISSION_HITL_SUBMIT,
    "needs_review": PERMISSION_HITL_SUBMIT,
    "approve": PERMISSION_HITL_APPROVE,
    "human_approved": PERMISSION_HITL_APPROVE,
    "final_approve": PERMISSION_HITL_APPROVE,
    "reject": PERMISSION_HITL_REJECT,
    "human_rejected": PERMISSION_HITL_REJECT,
    "final_reject": PERMISSION_HITL_REJECT,
    "rework": PERMISSION_HITL_REWORK,
    "request_rework": PERMISSION_HITL_REWORK,
    "escalate": PERMISSION_HITL_ESCALATE,
    "escalated": PERMISSION_HITL_ESCALATE,
    "override": PERMISSION_HITL_OVERRIDE,
    "sme_override": PERMISSION_HITL_OVERRIDE,
    "resolve_conflict": PERMISSION_HITL_OVERRIDE,
    "close_case": PERMISSION_HITL_OVERRIDE,
    "modify": PERMISSION_ANNOTATION_EDIT,
    "add_missing": PERMISSION_ANNOTATION_CREATE,
    "delete": PERMISSION_ANNOTATION_DELETE,
    "reprocess": PERMISSION_HITL_REWORK,
    "request_reprocess": PERMISSION_HITL_REWORK,
    "comment": PERMISSION_COMMENT_ADD,
    "add_comment": PERMISSION_COMMENT_ADD,
    "view": PERMISSION_ANNOTATION_VIEW,
}


def normalize_role(role: str | None) -> str:
    if not role:
        return "HUMAN_ANNOTATOR"
    role_str = str(role).strip()
    role_lower = role_str.lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "annotator": "HUMAN_ANNOTATOR",
        "human_annotator": "HUMAN_ANNOTATOR",
        "reviewer": "QUALITY_AUDITOR",
        "reviewer_/_qa": "QUALITY_AUDITOR",
        "qa": "QUALITY_AUDITOR",
        "quality_auditor": "QUALITY_AUDITOR",
        "sme": "QUALITY_AUDITOR",
        "admin": "PROJECT_MANAGER",
        "project_manager": "PROJECT_MANAGER",
    }
    return aliases.get(role_lower, role_str.upper())


def get_role_permissions(role: str, custom_permissions: list[str] | None = None) -> set[str]:
    norm_role = normalize_role(role)
    base_perms = set(ROLE_PERMISSIONS.get(norm_role, set()))
    if custom_permissions:
        base_perms.update(custom_permissions)
    return base_perms


def has_permission(role: str, permission: str, custom_permissions: list[str] | None = None) -> bool:
    perms = get_role_permissions(role, custom_permissions)
    return permission in perms


def check_action_permission(role: str, action: str, custom_permissions: list[str] | None = None) -> tuple[bool, str | None]:
    norm_action = str(action).lower().strip()
    required_perm = ACTION_PERMISSIONS.get(norm_action)
    if not required_perm:
        return False, f"Action '{action}' is unmapped or unrecognized"
    
    if has_permission(role, required_perm, custom_permissions):
        return True, None
    
    norm_role = normalize_role(role)
    return False, f"Role '{norm_role}' lacks required permission '{required_perm}' for action '{action}'"
