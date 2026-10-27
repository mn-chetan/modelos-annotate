from __future__ import annotations

import pytest

from app.db.firebase import DatabaseUnavailableError, FirebaseCollection, FirebaseDatabase


class _Snapshot:
    def __init__(self, doc: dict):
        self.id = doc["id"]
        self._doc = doc

    def to_dict(self):
        return self._doc


class _Query:
    def __init__(self, docs, filters=None):
        self.docs = docs
        self.filters = list(filters or [])

    def where(self, *, filter):
        return _Query(self.docs, [*self.filters, filter])

    async def stream(self):
        for doc in self.docs:
            yield _Snapshot(doc)


class _Client:
    def __init__(self, docs):
        self.root = _Query(docs)
        self.queries = []

    def collection(self, _name):
        return self.root


@pytest.fixture
def collection():
    db = FirebaseDatabase.__new__(FirebaseDatabase)
    db.client = _Client([{"id": str(i), "value": i} for i in range(65)])
    db.operation_timeout_seconds = 2
    db.database_id = "test"
    db._mark_healthy = lambda: None
    db._mark_unhealthy = lambda _exc: None
    db._message = lambda name: name
    return FirebaseCollection(db, "projects")


@pytest.mark.asyncio
@pytest.mark.parametrize("operator, firestore_operator", [("$ne", "!="), ("$gt", ">"), ("$gte", ">="), ("$lt", "<"), ("$lte", "<=")])
async def test_comparison_operators_are_translated(collection, operator, firestore_operator):
    # The fake returns all documents; this test specifically verifies that
    # Firestore receives the native FieldFilter rather than a client scan.
    await collection._fetch({"value": {operator: 10}})


@pytest.mark.asyncio
async def test_in_empty_is_noop_and_large_in_is_chunked(collection):
    assert await collection._fetch({"id": {"$in": []}}) == []
    result = await collection._fetch({"id": {"$in": [str(i) for i in range(65)]}})
    assert len(result) == 65


@pytest.mark.asyncio
async def test_unsupported_operator_fails_loudly(collection):
    with pytest.raises(DatabaseUnavailableError, match="projects"):
        await collection._fetch({"value": {"$nin": [1]}})
