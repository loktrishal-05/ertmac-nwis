"""Environment-based backend settings."""

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@127.0.0.1:5432/sovereign_workbench",
        validation_alias="DATABASE_URL",
        repr=False,
    )

    database_connect_timeout: int = Field(default=5, ge=1, le=30)
    qdrant_url: str = Field(default="http://127.0.0.1:6333", validation_alias="QDRANT_URL")
    qdrant_collection: str = Field(default="knowledge_chunks_v1", validation_alias="QDRANT_COLLECTION")
    qdrant_api_key: str | None = Field(default=None, validation_alias="QDRANT_API_KEY", repr=False)
    # Public synthetic-data demo on managed cloud services (Vercel + Neon + Qdrant Cloud). Off for every real deployment.
    hosted_demo: bool = Field(default=False, validation_alias="WORKBENCH_HOSTED_DEMO")
    nwis_only: bool = Field(default=False, validation_alias="WORKBENCH_NWIS_ONLY")
    # "onnx" runs the same BGE models as int8 ONNX (no torch), for small serverless runtimes.
    retrieval_runtime: Literal["torch", "onnx"] = Field(default="torch", validation_alias="RETRIEVAL_RUNTIME")

    @field_validator("qdrant_url", "qdrant_api_key", mode="before")
    @classmethod
    def strip_pasted_whitespace(cls, value):
        # Dashboard-pasted secrets often carry a trailing newline, which is an illegal HTTP header value.
        return value.strip() if isinstance(value, str) else value
    embedding_model: str = Field(default="BAAI/bge-base-en-v1.5", validation_alias="EMBEDDING_MODEL")
    embedding_dimension: int = Field(default=768, validation_alias="EMBEDDING_DIMENSION")
    chunk_target_tokens: int = Field(default=400, validation_alias="CHUNK_TARGET_TOKENS")
    chunk_max_tokens: int = Field(default=500, validation_alias="CHUNK_MAX_TOKENS")
    chunk_overlap_tokens: int = Field(default=60, validation_alias="CHUNK_OVERLAP_TOKENS")
    data_root: Path = Path(__file__).resolve().parents[3] / "data"
    model_root: Path = Path(__file__).resolve().parents[3] / "models"
    pid_vision_enabled: bool = Field(default=False, validation_alias="PID_VISION_ENABLED")
    pid_vision_model: str = Field(default="qwen3.5:9b", validation_alias="PID_VISION_MODEL")
    pid_vision_timeout_seconds: float = Field(default=60, gt=0, le=600, validation_alias="PID_VISION_TIMEOUT_SECONDS")
    pid_render_dpi: int = Field(default=300, ge=300, le=400, validation_alias="PID_RENDER_DPI")
    sparse_retrieval_enabled: bool = Field(default=True, validation_alias="SPARSE_RETRIEVAL_ENABLED")
    dense_top_k: int = Field(default=30, ge=1, le=100, validation_alias="DENSE_TOP_K")
    sparse_top_k: int = Field(default=30, ge=1, le=100, validation_alias="SPARSE_TOP_K")
    hybrid_fusion: str = Field(default="rrf", pattern="^rrf$", validation_alias="HYBRID_FUSION")
    reranking_enabled: bool = Field(default=True, validation_alias="RERANKING_ENABLED")
    reranker_model: str = Field(default="BAAI/bge-reranker-base", pattern="^BAAI/bge-reranker-base$", validation_alias="RERANKER_MODEL")
    rerank_top_k: int = Field(default=20, ge=1, le=100, validation_alias="RERANK_TOP_K")
    final_context_k: int = Field(default=6, ge=1, le=30, validation_alias="FINAL_CONTEXT_K")
    structured_csv_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1, validation_alias="STRUCTURED_CSV_MAX_BYTES")
    structured_csv_max_rows: int = Field(default=50_000, ge=1, validation_alias="STRUCTURED_CSV_MAX_ROWS")
    structured_query_max_limit: int = Field(default=2000, ge=1, validation_alias="STRUCTURED_QUERY_MAX_LIMIT")

    model_runtime: Literal["ollama", "vllm"] = Field(default="ollama", validation_alias="MODEL_RUNTIME")
    model_base_url: str = Field(default="http://127.0.0.1:11434", validation_alias="MODEL_BASE_URL")
    # No default: a guessed model tag would silently benchmark the wrong model.
    model_name: str = Field(default="", validation_alias="MODEL_NAME")
    model_allowed_hosts: str = Field(
        default="127.0.0.1,localhost,::1,ollama,vllm,model-runtime", validation_alias="MODEL_ALLOWED_HOSTS",
    )
    model_connect_timeout_seconds: float = Field(default=5, gt=0, validation_alias="MODEL_CONNECT_TIMEOUT_SECONDS")
    model_timeout_seconds: float = Field(default=120, gt=0, validation_alias="MODEL_TIMEOUT_SECONDS")
    model_first_load_timeout_seconds: float = Field(default=600, gt=0, validation_alias="MODEL_FIRST_LOAD_TIMEOUT_SECONDS")
    model_max_retries: int = Field(default=2, ge=0, le=10, validation_alias="MODEL_MAX_RETRIES")
    model_temperature: float = Field(default=0.0, ge=0, le=2, validation_alias="MODEL_TEMPERATURE")
    model_seed: int = Field(default=42, validation_alias="MODEL_SEED")
    model_context_window: int = Field(default=8192, ge=1, validation_alias="MODEL_CONTEXT_WINDOW")
    model_max_output_tokens: int = Field(default=1024, ge=1, validation_alias="MODEL_MAX_OUTPUT_TOKENS")
    model_keep_alive: str = Field(default="30m", validation_alias="MODEL_KEEP_ALIVE")
    model_structured_repair_attempts: int = Field(default=1, ge=0, le=3, validation_alias="MODEL_STRUCTURED_REPAIR_ATTEMPTS")
    fast_model: Literal["qwen3.5:4b"] = Field(default="qwen3.5:4b", validation_alias="FAST_MODEL")
    primary_model: Literal["qwen3.5:9b"] = Field(default="qwen3.5:9b", validation_alias="PRIMARY_MODEL")
    system1_enabled: bool = Field(default=False, validation_alias="SYSTEM1_ENABLED")
    system1_model: str = Field(default="qwen3.5:4b", validation_alias="SYSTEM1_MODEL")
    system1_timeout_seconds: float = Field(default=15, gt=0, le=120, validation_alias="SYSTEM1_TIMEOUT_SECONDS")
    model_log_prompts: bool = Field(default=False, validation_alias="MODEL_LOG_PROMPTS")

    # No configured default anomaly threshold, equipment tag, or route: every
    # one of those must arrive from the caller or from cited evidence.
    agent_router_min_confidence: float = Field(default=0.5, ge=0, le=1, validation_alias="AGENT_ROUTER_MIN_CONFIDENCE")
    agent_tool_max_window_days: int = Field(default=90, ge=1, le=3650, validation_alias="AGENT_TOOL_MAX_WINDOW_DAYS")
    agent_max_steps: int = Field(default=12, ge=1, le=100, validation_alias="AGENT_MAX_STEPS")
    agent_trace_enabled: bool = Field(default=True, validation_alias="AGENT_TRACE_ENABLED")
    agent_trace_store_query: bool = Field(default=True, validation_alias="AGENT_TRACE_STORE_QUERY")
    agent_run_timeout_seconds: float = Field(default=300, gt=0, validation_alias="AGENT_RUN_TIMEOUT_SECONDS")
    # Phase 3B2 found no calibrated rejection threshold (docs/phase3b2-validation.md);
    # this score is whatever `RetrievedChunk.score` reports -- a raw cross-encoder
    # logit under the default hybrid_rerank strategy (unbounded, positive-leaning for
    # relevant pairs), or an RRF fusion score otherwise. 0.0 is a conservative,
    # provisional default: see docs/phase4-decisions.md D-009.
    knowledge_relevance_floor: float = Field(
        default=0.0,
        validation_alias=AliasChoices("WORKBENCH_KNOWLEDGE_RELEVANCE_FLOOR", "KNOWLEDGE_RELEVANCE_FLOOR"),
    )

    # Phase 5B local authentication. No hosted identity, no client-trusted header.
    session_cookie_name: str = Field(default="workbench_session", validation_alias="SESSION_COOKIE_NAME")
    session_ttl_seconds: float = Field(default=8 * 3600, gt=0, validation_alias="SESSION_TTL_SECONDS")
    # True requires HTTPS (browsers drop Secure cookies over plain http). Local
    # dev over http needs this False; set True behind TLS in any real deployment.
    session_cookie_secure: bool = Field(default=False, validation_alias="SESSION_COOKIE_SECURE")
    stt_url: str = ""
    tts_url: str = ""
    speech_timeout_seconds: float = Field(default=30, gt=0, le=120)
    # Word confidence below this marks a technical identifier for human correction.
    stt_identifier_min_confidence: float = Field(default=0.85, ge=0, le=1)
    # PUBLIC_EXTERNAL_OPTIONAL resource: off by default and never eligible for confidential data.
    bhashini_enabled: bool = False
    deployment_mode: Literal["development", "confidential", "public"] = "development"
    signup_mode: Literal["disabled", "approval", "open"] = "approval"
    auth_secret: str = Field(default="", repr=False)
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_sender: str = ""
    smtp_username: str = Field(default="", repr=False)
    smtp_password: str = Field(default="", repr=False)
    smtp_tls: Literal["starttls", "tls", "none"] = "starttls"
    google_enabled: bool = False
    google_client_id: str = ""
    google_client_secret: str = Field(default="", repr=False)
    google_callback_url: str = ""
    auth_frontend_origin: str = ""
    government_resources_enabled: bool = False
    government_resource_registry: str = ""
    release_min_free_gib: int = Field(default=10, ge=1)
    release_model_digests: dict[str, str] = Field(default_factory=dict)
    # Operator-reviewed JSON registry of downloadable language resources (e.g. from AIKosh).
    language_resource_registry: str = ""
    automation_secret: str = Field(default="", repr=False)
    automation_user_id: str = ""
    # Provisional operator-configurable default, not an MRPL-approved policy
    # (see docs/phase5b.md): how long an APPROVED decision stays valid for
    # release before it is treated as EXPIRED.
    approval_validity_seconds: float = Field(default=24 * 3600, gt=0, validation_alias="APPROVAL_VALIDITY_SECONDS")

    @property
    def model_allowed_hosts_set(self) -> set[str]:
        return {host.strip().lower() for host in self.model_allowed_hosts.split(",") if host.strip()}

    @model_validator(mode="after")
    def validate_pipeline(self):
        if self.deployment_mode == "confidential" and self.signup_mode == "open":
            raise ValueError("Confidential deployments cannot use open signup")
        if self.auth_secret and len(self.auth_secret.encode()) < 32:
            raise ValueError("Authentication secret requires at least 32 bytes")
        if self.smtp_host:
            from app.core.locality import classify_host
            if self.deployment_mode == "confidential" and classify_host(self.smtp_host) not in {"local", "private"}:
                raise ValueError("Confidential SMTP requires a private relay")
            if self.smtp_tls == "none" and not (self.deployment_mode == "development" and classify_host(self.smtp_host) == "local"):
                raise ValueError("SMTP requires verified TLS outside development loopback")
        if self.embedding_model != "BAAI/bge-base-en-v1.5" or self.embedding_dimension != 768:
            raise ValueError("Phase 3A requires BAAI/bge-base-en-v1.5 with 768 dimensions")
        if not 0 <= self.chunk_overlap_tokens < 80 <= self.chunk_target_tokens <= self.chunk_max_tokens <= 500:
            raise ValueError("Require overlap < 80 <= target <= maximum <= 500")
        return self

    @model_validator(mode="after")
    def validate_model_gateway(self):
        from app.services.model_gateway.errors import ModelConfigurationError
        from app.services.model_gateway.registry import validate_model_url, validate_model_name
        if not self.model_name.strip():
            raise ModelConfigurationError(
                "MODEL_NAME is required and has no default. Run 'ollama list' to see installed "
                "tags, then set MODEL_NAME in the root .env to one of them."
            )
        validate_model_url(self.model_base_url, self.model_allowed_hosts_set)
        validate_model_name(self.model_name)
        from app.core.locality import classify_database, classify_http_url, local_filesystem
        if self.hosted_demo and self.deployment_mode != 'public':
            raise ValueError('Hosted demo mode is only allowed for public synthetic-data deployments')
        if not self.hosted_demo and (classify_database(self.database_url) == 'invalid' or classify_http_url(self.qdrant_url) == 'invalid'):
            raise ValueError('PostgreSQL and Qdrant must use local/private on-premise endpoints')
        if not local_filesystem(self.data_root) or not local_filesystem(self.model_root):
            raise ValueError('Data and model roots must be local filesystem paths')
        return self

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        env_prefix="WORKBENCH_",
        extra="ignore",
    )

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


settings = Settings()
