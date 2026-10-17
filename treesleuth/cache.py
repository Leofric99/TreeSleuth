import hashlib
import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from treesleuth.app_data import application_data_directory, research_root_key
from treesleuth.paths import ensure_within_root, validate_research_root

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CachedText:
    text: str
    cache_hit: bool
    warnings: tuple[str, ...] = ()


class ExtractionCache:
    def __init__(
        self,
        root: Path,
        extractor_identity: str,
        *,
        app_data_root: Path | None = None,
    ) -> None:
        self.root = validate_research_root(root)
        if not extractor_identity.strip():
            raise ValueError("Extractor identity must be non-empty")
        self.extractor_identity = extractor_identity
        self.cache_directory = (
            application_data_directory("extraction", app_data_root) / research_root_key(self.root)
        )

    @staticmethod
    def _content_digest(source: Path) -> str:
        digest = hashlib.sha256()
        with source.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _cache_path(self, source: Path) -> Path:
        resolved_source = ensure_within_root(self.root, source)
        relative_key = str(resolved_source.relative_to(self.root))
        key = hashlib.sha256(f"{relative_key}\0{self.extractor_identity}".encode("utf-8")).hexdigest()
        return self.cache_directory / f"{key}.json"

    @staticmethod
    def _warning(message: str, *, exc_info: bool = False) -> str:
        logger.warning("%s", message, exc_info=exc_info)
        return message

    def get_or_extract(self, source: Path, extract: Callable[[Path], str]) -> CachedText:
        warnings: list[str] = []
        cache_path = self._cache_path(source)
        try:
            content_digest = self._content_digest(source)
        except OSError as exc:
            warning = self._warning(
                f"Could not read source for cache validation: {source}: {exc}",
                exc_info=True,
            )
            warnings.append(warning)
            text = extract(source)
            return CachedText(text=text, cache_hit=False, warnings=tuple(warnings))

        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if (
                isinstance(payload, dict)
                and payload.get("content_digest") == content_digest
                and payload.get("extractor_identity") == self.extractor_identity
                and isinstance(payload.get("text"), str)
                and payload["text"].strip()
            ):
                return CachedText(text=payload["text"], cache_hit=True)
            warnings.append(self._warning(f"Cache entry is stale or invalid and will be replaced: {cache_path}"))
        except FileNotFoundError:
            pass
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            warnings.append(self._warning(f"Could not read cache entry {cache_path}: {exc}", exc_info=True))

        text = extract(source)
        if not text.strip():
            return CachedText(text=text, cache_hit=False, warnings=tuple(warnings))

        temporary_path: Path | None = None
        try:
            self.cache_directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.cache_directory,
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(
                    {
                        "content_digest": content_digest,
                        "extractor_identity": self.extractor_identity,
                        "text": text,
                    },
                    temporary_file,
                    ensure_ascii=False,
                )
            temporary_path.replace(cache_path)
        except OSError as exc:
            warnings.append(self._warning(f"Could not write cache entry for {source}: {exc}", exc_info=True))
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError as exc:
                    warnings.append(
                        self._warning(
                            f"Could not clean temporary cache file {temporary_path}: {exc}",
                            exc_info=True,
                        )
                    )

        return CachedText(text=text, cache_hit=False, warnings=tuple(warnings))
