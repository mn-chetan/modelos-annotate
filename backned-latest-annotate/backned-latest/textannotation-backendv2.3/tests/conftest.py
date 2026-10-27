from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.main import app


class FakeCollection:
    def __init__(self):
        self.documents: list[dict] = []
        self.indexes: list[tuple[str, bool]] = []

    async def insert_one(self, document):
        self.documents.append(document)
        return SimpleNamespace(inserted_id=str(uuid4()))

    async def create_index(self, *args, **kwargs):
        self.indexes.append((str(args[0]), bool(kwargs.get("unique", False))))

    async def find_one(self, query):
        for document in self.documents:
            if all(document.get(key) == value for key, value in query.items()):
                return document
        return None

    def find(self, query, projection=None):
        def matches(document: dict) -> bool:
            for key, expected in query.items():
                actual = document.get(key)
                if isinstance(expected, dict):
                    if "$ne" in expected and actual == expected["$ne"]:
                        return False
                    if "$in" in expected and actual not in expected["$in"]:
                        return False
                elif actual != expected:
                    return False
            return True

        return FakeCursor([document for document in self.documents if matches(document)], projection)

    async def update_one(self, query, update):
        document = await self.find_one(query)
        if document is None:
            return SimpleNamespace(matched_count=0, modified_count=0)

        if "$set" in update:
            document.update(update["$set"])

        return SimpleNamespace(matched_count=1, modified_count=1)


class FakeCursor:
    def __init__(self, documents: list[dict], projection: dict | None = None):
        self.documents = documents
        self.projection = projection or {}

    async def to_list(self, length=None):
        if not self.projection:
            return list(self.documents)

        projected_documents: list[dict] = []
        include_keys = {key for key, value in self.projection.items() if value}
        exclude_keys = {key for key, value in self.projection.items() if not value}

        for document in self.documents:
            if include_keys:
                projected_document = {key: value for key, value in document.items() if key in include_keys}
            else:
                projected_document = dict(document)
            for key in exclude_keys:
                projected_document.pop(key, None)
            projected_documents.append(projected_document)

        return projected_documents


class FakeDatabase(dict):
    def __init__(self):
        super().__init__({"sources": FakeCollection(), "analyses": FakeCollection()})


@pytest.fixture()
def client() -> AsyncIterator[TestClient]:
    fake_db = FakeDatabase()
    with patch("app.database.mongodb.MongoDB.connect", AsyncMock(return_value=fake_db)), patch(
        "app.database.mongodb.MongoDB.init_indexes", AsyncMock(return_value=None)
    ), patch("app.database.mongodb.MongoDB.close", AsyncMock(return_value=None)), patch(
        "app.database.mongodb.MongoDB.ping", AsyncMock(return_value=True)
    ):
        with TestClient(app) as test_client:
            test_client.app.state.fake_db = fake_db
            yield test_client
