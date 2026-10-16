import os
from functools import lru_cache

from pydantic import BaseModel, Field


class Settings(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_timeout_seconds: float = Field(default=120.0, gt=0)
    max_workers: int = Field(default=2, ge=1, le=8)
    max_run_events: int = Field(default=500, ge=10)
    max_active_runs: int = Field(default=2, ge=1, le=8)


@lru_cache
def get_settings() -> Settings:
    return Settings(
        host=os.getenv("TREESLEUTH_HOST", "127.0.0.1"),
        port=int(os.getenv("TREESLEUTH_PORT", "8000")),
        ollama_host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
        ollama_timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120")),
        max_workers=int(os.getenv("TREESLEUTH_MAX_WORKERS", "2")),
        max_run_events=int(os.getenv("TREESLEUTH_MAX_RUN_EVENTS", "500")),
        max_active_runs=int(os.getenv("TREESLEUTH_MAX_ACTIVE_RUNS", "2")),
    )
