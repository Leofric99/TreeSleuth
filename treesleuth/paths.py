import os
from pathlib import Path


class PathValidationError(ValueError):
    """Raised when a user-selected or generated path is unsafe or unusable."""


def validate_research_root(value: str | Path) -> Path:
    candidate = Path(value).expanduser()
    try:
        root = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise PathValidationError(f"Research path does not exist or cannot be resolved: {candidate}") from exc

    if not root.is_dir():
        raise PathValidationError(f"Research path is not a directory: {root}")
    if not os.access(root, os.R_OK | os.X_OK):
        raise PathValidationError(f"Research directory is not readable: {root}")
    return root


def ensure_within_root(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve()
    if not resolved_candidate.is_relative_to(resolved_root):
        raise PathValidationError(f"Path is outside the selected research directory: {candidate}")
    return resolved_candidate
