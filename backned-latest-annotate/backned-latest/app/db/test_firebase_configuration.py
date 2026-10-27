from __future__ import annotations

from unittest.mock import patch

import pytest

from app.config import Settings
from app.db.firebase import FirebaseDatabase


def test_firestore_provider_uses_production_database() -> None:
    settings = Settings(DATABASE_PROVIDER="firestore", FIREBASE_DATABASE_ID="engenii-annotate-native")

    assert settings.database_provider == "firebase"
    assert settings.effective_firebase_project_id == "prod-y-in2300452"
    assert settings.effective_firebase_database_id == "engenii-annotate-native"

    with pytest.raises(ValueError, match="DATABASE_PROVIDER"):
        Settings(DATABASE_PROVIDER="mongodb")
    assert Settings(FIREBASE_DATABASE_ID="secondary").effective_firebase_database_id == "secondary"


def test_database_uses_native_firestore_client_and_no_memory_fallback() -> None:
    with patch("google.cloud.firestore.AsyncClient") as client_factory:
        db = FirebaseDatabase()

    client_factory.assert_called_once()
    call = client_factory.call_args.kwargs
    assert call["project"] == "prod-y-in2300452"
    assert call["database"] == "engenii-annotate-native"
    assert call["client_options"].api_endpoint == "firestore.googleapis.com"
    assert db.provider == "firebase"
    assert db.persistence_mode == "durable"
    assert db.allow_memory_fallback is False


def test_default_database_is_rejected_before_client_creation() -> None:
    with pytest.raises(ValueError, match="named Firestore database"):
        FirebaseDatabase(database_id="(default)")
