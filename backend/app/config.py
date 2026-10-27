"""Validated application settings."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    debug: bool = False
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"

    # Local Firestore Emulator Host (e.g. 127.0.0.1:8080)
    firestore_emulator_host: str = Field(default="", alias="FIRESTORE_EMULATOR_HOST")

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        if self.firestore_emulator_host:
            clean = str(self.firestore_emulator_host).strip()
            if "://" in clean:
                clean = clean.split("://", 1)[1]
            os.environ["FIRESTORE_EMULATOR_HOST"] = clean

    # Controls whether a demo/seed project is inserted when the database is empty.
    # MUST remain False in production. Only set True in local dev or automated tests.
    demo_image_pipeline: bool = False
    demo_qc_bypass: bool = False

    seed_demo_data: bool = Field(default=False, alias="SEED_DEMO_DATA")

    # Firestore is the only supported production persistence provider.  The
    # ``firestore`` spelling is accepted as a legacy config alias, but is
    # normalized so diagnostics and every caller have one source of truth.
    database_provider: Literal["firebase"] = Field(default="firebase", alias="DATABASE_PROVIDER")
    firebase_project_id: str = Field(default="prod-y-in2300452", alias="FIREBASE_PROJECT_ID")
    firebase_database_id: str = Field(default="engenii-annotate-native", alias="FIREBASE_DATABASE_ID")
    firebase_credentials_path: str = Field(default="", alias="FIREBASE_CREDENTIALS_PATH")
    allow_memory_db_fallback: bool = Field(default=False, alias="ALLOW_MEMORY_DB_FALLBACK")

    @property
    def is_production(self) -> bool:
        """Determines if the application is running in production mode."""
        env = (os.environ.get("APP_ENV") or os.environ.get("ENVIRONMENT") or self.app_env or "").strip().lower()
        if env in {"production", "prod", "release"}:
            return True
        if os.environ.get("K_SERVICE"):
            return True
        return False

    @field_validator("database_provider", mode="before")
    @classmethod
    def normalize_database_provider(cls, value: str | None) -> str:
        provider = str(value or "firebase").strip().lower()
        if provider in {"firebase", "firestore"}:
            return "firebase"
        raise ValueError("DATABASE_PROVIDER must be firebase; MongoDB and fallback providers are unsupported.")

    @field_validator("firebase_database_id", mode="before")
    @classmethod
    def require_firestore_database_id(cls, value: str | None) -> str:
        database_id = str(value or "").strip()
        if not database_id or database_id == "(default)":
            # In local dev or tests with emulator, default to local-dev-db if empty
            if os.environ.get("FIRESTORE_EMULATOR_HOST") and not database_id:
                return "local-dev-db"
            raise ValueError("FIREBASE_DATABASE_ID must name an existing Firestore database.")
        return database_id

    @property
    def effective_firebase_project_id(self) -> str:
        return (
            self.firebase_project_id.strip()
            or self.google_cloud_project.strip()
            or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
            or "prod-y-in2300452"
        )

    @property
    def effective_firebase_database_id(self) -> str:
        return (
            self.firebase_database_id.strip()
            or os.getenv("FIREBASE_DATABASE_ID", "").strip()
            or "engenii-annotate-native"
        )

    storage_dir: Path = Path("./storage")

    @field_validator("storage_dir", mode="before")
    @classmethod
    def normalize_storage_dir(cls, value: str | Path | None) -> Path:
        base_dir = Path(__file__).resolve().parent.parent
        if not value:
            return (base_dir / "storage").resolve()
        p = Path(value)
        if not p.is_absolute():
            return (base_dir / p).resolve()
        return p.resolve()

    # Cloud Storage Configuration (GCS & AWS S3)
    storage_provider: Literal["local", "gcs", "s3"] = "gcs"
    gcs_bucket_name: str = ""
    gcs_project_id: str = ""
    gcs_prefix: str = ""
    aws_s3_bucket: str = ""
    aws_region: str = "us-east-1"
    aws_endpoint_url: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # Shared device / cache
    model_cache_dir: Path = Path("./model_cache")
    device: Literal["auto", "cpu", "cuda", "mps"] = "auto"
    skip_model_load: bool = False
    force_fake: bool = Field(default=False, alias="FORCE_FAKE")
    fallback_mock_models: bool = Field(default=True, alias="FALLBACK_MOCK_MODELS")
    # Route vision model calls through the MCP capability layer. Falls back to
    # direct adapter calls on any MCP failure, so this stays safe to disable.
    mcp_enabled: bool = True
    # Shared confidence thresholds
    confidence_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    detection_confidence_threshold: float = Field(default=0.25, ge=0.0, le=1.0, alias="DETECTION_CONFIDENCE_THRESHOLD")
    # Per-model defaults: keep weak candidates out of persisted AI results.
    # Lower-confidence candidates must be explicitly routed to HITL/review.
    yolo_confidence_threshold: float = Field(default=0.50, ge=0.0, le=1.0)
    dino_confidence_threshold: float = Field(default=0.20, ge=0.0, le=1.0)
    dino_box_threshold: float = Field(default=0.20, ge=0.0, le=1.0)
    dino_text_threshold: float = Field(default=0.20, ge=0.0, le=1.0)
    dino_nms_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    # Cross-model merge / giant-box filter
    merge_iou_threshold: float = Field(default=0.45, ge=0.1, le=0.95)
    # Duplicate prompt detections against already-persisted annotations.
    duplicate_iou_threshold: float = Field(default=0.85, ge=0.5, le=0.99)
    faster_rcnn_confidence_threshold: float = Field(default=0.50, ge=0.0, le=1.0)
    max_box_area_pct: float = Field(
        default=8500.0,
        ge=1000.0,
        le=10000.0,
        description="Max bbox area as percent² (100×100 full frame). Default ≈85% of image.",
    )
    review_risk_confidence_threshold: float = Field(default=0.8, ge=0.0, le=1.0)

    # YOLOv26
    yolo26_enabled: bool = True
    yolo26_model_id: str = "yolo26n.pt"
    yolo26_weights_path: Path | None = None

    # Grounding DINO
    dino_enabled: bool = True
    dino_model_id: str = "IDEA-Research/grounding-dino-tiny"

    # Faster R-CNN secondary detector
    faster_rcnn_enabled: bool = True
    faster_rcnn_model_id: str = "fasterrcnn_resnet50_fpn_v2"

    # Florence-2
    florence_enabled: bool = True
    florence_model_id: str = "microsoft/Florence-2-base"

    # SAM2
    sam2_enabled: bool = True
    sam2_model_id: str = "sam2.1_t.pt"
    sam2_weights_path: Path | None = None

    # CLIP (zero-shot region/attribute classification)
    clip_enabled: bool = True
    clip_model_id: str = "openai/clip-vit-base-patch32"

    # Deprecated single-model alias (maps to yolo26)
    model_id: str = "yolo26n.pt"
    model_weights_path: Path | None = None

    batch_size: int = Field(default=8, ge=1, le=10_000, alias="BATCH_SIZE")
    max_parallel_workers: int = Field(default=2, ge=1, le=64)
    max_concurrent_images: int = Field(default=4, ge=1, le=32, alias="MAX_CONCURRENT_IMAGES")
    max_queue_size: int = Field(default=100, ge=1, le=10_000, alias="MAX_QUEUE_SIZE")
    max_retries: int = Field(default=2, ge=0, le=10, alias="MAX_RETRIES")
    retry_count: int = Field(default=2, ge=0, le=10)
    timeout_image_seconds: int = Field(default=30, ge=1, le=3600, alias="TIMEOUT_IMAGE_SECONDS")
    timeout_model_seconds: int = Field(default=60, ge=1, le=3600, alias="TIMEOUT_MODEL_SECONDS")
    timeout_batch_seconds: int = Field(default=600, ge=1, le=86400, alias="TIMEOUT_BATCH_SECONDS")
    recover_interrupted_batches: bool = Field(default=False)
    worker_poll_interval_ms: int = Field(default=200, ge=50, le=10_000)

    max_upload_bytes: int = Field(default=100 * 1024 * 1024, ge=1024)
    max_image_upload_mb: int = Field(default=100, ge=1)
    max_video_upload_mb: int = Field(default=250, ge=1)
    max_text_upload_mb: int = Field(default=100, ge=1)
    max_document_upload_mb: int = Field(default=100, ge=1)
    allowed_image_types: str = "image/jpeg,image/png,image/webp,image/bmp,image/tiff,image/avif"

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    text_annotation_service_url: str = Field(
        default="http://127.0.0.1:8001",
        alias="TEXT_ANNOTATION_SERVICE_URL",
    )

    # Azure OpenAI agent
    azure_openai_endpoint: str | None = Field(default=None, alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: str | None = Field(default=None, alias="AZURE_OPENAI_API_KEY")
    azure_openai_deployment: str = Field(default="gpt-5.4-mini", alias="AZURE_OPENAI_DEPLOYMENT")

    # Vertex AI agent (ADC authentication ONLY)
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    google_api_key: str | None = Field(default=None, alias="GOOGLE_API_KEY")
    vertex_agent_model: str = Field(default="gemini-3.6-flash", alias="VERTEX_AGENT_MODEL")
    gemini_agent_model: str | None = Field(default=None, alias="GEMINI_AGENT_MODEL")
    google_cloud_project: str = Field(default="prod-y-in2300452", alias="GOOGLE_CLOUD_PROJECT")
    vertex_location: str = Field(default="global", alias="VERTEX_LOCATION")
    agent_enabled: bool = Field(default=True, alias="AGENT_ENABLED")
    agent_budget_usd: float = Field(default=5.0, ge=0.0, alias="AGENT_BUDGET_USD")
    agent_request_cap: int = Field(default=100, ge=0, alias="AGENT_REQUEST_CAP")
    agent_send_images: bool = Field(default=True, alias="AGENT_SEND_IMAGES")
    agent_max_images: int = Field(default=12, ge=1, le=24, alias="AGENT_MAX_IMAGES")

    # Dataset reconnaissance embeddings (local; not surfaced in product UI)
    embedding_model_id: str = "openai/clip-vit-base-patch32"
    embedding_enabled: bool = True
    recon_max_sample: int = Field(default=24, ge=4, le=200)
    recon_outlier_quota: int = Field(default=4, ge=0, le=50)

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug_flag(cls, value: object) -> bool:
        """Accept deployment-style values such as DEBUG=release."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production", "off", "0", "false", "no"}:
                return False
            if normalized in {"debug", "dev", "development", "on", "1", "true", "yes"}:
                return True
        return bool(value)

    @property
    def is_azure_agent(self) -> bool:
        return bool(self.azure_openai_endpoint and self.azure_openai_api_key)

    @property
    def effective_gemini_api_key(self) -> str | None:
        return self.gemini_api_key or self.google_api_key or None

    @property
    def effective_agent_model(self) -> str:
        if self.is_azure_agent:
            return self.azure_openai_deployment or "gpt-5.4-mini"
        return self.vertex_agent_model or self.gemini_agent_model or "gemini-3.6-flash"

    @field_validator("yolo26_model_id")
    @classmethod
    def yolo26_must_be_yolo26(cls, value: str) -> str:
        name = value.strip()
        if not name.startswith("yolo26") or not name.endswith(".pt"):
            raise ValueError(
                f"YOLO26_MODEL_ID must be a YOLOv26 weights file (yolo26*.pt); got {value!r}"
            )
        return name

    @field_validator("model_id")
    @classmethod
    def model_id_must_be_yolo26(cls, value: str) -> str:
        name = value.strip()
        if not name.startswith("yolo26") or not name.endswith(".pt"):
            raise ValueError(
                f"MODEL_ID must be a YOLOv26 weights file (yolo26*.pt); got {value!r}"
            )
        return name

    @field_validator("sam2_model_id")
    @classmethod
    def sam2_must_be_sam2(cls, value: str) -> str:
        name = value.strip()
        if not (name.startswith("sam2") and name.endswith(".pt")):
            raise ValueError(f"SAM2_MODEL_ID must be sam2*.pt; got {value!r}")
        return name

    @field_validator("vertex_agent_model", mode="before")
    @classmethod
    def validate_vertex_model(cls, value: str | None) -> str:
        if not value:
            return "gemini-3.6-flash"
        name = str(value).strip()
        if not (name.startswith("gemini-") or name.startswith("gemini")):
            raise ValueError(
                f"Agent model must be a Gemini model (e.g. 'gemini-3.6-flash', 'gemini-2.5-flash'); got {value!r}."
            )
        return name

    @field_validator("gemini_agent_model", mode="before")
    @classmethod
    def validate_legacy_gemini_model(cls, value: str | None) -> str | None:
        if not value:
            return None
        name = str(value).strip()
        if not (name.startswith("gemini-") or name.startswith("gemini")):
            raise ValueError(
                f"Agent model must be a Gemini model (e.g. 'gemini-3.6-flash', 'gemini-2.5-flash'); got {value!r}."
            )
        return name

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_content_types(self) -> set[str]:
        return {t.strip() for t in self.allowed_image_types.split(",") if t.strip()}

    def resolve_yolo26_weights(self) -> Path:
        candidates: list[Path] = []
        if self.yolo26_weights_path is not None:
            candidates.append(self.yolo26_weights_path.expanduser().resolve())
        if self.model_weights_path is not None:
            candidates.append(self.model_weights_path.expanduser().resolve())

        # Check local checkout next to cwd or backend package root
        candidates.append((Path.cwd() / self.yolo26_model_id).expanduser().resolve())
        candidates.append((self.backend_root / self.yolo26_model_id).expanduser().resolve())
        candidates.append((self.model_cache_dir / self.yolo26_model_id).expanduser().resolve())

        for candidate in candidates:
            if candidate.is_file():
                return candidate

        return (self.model_cache_dir / self.yolo26_model_id).expanduser().resolve()

    def resolve_weights_path(self) -> Path:
        """Backward-compatible alias."""
        return self.resolve_yolo26_weights()

    def resolve_sam2_weights(self) -> Path:
        if self.sam2_weights_path is not None:
            return self.sam2_weights_path.expanduser().resolve()
        cached = (self.model_cache_dir / self.sam2_model_id).expanduser().resolve()
        if cached.exists():
            return cached
        # Local checkout often keeps weights next to the backend package root.
        sibling = (Path.cwd() / self.sam2_model_id).expanduser().resolve()
        if sibling.exists():
            return sibling
        return cached

    @property
    def backend_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    def ensure_runtime_dirs(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.model_cache_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
