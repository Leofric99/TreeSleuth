"""
Hybrid VLM Extractor - integrates hybrid OCR/HTR+VLM into existing extraction pipeline.

Wraps hybrid_extraction.py functions to work as a drop-in replacement for VlmExtractor.extract_text().
"""

import logging
import time
from pathlib import Path
from typing import Any, Optional

from treesleuth.config import Settings
from treesleuth.hybrid_extraction import (
    HybridExtractionResult,
    run_hybrid_extraction_pipeline,
)

logger = logging.getLogger(__name__)


class HybridVlmExtractor:
    """
    Drop-in replacement for VlmExtractor using hybrid architecture.

    Combines:
    - Row detection (OpenCV/Pillow)
    - HTR model (microsoft/trocr-large-handwritten)
    - VLM refinement (Qwen2.5-VL)

    Designed to prevent hallucination loops and text dropping on dense historical documents.
    """

    def __init__(
        self,
        settings: Settings,
        vlm_model: str | None = None,
        htr_model: str = "microsoft/trocr-large-handwritten",
        device: str = "cuda",
        target_schema: Optional[dict] = None,
        client: Optional[Any] = None,
    ) -> None:
        """
        Initialize hybrid extractor.

        Args:
            settings: App settings
            vlm_model: VLM model name (e.g., "qwen2.5vl")
            htr_model: HTR model name from Hugging Face
            device: "cuda" or "cpu"
            target_schema: Column schema for structured extraction (optional)
                          e.g., {"Name": str, "Age": int, "Occupation": str, ...}
            client: Pre-configured Ollama/OpenRouter client (optional)
        """
        self.settings = settings
        self.vlm_model = (vlm_model or "").strip()
        self.htr_model = htr_model
        self.device = device
        self.target_schema = target_schema
        self._client = client
        self._prompt = settings.vlm_prompt or ""  # Not used in hybrid mode but kept for compat

    def _vlm_client(self) -> Any:
        """Get or create Ollama client."""
        if self._client is None:
            from ollama import Client

            self._client = Client(
                host=self.settings.vlm_host or self.settings.ollama_host,
                timeout=self.settings.vlm_timeout_seconds,
            )
        return self._client

    def extract_text(self, source: Path) -> str:
        """
        Extract text using hybrid pipeline.

        Args:
            source: Path to image or PDF

        Returns:
            Full-page text transcription
        """
        suffix = source.suffix.casefold()

        if suffix == ".pdf":
            # For PDFs, extract each page and process separately
            return self._extract_pdf_hybrid(source)
        elif suffix in {".jpg", ".jpeg", ".png", ".gif"}:
            # Single image - process directly
            return self._extract_image_hybrid(source)
        else:
            raise ValueError(f"Unsupported format: {suffix}")

    def _extract_image_hybrid(self, image_path: Path) -> str:
        """Process single image through hybrid pipeline."""
        logger.info(f"Hybrid extraction: {image_path.name}")
        start = time.time()

        try:
            result = run_hybrid_extraction_pipeline(
                image_path,
                target_schema=self.target_schema,
                vlm_client=self._vlm_client(),
                vlm_model=self.vlm_model,
                htr_model=self.htr_model,
                device=self.device,
                row_detection_threshold=200,
                min_row_height=20,
            )

            elapsed = time.time() - start
            logger.info(
                f"Hybrid extraction complete: {image_path.name} in {elapsed:.2f}s "
                f"({len(result.rows)} rows, {len(result.raw_full_page_text)} chars)"
            )

            # Return raw transcription for caching compatibility
            return result.raw_full_page_text

        except Exception as exc:
            logger.exception(f"Hybrid extraction failed for {image_path}")
            raise RuntimeError(f"Hybrid extraction failed: {exc}") from exc

    def _extract_pdf_hybrid(self, pdf_path: Path) -> str:
        """Extract PDF by processing each page individually."""
        import tempfile
        from pathlib import Path

        from PIL import Image

        logger.info(f"Hybrid PDF extraction: {pdf_path.name}")

        try:
            import pymupdf
        except ImportError:
            logger.error("pymupdf not installed; cannot extract PDF. Install with: pip install pymupdf")
            raise

        pages_text = []

        with pymupdf.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf, start=1):
                logger.info(f"Processing PDF page {page_num} of {len(pdf)}")

                # Render page to image
                pixmap = page.get_pixmap(dpi=self.settings.vlm_pdf_dpi, alpha=False)
                image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)

                # Process through hybrid pipeline
                try:
                    result = run_hybrid_extraction_pipeline(
                        image_path=None,  # We'll pass the PIL image directly instead
                        target_schema=self.target_schema,
                        vlm_client=self._vlm_client(),
                        vlm_model=self.vlm_model,
                        htr_model=self.htr_model,
                        device=self.device,
                    )
                    pages_text.append(result.raw_full_page_text)
                except Exception as exc:
                    logger.exception(f"Hybrid extraction failed for PDF page {page_num}")
                    pages_text.append(f"[PAGE {page_num} EXTRACTION FAILED: {exc}]")

        # Combine pages
        full_text = "\n\n".join(
            f"--- Page {num} ---\n\n{text}" for num, text in enumerate(pages_text, start=1)
        )
        return full_text

    @property
    def identity(self) -> str:
        """Cache identity string for this extractor configuration."""
        return f"treesleuth-hybrid-extraction-v1:{self.vlm_model}:{self.htr_model}"


def create_hybrid_extractor(
    settings: Settings,
    vlm_model: str | None = None,
    htr_model: str = "microsoft/trocr-large-handwritten",
    device: str = "cuda",
    target_schema: Optional[dict] = None,
) -> HybridVlmExtractor:
    """
    Factory function to create a hybrid extractor.

    Usage:
        ```python
        from treesleuth.config import get_settings
        from treesleuth.hybrid_vlm_extractor import create_hybrid_extractor

        settings = get_settings()
        extractor = create_hybrid_extractor(
            settings,
            vlm_model="qwen2.5vl",
            target_schema={
                "Name": str,
                "Age": int,
                "Occupation": str,
                "Birthplace": str,
            }
        )
        text = extractor.extract_text(Path("document.jpg"))
        ```
    """
    return HybridVlmExtractor(
        settings,
        vlm_model=vlm_model,
        htr_model=htr_model,
        device=device,
        target_schema=target_schema,
    )
