import hashlib
import json
import logging
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from treesleuth.app_data import application_data_directory, research_root_key
from treesleuth.analysis import AuditResponse, BiographyResponse
from treesleuth.paths import ensure_within_root, validate_research_root

logger = logging.getLogger(__name__)


class OutputWriteError(OSError):
    """Raised when application results cannot be saved safely."""


@dataclass(frozen=True)
class SavedAnalysis:
    person_id: str
    person_name: str
    biography_path: Path
    conflicts_path: Path
    analysis_path: Path
    biography: BiographyResponse
    conflicts: AuditResponse


def _safe_slug(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-")
    return slug or "person"


def _atomic_write(path: Path, content: str) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)
        temporary_path.replace(path)
    except OSError as exc:
        logger.exception("Could not write analysis result file %s", path)
        raise OutputWriteError(f"Could not save analysis output {path}: {exc}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning(
                    "Could not remove temporary analysis file %s: %s",
                    temporary_path,
                    exc,
                    exc_info=True,
                )


def save_analysis_results(
    root: Path,
    person_id: str,
    person_name: str,
    biography: BiographyResponse,
    conflicts: AuditResponse,
    *,
    app_data_root: Path | None = None,
) -> SavedAnalysis:
    selected_root = validate_research_root(root)
    cache_root = application_data_directory("results", app_data_root)
    output_directory = cache_root / research_root_key(selected_root)
    output_directory.mkdir(parents=True, exist_ok=True)
    ensure_within_root(cache_root, output_directory)

    identifier_hash = hashlib.sha256(person_id.encode("utf-8")).hexdigest()[:12]
    basename = f"{_safe_slug(person_name)}_{identifier_hash}"
    biography_path = ensure_within_root(cache_root, output_directory / f"{basename}_LifeStory.txt")
    conflicts_path = ensure_within_root(cache_root, output_directory / f"{basename}_Conflicts.json")
    analysis_path = ensure_within_root(cache_root, output_directory / f"{basename}_Analysis.json")
    analysis_document = {
        "person": {"id": person_id, "name": person_name},
        "biography": biography.model_dump(mode="json"),
        "conflicts": conflicts.model_dump(mode="json"),
    }

    try:
        _atomic_write(biography_path, biography.biography.strip() + "\n")
        _atomic_write(
            conflicts_path,
            json.dumps(conflicts.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        )
        _atomic_write(analysis_path, json.dumps(analysis_document, ensure_ascii=False, indent=2) + "\n")
    except OSError as exc:
        if isinstance(exc, OutputWriteError):
            raise
        raise OutputWriteError(f"Could not prepare analysis outputs for {person_id}: {exc}") from exc

    return SavedAnalysis(
        person_id=person_id,
        person_name=person_name,
        biography_path=biography_path,
        conflicts_path=conflicts_path,
        analysis_path=analysis_path,
        biography=biography,
        conflicts=conflicts,
    )
