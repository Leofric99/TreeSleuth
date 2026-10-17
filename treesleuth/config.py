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
    vlm_host: str | None = None
    vlm_timeout_seconds: float = Field(default=600.0, gt=0)
    vlm_max_image_side: int = Field(default=1280, ge=256, le=8192)
    vlm_jpeg_quality: int = Field(default=85, ge=50, le=95)
    vlm_pdf_dpi: int = Field(default=200, ge=72, le=600)
    vlm_prompt: str | None = None
    # Model selection for two-stage pipeline
    text_llm_model: str = "mistral"
    vlm_model: str = "qwen2.5-vl:7b"
    # VRAM optimization: context window limit to prevent KV cache overflow
    vlm_ctx_window: int = Field(default=4096, ge=1024, le=32768)


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
        vlm_host=os.getenv("TREESLEUTH_VLM_HOST") or None,
        vlm_timeout_seconds=float(os.getenv("TREESLEUTH_VLM_TIMEOUT_SECONDS", "600")),
        vlm_max_image_side=int(os.getenv("TREESLEUTH_VLM_MAX_IMAGE_SIDE", "1280")),
        vlm_jpeg_quality=int(os.getenv("TREESLEUTH_VLM_JPEG_QUALITY", "85")),
        vlm_pdf_dpi=int(os.getenv("TREESLEUTH_VLM_PDF_DPI", "200")),
        vlm_prompt=os.getenv("TREESLEUTH_VLM_PROMPT") or None,
        text_llm_model=os.getenv("TREESLEUTH_TEXT_LLM_MODEL", "mistral"),
        vlm_model=os.getenv("TREESLEUTH_VLM_MODEL", "qwen2.5-vl:7b"),
        vlm_ctx_window=int(os.getenv("TREESLEUTH_VLM_CTX_WINDOW", "4096")),
    )
