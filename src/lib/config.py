"""Configuration module — Pydantic settings loaded from env vars or .env."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration for the orchestrator."""

    model_config = {"env_prefix": "ORCH_", "env_file": ".env", "extra": "ignore"}

    # Confidence thresholds for routing
    # Calibrated for text-embedding-3-small cosine similarity scores.
    # Hash-based test embeddings use overrides in test fixtures.
    confidence_high: float = 0.40
    confidence_moderate: float = 0.25

    # Retry limits
    retry_limit: int = 3

    # Context compaction trigger (token count estimate)
    compaction_trigger: int = 6000

    # Model configuration
    embedding_model: str = "text-embedding-3-small"
    llm_model: str = "gpt-4o"

    # Pieces directory
    pieces_dir: str = "pieces"


settings = Settings()
