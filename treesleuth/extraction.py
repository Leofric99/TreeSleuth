import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from treesleuth.discovery import DOCUMENT_SUFFIXES

logger = logging.getLogger(__name__)


class DocumentExtractionError(RuntimeError):
    """Raised when a supported source document cannot be converted to text."""


class Converter(Protocol):
    def convert(self, source: Path) -> object: ...


def _detect_accelerator() -> str:
    try:
        import torch
    except ImportError:
        return "cpu"

    try:
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except RuntimeError as exc:
        logger.warning("Hardware acceleration is unavailable; using CPU: %s", exc)
    return "cpu"


def _create_docling_converter(device: str) -> Converter:
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import (
        DocumentConverter,
        ImageFormatOption,
        PdfFormatOption,
    )

    pipeline_options = PdfPipelineOptions(
        accelerator_options=AcceleratorOptions(device=device),
        do_ocr=True,
    )
    format_options = {
        InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        InputFormat.IMAGE: ImageFormatOption(pipeline_options=pipeline_options),
    }
    return DocumentConverter(format_options=format_options)


class DoclingExtractor:
    def __init__(
        self,
        use_acceleration: bool = True,
        converter_factory: Callable[[str], Converter] = _create_docling_converter,
    ) -> None:
        self._use_acceleration = use_acceleration
        self._converter_factory = converter_factory
        self._converters: dict[str, Converter] = {}
        self._lock = threading.Lock()

    def _converter(self, device: str) -> Converter:
        if device not in self._converters:
            self._converters[device] = self._converter_factory(device)
        return self._converters[device]

    def _convert_markdown(self, source: Path, device: str) -> str:
        result = self._converter(device).convert(source)
        markdown = result.document.export_to_markdown()
        if not isinstance(markdown, str):
            raise DocumentExtractionError(f"Docling returned a non-text result for {source}")
        return markdown.strip()

    def extract_text(self, source: Path) -> str:
        suffix = source.suffix.casefold()
        if suffix not in DOCUMENT_SUFFIXES:
            raise DocumentExtractionError(f"Unsupported document format: {source}")
        if suffix in {".txt", ".md", ".markdown"}:
            try:
                text = source.read_text(encoding="utf-8", errors="replace").strip()
            except OSError as exc:
                logger.exception("Could not read text document %s", source)
                raise DocumentExtractionError(f"Unable to read text document {source}: {exc}") from exc
            if not text:
                raise DocumentExtractionError(f"No readable text was found in {source}")
            return text

        device = _detect_accelerator() if self._use_acceleration else "cpu"
        with self._lock:
            try:
                markdown = self._convert_markdown(source, device)
            except Exception as exc:
                if device == "cpu":
                    logger.exception("Docling CPU processing failed for %s", source)
                    raise DocumentExtractionError(f"Docling failed to process {source}: {exc}") from exc
                logger.warning(
                    "Docling %s processing failed for %s; retrying on CPU: %s",
                    device,
                    source,
                    exc,
                    exc_info=True,
                )
                try:
                    markdown = self._convert_markdown(source, "cpu")
                except Exception as cpu_exc:
                    logger.exception("Docling %s and CPU processing failed for %s", device, source)
                    raise DocumentExtractionError(
                        f"Docling failed on {device} and CPU for {source}: {cpu_exc}"
                    ) from cpu_exc

        if not markdown:
            raise DocumentExtractionError(f"No readable text was found in {source}")
        return markdown
