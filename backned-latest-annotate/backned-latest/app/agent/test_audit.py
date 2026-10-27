from __future__ import annotations

import app.agent.audit as audit_module
from app.agent.audit import create_audit_record


class _CaptureLogger:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def info(self, event_name: str, **fields: object) -> None:
        self.calls.append((event_name, fields))


def _record():
    return create_audit_record(
        project_id="record-project",
        asset_id="asset-123",
        user_request="annotate this asset",
        ontology_snapshot=[],
        available_models={"yolo26": True},
    )


def test_audit_log_event_merges_duplicate_project_id_without_type_error(monkeypatch):
    captured = _CaptureLogger()
    monkeypatch.setattr(audit_module, "logger", captured)

    _record().log_event(
        "agent_decision",
        {
            "project_id": "project-123",
            "batch_id": "batch-123",
            "job_id": "job-123",
            "quality_action": "RETRY",
            "next_node": "replan",
        },
    )

    event_name, fields = captured.calls[0]
    assert event_name == "agent_audit_agent_decision"
    assert fields["project_id"] == "project-123"
    assert fields["batch_id"] == "batch-123"
    assert fields["job_id"] == "job-123"
    assert fields["quality_action"] == "RETRY"
    assert fields["next_node"] == "replan"


def test_audit_log_event_uses_record_project_when_payload_omits_it(monkeypatch):
    captured = _CaptureLogger()
    monkeypatch.setattr(audit_module, "logger", captured)

    _record().log_event("model_execution", {"model_id": "yolo26"})

    _, fields = captured.calls[0]
    assert fields["project_id"] == "record-project"
    assert fields["model_id"] == "yolo26"
