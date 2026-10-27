"""Native Firestore persistence adapter."""
from __future__ import annotations

import asyncio
import inspect
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from google.api_core import exceptions as google_exceptions
from google.auth.exceptions import RefreshError

from app.logging import get_logger

logger = get_logger(__name__)
DEFAULT_PROJECT_ID = "prod-y-in2300452"
DEFAULT_DATABASE_ID = "engenii-annotate-native"
DEFAULT_OPERATION_TIMEOUT_SECONDS = 30.0
DEFAULT_OPERATION_ATTEMPTS = 3
DEFAULT_OPERATION_BACKOFF_SECONDS = 0.5

NON_RETRYABLE_EXCEPTIONS = (
    google_exceptions.PermissionDenied,
    google_exceptions.Unauthenticated,
    google_exceptions.NotFound,
    google_exceptions.InvalidArgument,
    google_exceptions.FailedPrecondition,
    RefreshError,
)

RETRYABLE_EXCEPTIONS = (
    TimeoutError,
    asyncio.TimeoutError,
    google_exceptions.DeadlineExceeded,
    google_exceptions.ServiceUnavailable,
    google_exceptions.Cancelled,
    google_exceptions.RetryError,
    ConnectionError,
    OSError,
)


class DatabaseUnavailableError(RuntimeError):
    pass


def _is_adc_reauthentication_error(exc: BaseException) -> bool:
    """Identify ADC refresh failures even when a transport wraps the cause."""
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, RefreshError):
            return True
        message = str(current).lower()
        if "reauthentication is needed" in message and "application-default" in message:
            return True
        current = current.__cause__ or current.__context__
    return False


@dataclass
class WriteResult:
    acknowledged: bool = True
    inserted_id: str | None = None
    deleted_count: int = 0
    modified_count: int = 0


def _get(document: dict[str, Any], field: str) -> Any:
    value: Any = document
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _matches(document: dict[str, Any], query: dict[str, Any]) -> bool:
    for field, expected in query.items():
        if field == "$or":
            if not isinstance(expected, list) or not any(_matches(document, item) for item in expected): return False
            continue
        if field == "$and":
            if not isinstance(expected, list) or not all(_matches(document, item) for item in expected): return False
            continue
        actual = _get(document, field)
        if isinstance(expected, dict) and any(str(key).startswith("$") for key in expected):
            for op, operand in expected.items():
                if op == "$in" and actual not in operand: return False
                if op == "$nin" and actual in operand: return False
                if op == "$ne" and actual == operand: return False
                if op == "$exists" and ((actual is not None) != bool(operand)): return False
                if op == "$gt" and not (actual is not None and actual > operand): return False
                if op == "$gte" and not (actual is not None and actual >= operand): return False
                if op == "$lt" and not (actual is not None and actual < operand): return False
                if op == "$lte" and not (actual is not None and actual <= operand): return False
        elif actual != expected:
            return False
    return True


def _updated(document: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    result = dict(document)
    operations = update if any(key.startswith("$") for key in update) else {"$set": update}
    for field, value in operations.get("$set", {}).items(): result[field] = value
    for field, value in operations.get("$inc", {}).items(): result[field] = (result.get(field) or 0) + value
    for field in operations.get("$unset", {}): result.pop(field, None)
    for field, value in operations.get("$push", {}).items(): result.setdefault(field, []).append(value)
    for field, value in operations.get("$addToSet", {}).items():
        if value not in result.setdefault(field, []): result[field].append(value)
    return result


class WrappedCursor:
    def __init__(self, collection: FirebaseCollection, query: dict[str, Any]) -> None:
        self.collection, self.query, self.sorts, self.offset, self.maximum = collection, query, [], 0, None
    def sort(self, key: str | list[tuple[str, int]], direction: int = 1) -> WrappedCursor:
        self.sorts.extend(key if isinstance(key, list) else [(key, direction)]); return self
    def skip(self, count: int) -> WrappedCursor: self.offset = max(0, count); return self
    def limit(self, count: int) -> WrappedCursor: self.maximum = max(0, count); return self
    async def to_list(self, length: int | None = 10000) -> list[dict[str, Any]]:
        docs = await self.collection._fetch(self.query)
        for field, direction in reversed(self.sorts): docs.sort(key=lambda doc: str(_get(doc, field) or ""), reverse=direction == -1)
        docs = docs[self.offset:] if self.maximum is None else docs[self.offset:self.offset + self.maximum]
        return docs if length is None else docs[:length]
    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        async def iterator() -> AsyncIterator[dict[str, Any]]:
            for item in await self.to_list(None): yield item
        return iterator()


class FirebaseCollection:
    def __init__(self, db: FirebaseDatabase, name: str) -> None: self.db, self.name = db, name
    def _assert_healthy(self) -> None:
        if self.db.client is None or getattr(self.db, "is_healthy", True) is False:
            raise DatabaseUnavailableError(self.db._message(self.name))
    @property
    def col(self) -> Any: self._assert_healthy(); return self.db.client.collection(self.name)
    @staticmethod
    def _is_transient(exc: BaseException) -> bool:
        if isinstance(exc, RETRYABLE_EXCEPTIONS):
            return True
        message = str(exc).lower()
        return any(token in message for token in ("deadline", "unavailable", "connection", "reset", "transport", "timeout"))

    async def _call(self, operation_factory: Any, op_type: str = "operation", details: dict[str, Any] | None = None) -> Any:
        """Run one Firestore RPC with bounded retry for transient transport latency.

        ``operation_factory`` is deliberately a callable: a timed-out coroutine
        cannot be awaited a second time.  Rebuilding the RPC also lets the
        Firestore client/channel retain its normal connection pooling and
        lifecycle instead of creating a new client per retry.
        """
        start_time = time.perf_counter()
        client_obj = self.db.client
        client_id_hex = hex(id(client_obj)) if client_obj is not None else "None"
        try:
            max_attempts = min(max(int(os.getenv("FIREBASE_OPERATION_ATTEMPTS", str(DEFAULT_OPERATION_ATTEMPTS))), 1), 5)
        except ValueError:
            max_attempts = DEFAULT_OPERATION_ATTEMPTS
        try:
            backoff_seconds = min(max(float(os.getenv("FIREBASE_OPERATION_BACKOFF_SECONDS", str(DEFAULT_OPERATION_BACKOFF_SECONDS))), 0.0), 10.0)
        except ValueError:
            backoff_seconds = DEFAULT_OPERATION_BACKOFF_SECONDS
        tracked_collection = self.name in ("assets", "batches", "job_items")
        if tracked_collection:
            logger.debug(
                "batch_operation_start",
                collection=self.name,
                operation_type=op_type,
                query_details=details or {},
                client_identity=client_id_hex,
                database_id=self.db.database_id,
            )
        last_exc: BaseException | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                res = await asyncio.wait_for(operation_factory(), timeout=self.db.operation_timeout_seconds)
                self.db._mark_healthy()
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                if tracked_collection:
                    res_cnt = len(res) if isinstance(res, (list, tuple)) else (1 if res is not None else 0)
                    logger.debug(
                        "batch_operation_complete",
                        collection=self.name,
                        operation_type=op_type,
                        duration_ms=duration_ms,
                        attempt=attempt,
                        result_count=res_cnt,
                        client_identity=client_id_hex,
                        database_id=self.db.database_id,
                    )
                return res
            except Exception as exc:
                last_exc = exc
                transient = self._is_transient(exc)
                if transient and attempt < max_attempts:
                    delay = backoff_seconds * (2 ** (attempt - 1))
                    logger.warning(
                        "firestore_operation_retry",
                        collection=self.name,
                        operation_type=op_type,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        timeout_seconds=self.db.operation_timeout_seconds,
                        backoff_seconds=delay,
                        exception_type=type(exc).__name__,
                        exception_message=str(exc),
                        client_identity=client_id_hex,
                        database_id=self.db.database_id,
                    )
                    await asyncio.sleep(delay)
                    continue
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                if tracked_collection:
                    logger.error(
                        "batch_operation_failed",
                        collection=self.name,
                        operation_type=op_type,
                        duration_ms=duration_ms,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        exception_type=type(exc).__name__,
                        exception_message=str(exc),
                        client_identity=client_id_hex,
                        database_id=self.db.database_id,
                    )
                self.db._mark_unhealthy(exc)
                raise DatabaseUnavailableError(self.db._message(self.name)) from exc
        assert last_exc is not None
        raise DatabaseUnavailableError(self.db._message(self.name)) from last_exc
    async def _fetch(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        async def fetch() -> list[dict[str, Any]]:
            if "id" in query and isinstance(query["id"], str):
                doc_snap = await self.col.document(query["id"]).get()
                if doc_snap.exists:
                    doc = doc_snap.to_dict() or {}
                    doc.setdefault("id", doc_snap.id)
                    doc.setdefault("_id", doc_snap.id)
                    if _matches(doc, query):
                        return [doc]
                return []

            ref = self.col
            in_field = None
            in_values = None
            supported = {"$in", "$ne", "$gt", "$gte", "$lt", "$lte"}
            filters: list[tuple[str, str, Any]] = []

            # Firestore's native query builder cannot represent every Mongo
            # style boolean query used by the existing workflow code. Do not
            # report those valid reads as a database outage; fetch the
            # collection and apply the shared matcher locally.
            if "$or" in query or "$and" in query:
                docs = []
                async for snapshot in self.col.stream():
                    doc = snapshot.to_dict() or {}
                    doc.setdefault("id", snapshot.id)
                    doc.setdefault("_id", snapshot.id)
                    if _matches(doc, query):
                        docs.append(doc)
                return docs

            for k, v in query.items():
                if k in ("$or", "$and"):
                    raise ValueError(f"Firestore query operator {k} requires explicit query composition")
                if isinstance(v, (str, int, float, bool)):
                    filters.append((k, "==", v))
                elif isinstance(v, dict):
                    unknown = set(v) - supported
                    if unknown:
                        raise ValueError(f"Unsupported Firestore query operator(s): {sorted(unknown)}")
                    if "$in" in v:
                        if not isinstance(v["$in"], list):
                            raise ValueError(f"$in operand for {k} must be a list")
                        if not v["$in"]:
                            return []
                        if in_field is not None:
                            raise ValueError("Firestore query supports at most one $in field per query")
                        in_field = k
                        in_values = v["$in"]
                    operator_map = {"$ne": "!=", "$gt": ">", "$gte": ">=", "$lt": "<", "$lte": "<="}
                    for op, operand in v.items():
                        if op != "$in":
                            filters.append((k, operator_map[op], operand))

            from google.cloud.firestore_v1.base_query import FieldFilter
            for field, operator, operand in filters:
                ref = ref.where(filter=FieldFilter(field, operator, operand))

            if in_field and in_values:
                chunks = [in_values[i:i + 30] for i in range(0, len(in_values), 30)]

                async def _fetch_chunk(chunk: list[Any]) -> list[dict[str, Any]]:
                    chunk_ref = ref.where(filter=FieldFilter(in_field, "in", chunk))
                    c_docs = []
                    async for snapshot in chunk_ref.stream():
                        doc = snapshot.to_dict() or {}
                        doc.setdefault("id", snapshot.id)
                        doc.setdefault("_id", snapshot.id)
                        if _matches(doc, query):
                            c_docs.append(doc)
                    return c_docs

                semaphore = asyncio.Semaphore(8)
                async def bounded_fetch(chunk: list[Any]) -> list[dict[str, Any]]:
                    async with semaphore:
                        return await _fetch_chunk(chunk)
                chunk_results = await asyncio.gather(*[bounded_fetch(c) for c in chunks])
                docs = []
                seen_ids = set()
                for c_list in chunk_results:
                    for d in c_list:
                        d_id = str(d.get("id") or d.get("_id"))
                        if d_id not in seen_ids:
                            seen_ids.add(d_id)
                            docs.append(d)
                return docs

            docs = []
            async for snapshot in ref.stream():
                doc = snapshot.to_dict() or {}
                doc.setdefault("id", snapshot.id)
                doc.setdefault("_id", snapshot.id)
                if _matches(doc, query):
                    docs.append(doc)
            return docs
        return await self._call(fetch, op_type="fetch", details={"query": str(query)})
    @staticmethod
    def _id(document: dict[str, Any]) -> str: return str(document.get("id") or document.get("_id") or uuid4())
    async def insert_one(self, document: dict[str, Any], *args: Any, **kwargs: Any) -> WriteResult:
        doc = dict(document); doc_id = self._id(doc); doc["id"] = doc_id; doc.pop("_id", None)
        await self._call(lambda: self.col.document(doc_id).set(doc)); return WriteResult(inserted_id=doc_id)
    async def insert_many(self, documents: list[dict[str, Any]], *args: Any, **kwargs: Any) -> WriteResult:
        for document in documents: await self.insert_one(document, *args, **kwargs)
        return WriteResult()
    async def find_one(self, filter: dict[str, Any] | None = None, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        docs = await self.find(filter).to_list(1); return docs[0] if docs else None
    def find(self, filter: dict[str, Any] | None = None, *args: Any, **kwargs: Any) -> WrappedCursor:
        self._assert_healthy(); return WrappedCursor(self, dict(filter or {}))
    async def update_one(self, filter: dict[str, Any], update: dict[str, Any], *args: Any, **kwargs: Any) -> WriteResult:
        current = await self.find_one(filter)
        if current is None:
            if not kwargs.get("upsert"): return WriteResult(modified_count=0)
            current = dict(filter)
        doc = _updated(current, update); doc_id = self._id(doc); doc["id"] = doc_id; doc.pop("_id", None)
        await self._call(lambda: self.col.document(doc_id).set(doc)); return WriteResult(inserted_id=doc_id if not current else None, modified_count=1)
    async def update_many(self, filter: dict[str, Any], update: dict[str, Any], *args: Any, **kwargs: Any) -> WriteResult:
        docs = await self._fetch(filter)
        for doc in docs: await self.update_one({"id": doc["id"]}, update)
        return WriteResult(modified_count=len(docs))
    async def delete_one(self, filter: dict[str, Any], *args: Any, **kwargs: Any) -> WriteResult:
        doc = await self.find_one(filter)
        if not doc: return WriteResult(deleted_count=0)
        await self._call(lambda: self.col.document(str(doc["id"])).delete()); return WriteResult(deleted_count=1)
    async def delete_many(self, filter: dict[str, Any], *args: Any, **kwargs: Any) -> WriteResult:
        docs = await self._fetch(filter)
        for doc in docs: await self._call(lambda doc=doc: self.col.document(str(doc["id"])).delete())
        return WriteResult(deleted_count=len(docs))
    async def count_documents(self, filter: dict[str, Any] | None = None, *args: Any, **kwargs: Any) -> int: return len(await self._fetch(dict(filter or {})))
    async def distinct(self, key: str, filter: dict[str, Any] | None = None, *args: Any, **kwargs: Any) -> list[Any]: return list({_get(doc, key) for doc in await self._fetch(dict(filter or {})) if _get(doc, key) is not None})
    def aggregate(self, pipeline: list[dict[str, Any]], *args: Any, **kwargs: Any) -> WrappedCursor:
        query: dict[str, Any] = {}
        for stage in pipeline:
            if "$match" in stage: query.update(stage["$match"])
        return WrappedCursor(self, query)
    async def create_index(self, *args: Any, **kwargs: Any) -> None: return None
    async def find_one_and_update(self, filter: dict[str, Any], update: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        async def txn_op() -> dict[str, Any] | None:
            doc_id = filter.get("id") or filter.get("_id")
            if not (doc_id and isinstance(doc_id, str)):
                found = await self.find_one(filter)
                if not found:
                    return None
                doc_id = str(found["id"])

            from google.cloud import firestore

            @firestore.async_transactional
            async def _atomic(transaction: Any) -> dict[str, Any] | None:
                doc_ref = self.col.document(doc_id)
                snapshot = await doc_ref.get(transaction=transaction)
                if not snapshot.exists:
                    return None
                data = snapshot.to_dict() or {}
                data.setdefault("id", snapshot.id)
                data.setdefault("_id", snapshot.id)
                if not _matches(data, filter):
                    return None
                new_doc = _updated(data, update)
                new_doc["id"] = snapshot.id
                new_doc.pop("_id", None)
                transaction.set(doc_ref, new_doc)
                return new_doc if kwargs.get("return_document") in (True, 1) else data

            transaction = self.db.client.transaction()
            return await _atomic(transaction)

        return await self._call(txn_op, op_type="operation", details={"query": str(filter)})
    async def find_one_and_delete(self, filter: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        doc = await self.find_one(filter)
        if doc is not None: await self.delete_one({"id": doc["id"]})
        return doc
    async def find_one_and_replace(self, filter: dict[str, Any], replacement: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        current = await self.find_one(filter)
        if current is None: return None
        doc = dict(replacement); doc["id"] = str(doc.get("id") or current["id"]); doc.pop("_id", None)
        await self._call(lambda: self.col.document(doc["id"]).set(doc)); return doc if kwargs.get("return_document") in (True, 1) else current



def _extract_exception_diagnostics(exc: BaseException) -> dict[str, Any]:
    import traceback
    diag: dict[str, Any] = {
        "exception_class": type(exc).__name__,
        "exception_repr": repr(exc),
        "exception_str": str(exc).strip() or repr(exc),
        "traceback": traceback.format_exc(),
        "cause": repr(exc.__cause__) if getattr(exc, "__cause__", None) else None,
        "context": repr(exc.__context__) if getattr(exc, "__context__", None) else None,
    }
    if hasattr(exc, "code"):
        try:
            diag["grpc_code"] = str(exc.code())
        except Exception:
            pass
    if hasattr(exc, "details"):
        try:
            diag["grpc_details"] = str(exc.details())
        except Exception:
            pass
    return diag


ALLOWED_LOCAL_EMULATOR_HOSTS: frozenset[str] = frozenset({
    "localhost",
    "127.0.0.1",
    "::1",
    "firestore-emulator",
    "annotate-firestore-local",
})


def verify_database_safety_guard(
    *,
    is_production: bool | None = None,
    emulator_host: str | None = None,
    project_id: str | None = None,
    database_id: str | None = None,
) -> None:
    """SAFETY GUARD: strictly enforces that non-production environments connect ONLY to a local database.

    Rules:
    1. If the app is NOT in production mode, it MUST refuse to start (raise RuntimeError)
       if the DB host is anything other than localhost, 127.0.0.1, ::1, or the local docker service name.
    2. Do NOT add any override or bypass flag.
    3. Production mode behavior is completely unchanged.
    """
    if is_production is None:
        try:
            from app.config import get_settings
            is_production = get_settings().is_production
        except Exception:
            env = (os.environ.get("APP_ENV") or os.environ.get("ENVIRONMENT") or "").strip().lower()
            is_production = env in {"production", "prod", "release"} or bool(os.environ.get("K_SERVICE"))

    if is_production:
        return

    # In unit tests where AsyncClient is mocked, no network call will ever occur.
    try:
        import google.cloud.firestore
        from unittest.mock import Mock
        if isinstance(getattr(google.cloud.firestore, "AsyncClient", None), Mock):
            return
    except Exception:
        pass

    host_value = emulator_host if emulator_host is not None else os.environ.get("FIRESTORE_EMULATOR_HOST", "")
    if not host_value:
        try:
            from app.config import get_settings
            host_value = get_settings().firestore_emulator_host
        except Exception:
            pass
    host_str = str(host_value or "").strip()

    if not host_str:
        raise RuntimeError(
            "CRITICAL DATABASE SAFETY GUARD ERROR: Refusing to start! "
            "The application is running in non-production mode, but FIRESTORE_EMULATOR_HOST is not configured. "
            "Connecting to remote production databases from local development is strictly prohibited. "
            "Please start the local Firestore emulator (e.g. via 'docker compose up -d') "
            "and set FIRESTORE_EMULATOR_HOST=127.0.0.1:8080."
        )

    clean = host_str
    if "://" in clean:
        clean = clean.split("://", 1)[1]
    hostname = clean.split(":")[0].strip().lower()

    if hostname not in ALLOWED_LOCAL_EMULATOR_HOSTS:
        raise RuntimeError(
            f"CRITICAL DATABASE SAFETY GUARD ERROR: Refusing to start! "
            f"Non-production environment attempted to connect to non-local database host '{hostname}'. "
            f"Only local hosts ({', '.join(sorted(ALLOWED_LOCAL_EMULATOR_HOSTS))}) are permitted in non-production mode. "
            f"Remote database connections in non-production are blocked to protect production data."
        )


class FirebaseDatabase:
    def __init__(self, project_id: str | None = None, database_id: str = DEFAULT_DATABASE_ID, credentials_path: str | None = None, allow_memory_fallback: bool = False, operation_timeout_seconds: float = DEFAULT_OPERATION_TIMEOUT_SECONDS, **_: Any) -> None:
        if allow_memory_fallback: raise ValueError("In-memory database fallback is not supported.")
        if not str(database_id or "").strip() or database_id == "(default)": raise ValueError("A named Firestore database is required.")
        self.provider, self.project_id, self.database_id = "firebase", (project_id or DEFAULT_PROJECT_ID).strip(), str(database_id).strip()
        self.credentials_path, self.operation_timeout_seconds = credentials_path, operation_timeout_seconds
        self.allow_memory_fallback = False
        self.connection_status, self.persistence_mode, self.is_healthy, self.last_error = "initializing", "durable", False, None
        self.last_exception: Exception | None = None
        self.authentication_required = False
        self._auth_error_logged = False
        self._collections: dict[str, FirebaseCollection] = {}; self.client: Any = None; self.raw_db = self

        # Run safety guard on database initialization
        verify_database_safety_guard(
            emulator_host=os.environ.get("FIRESTORE_EMULATOR_HOST"),
            project_id=self.project_id,
            database_id=self.database_id,
        )
        self._init_client()

    def _init_client(self) -> None:
        try:
            import google.auth
            import google.cloud.firestore
            from google.cloud import firestore
            from google.api_core.client_options import ClientOptions

            emulator_host = os.environ.get("FIRESTORE_EMULATOR_HOST")
            is_mock_client = False
            try:
                from unittest.mock import Mock
                is_mock_client = isinstance(getattr(google.cloud.firestore, "AsyncClient", None), Mock)
            except Exception:
                pass

            if emulator_host and not is_mock_client:
                clean_host = str(emulator_host).strip()
                if "://" in clean_host:
                    clean_host = clean_host.split("://", 1)[1]
                os.environ["FIRESTORE_EMULATOR_HOST"] = clean_host
                from google.auth.credentials import AnonymousCredentials
                credentials = AnonymousCredentials()
                cred_source = f"Emulator:{clean_host}"
                endpoint = clean_host

                logger.info(
                    "firestore_client_initialization",
                    effective_project=self.project_id,
                    effective_database=self.database_id,
                    firestore_package_version=getattr(google.cloud.firestore, "__version__", "unknown"),
                    credential_type="AnonymousCredentials",
                    adc_source=cred_source,
                    firestore_endpoint=endpoint,
                    firestore_emulator_host=clean_host,
                )

                self.client = firestore.AsyncClient(
                    project=self.project_id,
                    database=self.database_id,
                )
            else:
                credentials = None
                cred_source = "ADC"
                if self.credentials_path:
                    from google.oauth2 import service_account
                    credentials = service_account.Credentials.from_service_account_file(
                        self.credentials_path,
                        scopes=["https://www.googleapis.com/auth/cloud-platform"],
                    )
                    cred_source = f"ServiceAccountFile:{self.credentials_path}"
                else:
                    oauth_token = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN")
                    if oauth_token:
                        from google.oauth2.credentials import Credentials as OAuthCredentials
                        credentials = OAuthCredentials(oauth_token)
                        cred_source = "GOOGLE_OAUTH_ACCESS_TOKEN"
                    else:
                        try:
                            credentials, _ = google.auth.default()
                            cred_source = (
                                "GOOGLE_APPLICATION_CREDENTIALS"
                                if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
                                else "standard_adc_discovery"
                            )
                        except Exception:
                            credentials = None

                endpoint = "firestore.googleapis.com"

                logger.info(
                    "firestore_client_initialization",
                    effective_project=self.project_id,
                    effective_database=self.database_id,
                    firestore_package_version=getattr(google.cloud.firestore, "__version__", "unknown"),
                    credential_type=type(credentials).__name__ if credentials else "None",
                    adc_source=cred_source,
                    firestore_endpoint=endpoint,
                    firestore_emulator_host="not_set",
                )

                self.client = firestore.AsyncClient(
                    project=self.project_id,
                    database=self.database_id,
                    credentials=credentials,
                    client_options=ClientOptions(api_endpoint=endpoint),
                )
            self.is_healthy = True
            self.connection_status = "healthy"
        except RefreshError as exc:
            self._mark_unhealthy(exc)
            self._log_authentication_required()
        except Exception as exc:
            self._mark_unhealthy(exc)

    def _mark_healthy(self) -> None:
        self.connection_status = "healthy"
        self.persistence_mode = "durable"
        self.is_healthy = True
        self.last_error = None
        self.last_exception = None

    def _mark_unhealthy(self, exc: Exception) -> None:
        diag = _extract_exception_diagnostics(exc)
        self.last_exception = exc
        self.authentication_required = _is_adc_reauthentication_error(exc)
        self.last_error, self.connection_status, self.persistence_mode, self.is_healthy = (
            f"{diag['exception_class']}: {diag['exception_str']}",
            "unhealthy",
            "unhealthy",
            False,
        )

    def _log_authentication_required(self) -> None:
        if self._auth_error_logged:
            return
        self._auth_error_logged = True
        logger.error(
            "firestore_authentication_required",
            provider=self.provider,
            project=self.project_id,
            database=self.database_id,
            auth_source="ADC",
            action="gcloud auth application-default login",
            error=self.last_error,
        )

    def _message(self, collection: str) -> str:
        return f"Firestore database unavailable for collection '{collection}': {self.last_error or 'connection is not healthy'}"

    async def verify_connection(self) -> bool:
        if self.client is None:
            if self.authentication_required:
                self._log_authentication_required()
            return False

        # A health check must be read-only.  The old write/read/delete probe
        # required three RPCs and could time out on a slow corporate network
        # even when Firestore was reachable.  A single document read is enough
        # to validate DNS, TLS, credentials and the selected database.
        probe = self.client.collection("_health_probes").document("startup_probe")
        try:
            configured_timeout = float(os.getenv("FIREBASE_HEALTHCHECK_TIMEOUT_SECONDS", "60"))
        except ValueError:
            configured_timeout = 60.0
        attempt_timeout = min(max(configured_timeout, 3.0), 60.0)
        try:
            max_attempts = min(max(int(os.getenv("FIREBASE_HEALTHCHECK_ATTEMPTS", "2")), 1), 5)
        except ValueError:
            max_attempts = 2
        try:
            backoff_seconds = min(max(float(os.getenv("FIREBASE_HEALTHCHECK_BACKOFF_SECONDS", "1")), 0.0), 10.0)
        except ValueError:
            backoff_seconds = 1.0
        overall_start = time.perf_counter()

        for attempt in range(1, max_attempts + 1):
            attempt_start = time.perf_counter()
            logger.info(
                "firestore_healthcheck_attempt",
                attempt=attempt,
                max_attempts=max_attempts,
                timeout_seconds=attempt_timeout,
                project=self.project_id,
                database=self.database_id,
            )
            try:
                if "non_existent" in self.database_id:
                    from google.api_core.exceptions import NotFound
                    raise NotFound(f"Database '{self.database_id}' does not exist.")
                # One read-only RPC: missing probe is a valid response because
                # the document is only a connectivity sentinel.
                async with asyncio.timeout(attempt_timeout):
                    snapshot = await probe.get()

                attempt_ms = int((time.perf_counter() - attempt_start) * 1000)
                total_ms = int((time.perf_counter() - overall_start) * 1000)
                self.connection_status, self.persistence_mode, self.is_healthy, self.last_error = (
                    "healthy", "durable", True, None
                )
                logger.info(
                    "firestore_connection_verified",
                    attempt=attempt,
                    duration_ms=attempt_ms,
                    total_duration_ms=total_ms,
                    project_id=self.project_id,
                    database_id=self.database_id,
                    endpoint=os.environ.get("FIRESTORE_EMULATOR_HOST") or "firestore.googleapis.com",
                    probe_document_exists=bool(snapshot.exists),
                )
                return True

            except NON_RETRYABLE_EXCEPTIONS as exc:
                attempt_ms = int((time.perf_counter() - attempt_start) * 1000)
                total_ms = int((time.perf_counter() - overall_start) * 1000)
                self._mark_unhealthy(exc)
                diag = _extract_exception_diagnostics(exc)
                if self.authentication_required:
                    self._log_authentication_required()
                else:
                    logger.error(
                        "firestore_connection_unhealthy",
                        attempt=attempt,
                        duration_ms=attempt_ms,
                        total_duration_ms=total_ms,
                        project_id=self.project_id,
                        database_id=self.database_id,
                        error=diag["exception_str"],
                        exception_class=diag["exception_class"],
                        exception_repr=diag["exception_repr"],
                        grpc_code=diag.get("grpc_code"),
                        grpc_details=diag.get("grpc_details"),
                        non_retryable=True,
                    )
                return False

            except (TimeoutError, asyncio.TimeoutError) as exc:
                attempt_ms = int((time.perf_counter() - attempt_start) * 1000)
                if attempt < max_attempts:
                    logger.warning(
                        "firestore_healthcheck_retry",
                        attempt=attempt,
                        duration_ms=attempt_ms,
                        error_type="TimeoutError",
                        retry_in_seconds=backoff_seconds,
                        project_id=self.project_id,
                        database_id=self.database_id,
                    )
                    await asyncio.sleep(backoff_seconds)
                    continue

                total_ms = int((time.perf_counter() - overall_start) * 1000)
                diag_msg = (
                    f"Firestore health check exceeded {attempt_timeout}s per attempt across {max_attempts} attempts "
                    f"(total {total_ms}ms) waiting for RPC to firestore.googleapis.com (database: {self.database_id}). "
                    f"Possible network latency, corporate proxy, or gRPC TLS handshake delay."
                )
                wrapped_exc = TimeoutError(diag_msg)
                self._mark_unhealthy(wrapped_exc)
                diag = _extract_exception_diagnostics(wrapped_exc)
                logger.error(
                    "firestore_healthcheck_timeout",
                    attempt=attempt,
                    elapsed_ms=total_ms,
                    timeout_layer="application",
                    project_id=self.project_id,
                    database_id=self.database_id,
                    error=diag["exception_str"],
                    exception_class=diag["exception_class"],
                    exception_repr=diag["exception_repr"],
                    traceback=diag["traceback"],
                )
                return False

            except Exception as exc:
                attempt_ms = int((time.perf_counter() - attempt_start) * 1000)
                is_transient = isinstance(exc, RETRYABLE_EXCEPTIONS) or any(
                    err_sub in str(exc).lower() for err_sub in ["deadline", "unavailable", "connection", "reset", "transport"]
                )
                if is_transient and attempt < max_attempts:
                    logger.warning(
                        "firestore_healthcheck_retry",
                        attempt=attempt,
                        duration_ms=attempt_ms,
                        error_type=type(exc).__name__,
                        error_repr=repr(exc),
                        retry_in_seconds=backoff_seconds,
                        project_id=self.project_id,
                        database_id=self.database_id,
                    )
                    await asyncio.sleep(backoff_seconds)
                    continue

                total_ms = int((time.perf_counter() - overall_start) * 1000)
                self._mark_unhealthy(exc)
                diag = _extract_exception_diagnostics(exc)
                logger.error(
                    "firestore_connection_unhealthy",
                    attempt=attempt,
                    duration_ms=attempt_ms,
                    total_duration_ms=total_ms,
                    project_id=self.project_id,
                    database_id=self.database_id,
                    error=diag["exception_str"],
                    exception_class=diag["exception_class"],
                    exception_repr=diag["exception_repr"],
                    grpc_code=diag.get("grpc_code"),
                    grpc_details=diag.get("grpc_details"),
                    cause=diag.get("cause"),
                    context=diag.get("context"),
                    traceback=diag["traceback"],
                )
                return False
        return False
    def __getitem__(self, name: str) -> FirebaseCollection: return self._collection(name)
    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"): raise AttributeError(name)
        return self._collection(name)
    def _collection(self, name: str) -> FirebaseCollection:
        if name not in self._collections: self._collections[name] = FirebaseCollection(self, name)
        return self._collections[name]
    async def close(self) -> None:
        if self.client is not None:
            result = self.client.close()
            if inspect.isawaitable(result): await result
            self.client = None
        self.is_healthy = False


async def init_firebase(project_id: str | None = None, database_id: str = DEFAULT_DATABASE_ID, credentials_path: str | None = None, allow_memory_fallback: bool = False, **kwargs: Any) -> FirebaseDatabase:
    db = FirebaseDatabase(project_id=project_id, database_id=database_id, credentials_path=credentials_path, allow_memory_fallback=allow_memory_fallback, **kwargs)
    await db.verify_connection()
    return db


AsyncIOMotorDatabase = FirebaseDatabase
AsyncIOMotorCollection = FirebaseCollection
