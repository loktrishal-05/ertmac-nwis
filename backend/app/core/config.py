"""Environment-based backend settings."""

from pathlib import Path

from pydantic import Field, model_validator
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
    embedding_model: str = Field(default="BAAI/bge-base-en-v1.5", validation_alias="EMBEDDING_MODEL")
    embedding_dimension: int = Field(default=768, validation_alias="EMBEDDING_DIMENSION")
    chunk_target_tokens: int = Field(default=400, validation_alias="CHUNK_TARGET_TOKENS")
    chunk_max_tokens: int = Field(default=500, validation_alias="CHUNK_MAX_TOKENS")
    chunk_overlap_tokens: int = Field(default=60, validation_alias="CHUNK_OVERLAP_TOKENS")
    data_root: Path = Path(__file__).resolve().parents[3] / "data"
    model_root: Path = Path(__file__).resolve().parents[3] / "models"
    pid_render_dpi: int = Field(default=300, ge=300, le=400, validation_alias="PID_RENDER_DPI")
    sparse_retrieval_enabled: bool = Field(default=True, validation_alias="SPARSE_RETRIEVAL_ENABLED")
    dense_top_k: int = Field(default=30, ge=1, le=100, validation_alias="DENSE_TOP_K")
    sparse_top_k: int = Field(default=30, ge=1, le=100, validation_alias="SPARSE_TOP_K")
    hybrid_fusion: str = Field(default="rrf", pattern="^rrf$", validation_alias="HYBRID_FUSION")
    reranking_enabled: bool = Field(default=True, validation_alias="RERANKING_ENABLED")
    reranker_model: str = Field(default="BAAI/bge-reranker-base", pattern="^BAAI/bge-reranker-base$", validation_alias="RERANKER_MODEL")
    rerank_top_k: int = Field(default=20, ge=1, le=100, validation_alias="RERANK_TOP_K")
    final_context_k: int = Field(default=6, ge=1, le=30, validation_alias="FINAL_CONTEXT_K")

    @model_validator(mode="after")
    def validate_pipeline(self):
        if self.embedding_model != "BAAI/bge-base-en-v1.5" or self.embedding_dimension != 768:
            raise ValueError("Phase 3A requires BAAI/bge-base-en-v1.5 with 768 dimensions")
        if not 0 <= self.chunk_overlap_tokens < 80 <= self.chunk_target_tokens <= self.chunk_max_tokens <= 500:
            raise ValueError("Require overlap < 80 <= target <= maximum <= 500")
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
