from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.auth.exceptions import RefreshError

from app.db.firebase import FirebaseDatabase


@pytest.mark.asyncio
async def test_adc_reauthentication_keeps_firestore_unhealthy_and_logs_once() -> None:
    probe = MagicMock()
    refresh_exc = RefreshError("Reauthentication is needed. Please run gcloud auth application-default login")
    probe.set = AsyncMock(side_effect=refresh_exc)
    probe.get = AsyncMock(side_effect=refresh_exc)
    fake_client = MagicMock()
    fake_client.collection.return_value.document.return_value = probe

    with patch("google.cloud.firestore.AsyncClient", return_value=fake_client), patch(
        "app.db.firebase.logger.error"
    ) as log_error:
        db = FirebaseDatabase()
        assert await db.verify_connection() is False
        assert await db.verify_connection() is False

    assert db.provider == "firebase"
    assert db.project_id == "prod-y-in2300452"
    assert db.database_id == "engenii-annotate-native"
    assert db.authentication_required is True
    assert db.is_healthy is False
    assert db.persistence_mode == "unhealthy"
    assert "RefreshError" in db.last_error
    auth_logs = [call for call in log_error.call_args_list if call.args == ("firestore_authentication_required",)]
    assert len(auth_logs) == 1
