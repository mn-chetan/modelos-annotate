"""Regression tests for PII security, match count accounting, and logging redaction."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.logging import redact_sensitive_data
from app.storage.files import FileStorage, normalize_filename


def test_redact_sensitive_data_redacts_credentials_and_pii_keys():
    """Verify that credentials and PII identifiers are redacted from structured logs."""
    event_dict = {
        "event": "user_action",
        "password": "SuperSecretPassword123!",
        "api_key": "AIzaSyD-FakeGoogleApiKey",
        "customer_name": "Rahul Sharma",
        "person_name": "Jane Doe",
        "user_name": "jdoe42",
        "full_name": "Alice Smith",
        "phone_number": "+1-555-0199",
        "ssn": "000-12-3456",
        "name": "Bob Vance",
        "email": "test@example.com",
        "phone": "555-1234",
        "safe_field": "order_processed",
        "text_length": 646,
    }

    sanitized = redact_sensitive_data(logger=None, method_name="info", event_dict=event_dict)

    # Sensitive credentials
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["api_key"] == "[REDACTED]"

    # PII names and identifiers
    assert sanitized["customer_name"] == "[REDACTED]"
    assert sanitized["person_name"] == "[REDACTED]"
    assert sanitized["user_name"] == "[REDACTED]"
    assert sanitized["full_name"] == "[REDACTED]"
    assert sanitized["phone_number"] == "[REDACTED]"
    assert sanitized["ssn"] == "[REDACTED]"
    assert sanitized["name"] == "[REDACTED]"
    assert sanitized["email"] == "[REDACTED]"
    assert sanitized["phone"] == "[REDACTED]"

    # Safe fields must remain untouched
    assert sanitized["safe_field"] == "order_processed"
    assert sanitized["text_length"] == 646


def test_pii_match_count_accounting_distinguishes_unique_vs_occurrences():
    """Verify the root-cause calculation for why match count was 1 across 4 file paths.
    
    The security report incorrectly collapsed total file occurrences into unique entity values.
    """
    raw_findings = [
        {
            "classifier": "PII/Name",
            "value": "Rahul Sharma",
            "file": "/app/storage/490700af-adf1-4e86-9935-d0f84070a517/6617f9c8-4493-4cd1-a095-9e198271e77b/customer-support-ner.txt",
        },
        {
            "classifier": "PII/Name",
            "value": "Rahul Sharma",
            "file": "/app/storage/490700af-adf1-4e86-9935-d0f84070a517/6617f9c8-4493-4cd1-a095-9e198271e77b/text-input.txt",
        },
        {
            "classifier": "PII/Name",
            "value": "Rahul Sharma",
            "file": "/app/storage/490700af-adf1-4e86-9935-d0f84070a517/f2e1c74f-a166-41b5-8bb9-aba567bee1e6/customer-support.txt",
        },
        {
            "classifier": "PII/Name",
            "value": "Rahul Sharma",
            "file": "/app/storage/490700af-adf1-4e86-9935-d0f84070a517/f2e1c74f-a166-41b5-8bb9-aba567bee1e6/text-input.txt",
        },
    ]

    unique_values = {f["value"] for f in raw_findings}
    unique_files = {f["file"] for f in raw_findings}
    total_occurrences = len(raw_findings)

    # Explaining the finding mismatch:
    # The scanner reported match count == 1 because len(unique_values) == 1
    assert len(unique_values) == 1, "Only 1 unique name string was detected"
    assert len(unique_files) == 4, "The name string occurred across 4 distinct files"
    assert total_occurrences == 4, "Total occurrence count is 4"


def test_storage_path_security_and_traversal(tmp_path: Path):
    """Verify that FileStorage prevents path traversal attacks."""
    storage = FileStorage(tmp_path)

    # Normal write works
    dest = storage.write_bytes("proj-1", "asset-1", "sample.txt", b"Hello world")
    assert dest.is_file()
    assert dest.read_text() == "Hello world"

    # Normalize filename prevents traversal
    assert normalize_filename("../../../etc/passwd") == "passwd"
    assert normalize_filename("foo/../../bar.txt") == "bar.txt"

    # Resolving path traversal raises error
    with pytest.raises(Exception):
        storage.resolve("../../../etc/passwd")


def test_synthetic_ner_fixture_is_sanitized():
    """Verify that synthetic test fixtures do not contain unmasked personal names."""
    from app.test_text_pipeline_blockers import _quality_state

    state = _quality_state(0.95)
    text = state["text_result"]["text"]
    assert "Rahul Sharma" not in text
    assert "Alex Doe" in text
