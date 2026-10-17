import json
import logging
import tempfile
from pathlib import Path

from treesleuth.app_data import application_data_directory, research_root_key
from treesleuth.paths import validate_research_root

logger = logging.getLogger(__name__)


class SurnameMappingError(ValueError):
    """Raised when stored surname mappings are unreadable or cannot be saved."""


class SurnameMappingValidationError(ValueError):
    """Raised when a submitted surname display mapping is invalid."""


def normalize_surname_mappings(mappings: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for original, display in mappings.items():
        if not isinstance(original, str) or not isinstance(display, str):
            raise SurnameMappingValidationError("Surname mappings must contain text keys and values")
        key = original.strip().casefold()
        value = display.strip()
        if not key or not value:
            raise SurnameMappingValidationError("Original and display surnames must not be empty")
        if len(key) > 256 or len(value) > 256:
            raise SurnameMappingValidationError("Surname values must be 256 characters or fewer")
        if key in normalized and normalized[key] != value:
            raise SurnameMappingValidationError(f"Conflicting display surnames were provided for {original!r}")
        normalized[key] = value
    return normalized


def _mapping_path(root: Path, app_data_root: Path | None) -> Path:
    selected_root = validate_research_root(root)
    directory = application_data_directory("surnames", app_data_root)
    return directory / f"{research_root_key(selected_root)}.json"


def load_surname_mappings(root: Path, app_data_root: Path | None = None) -> dict[str, str]:
    path = _mapping_path(root, app_data_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.exception("Could not read surname mappings from %s", path)
        raise SurnameMappingError(f"Could not read surname mappings: {exc}") from exc
    if not isinstance(payload, dict):
        raise SurnameMappingError(f"Surname mapping file must contain an object: {path}")
    try:
        return normalize_surname_mappings(payload)
    except SurnameMappingValidationError as exc:
        raise SurnameMappingError(f"Surname mapping file contains invalid values: {exc}") from exc


def save_surname_mappings(
    root: Path,
    mappings: dict[str, str],
    app_data_root: Path | None = None,
) -> dict[str, str]:
    path = _mapping_path(root, app_data_root)
    normalized = normalize_surname_mappings(mappings)
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
            json.dump(normalized, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
        temporary_path.replace(path)
    except OSError as exc:
        logger.exception("Could not save surname mappings to %s", path)
        raise SurnameMappingError(f"Could not save surname mappings: {exc}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                logger.warning(
                    "Could not remove temporary surname mapping file %s",
                    temporary_path,
                    exc_info=True,
                )
    return normalized


def display_surname(surname: str, mappings: dict[str, str]) -> str:
    return mappings.get(surname.strip().casefold(), surname)
