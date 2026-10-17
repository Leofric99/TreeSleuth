from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from treesleuth.paths import PathValidationError, ensure_within_root, validate_research_root

GEDCOM_SUFFIXES = frozenset({".ged"})
DOCUMENT_SUFFIXES = frozenset(
    {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".txt", ".md", ".markdown"}
)
EXCLUDED_DIRECTORY_NAMES = frozenset({".cache", ".tree_cache", "output"})


@dataclass(frozen=True)
class DiscoveredFile:
    path: Path
    relative_path: Path
    kind: str


@dataclass(frozen=True)
class DirectoryScan:
    root: Path
    gedcom_files: tuple[DiscoveredFile, ...]
    document_files: tuple[DiscoveredFile, ...]
    files_by_type: dict[str, int]
    errors: tuple[str, ...] = ()


def _kind_for(path: Path) -> str | None:
    suffix = path.suffix.casefold()
    if suffix in GEDCOM_SUFFIXES:
        return "gedcom"
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
        return "image"
    if suffix in {".txt", ".md", ".markdown"}:
        return "text"
    return None


def scan_directory(value: str | Path) -> DirectoryScan:
    root = validate_research_root(value)
    gedcom_files: list[DiscoveredFile] = []
    document_files: list[DiscoveredFile] = []
    counts: Counter[str] = Counter()
    errors: list[str] = []

    try:
        entries = root.rglob("*")
        for path in entries:
            try:
                relative_path = path.relative_to(root)
                if any(part.casefold() in EXCLUDED_DIRECTORY_NAMES for part in relative_path.parts):
                    continue
                resolved = ensure_within_root(root, path)
                if path.is_symlink() and path.is_dir():
                    continue
                if not resolved.is_file():
                    continue
                kind = _kind_for(path)
                if kind is None:
                    continue
                discovered = DiscoveredFile(path=resolved, relative_path=relative_path, kind=kind)
                counts[kind] += 1
                if kind == "gedcom":
                    gedcom_files.append(discovered)
                else:
                    document_files.append(discovered)
            except (OSError, RuntimeError, PathValidationError) as exc:
                errors.append(f"{path}: {exc}")
    except OSError as exc:
        errors.append(f"{root}: {exc}")

    sort_key = lambda item: str(item.relative_path).casefold()
    return DirectoryScan(
        root=root,
        gedcom_files=tuple(sorted(gedcom_files, key=sort_key)),
        document_files=tuple(sorted(document_files, key=sort_key)),
        files_by_type=dict(counts),
        errors=tuple(errors),
    )
