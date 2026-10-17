import hashlib
import os
from pathlib import Path


def application_data_root() -> Path:
    return Path(__file__).resolve().parent.parent / ".cache"


def research_root_key(root: Path) -> str:
    canonical_root = os.path.normcase(str(root.resolve()))
    return hashlib.sha256(canonical_root.encode("utf-8")).hexdigest()


def application_data_directory(name: str, root: Path | None = None) -> Path:
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("Application data directory name must be a single path component")
    directory = (root or application_data_root()) / name
    directory.mkdir(parents=True, exist_ok=True)
    return directory
