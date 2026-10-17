import hashlib
import io
import logging
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Protocol

from treesleuth.config import Settings
from treesleuth.discovery import DOCUMENT_SUFFIXES

logger = logging.getLogger(__name__)

TEXT_SUFFIXES = frozenset({".txt", ".md", ".markdown"})
EXTRACTION_VERSION = "treesleuth-vlm-extraction-v2"

DEFAULT_PROMPT = (
    "You are transcribing a historical genealogical document page. Transcribe all text exactly as "
    "written, preserving original spelling, abbreviations, names, dates, punctuation and line "
    "breaks. Read handwriting carefully. Write [illegible] for words you cannot read and do not "
    "guess. Do not translate, summarise, explain or add commentary. If the page has no text, "
    "reply with nothing."
)


class DocumentExtractionError(RuntimeError):
    """Raised when a supported source document cannot be converted to text."""


class VlmClient(Protocol):
    def chat(self, **kwargs: Any) -> Any: ...


PageRenderer = Callable[[Path], Iterator[bytes]]
PageProgress = Callable[[Path, int], None]


def vlm_extraction_identity(settings: Settings, model: str) -> str:
    prompt = settings.vlm_prompt or DEFAULT_PROMPT
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
    return (
        f"{EXTRACTION_VERSION}:{model}:{prompt_hash}:"
        f"dpi{settings.vlm_pdf_dpi}:side{settings.vlm_max_image_side}"
    )


def _png_bytes(image: Any, max_side: int) -> bytes:
    image = image.convert("RGB")
    longest = max(image.size)
    if longest > max_side:
        scale = max_side / longest
        image = image.resize(
            (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _chunk_image(image: Any, grid_size: int = 2) -> list[bytes]:
    """Split image into grid of tiles, then downscale and encode each tile as PNG.
    
    Args:
        image: PIL Image object
        grid_size: split into grid_size × grid_size tiles (default 2×2 = 4 tiles)
    
    Returns:
        List of PNG-encoded tile bytes, in row-major order
    """
    from PIL import Image
    
    image = image.convert("RGB")
    w, h = image.size
    tile_w = (w + grid_size - 1) // grid_size
    tile_h = (h + grid_size - 1) // grid_size
    
    tiles = []
    for row in range(grid_size):
        for col in range(grid_size):
            left = col * tile_w
            top = row * tile_h
            right = min((col + 1) * tile_w, w)
            bottom = min((row + 1) * tile_h, h)
            
            if left < w and top < h:
                tile = image.crop((left, top, right, bottom))
                buffer = io.BytesIO()
                tile.save(buffer, format="PNG")
                tiles.append(buffer.getvalue())
    
    return tiles


def render_pages(source: Path, *, dpi: int, max_side: int) -> Iterator[bytes]:
    """Yield each page or frame of a PDF/image as PNG bytes without writing to disk."""
    from PIL import Image

    if source.suffix.casefold() == ".pdf":
        import pymupdf

        with pymupdf.open(source) as pdf:
            for page in pdf:
                pixmap = page.get_pixmap(dpi=dpi, alpha=False)
                image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                yield _png_bytes(image, max_side)
        return

    with Image.open(source) as image:
        for frame in range(getattr(image, "n_frames", 1)):
            image.seek(frame)
            yield _png_bytes(image, max_side)


class VlmExtractor:
    def __init__(
        self,
        settings: Settings,
        model: str | None,
        client: VlmClient | None = None,
        renderer: PageRenderer | None = None,
        on_page: PageProgress | None = None,
    ) -> None:
        self._settings = settings
        self.model = (model or "").strip()
        self._client = client
        self._renderer = renderer or (
            lambda source: render_pages(
                source,
                dpi=settings.vlm_pdf_dpi,
                max_side=settings.vlm_max_image_side,
            )
        )
        self._on_page = on_page
        self._prompt = settings.vlm_prompt or DEFAULT_PROMPT
        self._lock = threading.Lock()
        self._gpu_checked = False

    @property
    def identity(self) -> str:
        return vlm_extraction_identity(self._settings, self.model)

    def _vlm_client(self) -> VlmClient:
        if self._client is None:
            from ollama import Client

            self._client = Client(
                host=self._settings.vlm_host or self._settings.ollama_host,
                timeout=self._settings.vlm_timeout_seconds,
            )
        return self._client

    def _warn_if_not_on_gpu(self) -> None:
        if self._gpu_checked:
            return
        self._gpu_checked = True
        try:
            running = self._vlm_client().ps().models  # type: ignore[attr-defined]
        except Exception as exc:
            logger.debug("Could not determine Ollama GPU residency: %s", exc)
            return
        for item in running or []:
            if getattr(item, "model", None) != self.model:
                continue
            size = getattr(item, "size", 0) or 0
            size_vram = getattr(item, "size_vram", 0) or 0
            if size and size_vram < size:
                logger.warning(
                    "Ollama is not running %s fully on a GPU (%d of %d bytes in VRAM); "
                    "transcription will be slow",
                    self.model,
                    size_vram,
                    size,
                )

    def _transcribe(self, source: Path, images: list[bytes], page: int) -> str:
        """Transcribe a page from a list of image tiles (or a single-element list for whole page)."""
        all_text = []
        for idx, image in enumerate(images, start=1):
            try:
                response = self._vlm_client().chat(
                    model=self.model,
                    messages=[{"role": "user", "content": self._prompt, "images": [image]}],
                    options={"temperature": 0},
                )
                message = response["message"]
                content = message["content"]
            except Exception as exc:
                logger.exception("Vision model failed on page %d (tile %d) of %s", page, idx, source)
                raise DocumentExtractionError(
                    f"Vision model {self.model} failed on page {page} (tile {idx}) of {source}: {exc}"
                ) from exc
            if not isinstance(content, str):
                raise DocumentExtractionError(
                    f"Vision model {self.model} returned a non-text result for page {page} (tile {idx}) of {source}"
                )
            text = content.strip()
            if text:
                all_text.append(text)
        
        return " ".join(all_text) if all_text else ""

    def extract_text(self, source: Path) -> str:
        suffix = source.suffix.casefold()
        if suffix not in DOCUMENT_SUFFIXES:
            raise DocumentExtractionError(f"Unsupported document format: {source}")
        if suffix in TEXT_SUFFIXES:
            try:
                text = source.read_text(encoding="utf-8", errors="replace").strip()
            except OSError as exc:
                logger.exception("Could not read text document %s", source)
                raise DocumentExtractionError(f"Unable to read text document {source}: {exc}") from exc
            if not text:
                raise DocumentExtractionError(f"No readable text was found in {source}")
            return text

        if not self.model:
            raise DocumentExtractionError(f"A vision model must be selected to transcribe {source}")
        pages: list[str] = []
        with self._lock:
            try:
                for number, page_image_bytes in enumerate(self._renderer(source), start=1):
                    if self._on_page:
                        self._on_page(source, number)
                    
                    # Chunk the page image into tiles for faster processing
                    image_chunks = [page_image_bytes]
                    try:
                        from PIL import Image
                        page_image = Image.open(io.BytesIO(page_image_bytes))
                        w, h = page_image.size
                        
                        # Use 2x2 chunking if image is large, else send as-is
                        if w > 1920 or h > 1920:
                            image_chunks = _chunk_image(page_image, grid_size=2)
                    except Exception:
                        # If we can't parse the image (e.g., in tests with fake data),
                        # just send it as-is
                        pass
                    
                    pages.append(self._transcribe(source, image_chunks, number))
                    self._warn_if_not_on_gpu()
            except DocumentExtractionError:
                raise
            except Exception as exc:
                logger.exception("Could not render %s for transcription", source)
                raise DocumentExtractionError(f"Unable to render {source}: {exc}") from exc

        if not any(pages):
            raise DocumentExtractionError(f"No readable text was found in {source}")
        if len(pages) == 1:
            return pages[0]
        return "\n\n".join(
            f"--- Page {number} ---\n\n{text}" for number, text in enumerate(pages, start=1)
        )


async def ensure_vision_model_available(settings: Settings, model: str) -> None:
    """Raise DocumentExtractionError unless the local Ollama service has the model installed."""
    from ollama import AsyncClient

    try:
        response = await AsyncClient(
            host=settings.vlm_host or settings.ollama_host,
            timeout=settings.vlm_timeout_seconds,
        ).list()
    except Exception as exc:
        raise DocumentExtractionError(
            f"Could not reach Ollama to check vision model {model}: {exc}"
        ) from exc
    installed = {getattr(item, "model", None) for item in getattr(response, "models", [])}
    if model not in installed:
        raise DocumentExtractionError(
            f"Vision model is not installed locally: {model}. Install it with 'ollama pull {model}'"
        )
