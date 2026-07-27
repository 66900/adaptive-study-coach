#!/usr/bin/env python3
"""Fail-closed path confinement helpers shared by the study and OCR managers."""

from __future__ import annotations

from pathlib import Path


class PathBoundaryError(ValueError):
    """Raised when a path resolves outside its allowed root."""


def resolve_inside(
    root: Path,
    candidate: str | Path,
    *,
    must_exist: bool,
    allow_root: bool = False,
    label: str = "path",
) -> Path:
    """Resolve symlinks/junctions and require the result to remain under root."""
    try:
        resolved_root = Path(root).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise PathBoundaryError(f"{label} root is unavailable: {root}") from exc

    raw_candidate = Path(candidate)
    if not raw_candidate.is_absolute():
        raw_candidate = resolved_root / raw_candidate
    try:
        resolved_candidate = raw_candidate.resolve(strict=must_exist)
    except (OSError, RuntimeError) as exc:
        raise PathBoundaryError(f"{label} cannot be resolved: {raw_candidate}") from exc

    if resolved_candidate == resolved_root and not allow_root:
        raise PathBoundaryError(f"{label} must be a child of {resolved_root}")
    if not resolved_candidate.is_relative_to(resolved_root):
        raise PathBoundaryError(
            f"{label} escapes the allowed root {resolved_root}: {resolved_candidate}"
        )
    return resolved_candidate
