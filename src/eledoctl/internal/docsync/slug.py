"""Slug generation helpers for documentation synchronization."""

from __future__ import annotations

from pathlib import Path


def build_slug(path: Path, *, docs_root: Path) -> str:
    """Build CMS slug from a documentation file path.

    Example:
        docs/product/template-editor.md -> /product/template-editor
    """
    relative = path.relative_to(docs_root)
    without_suffix = relative.with_suffix("")

    parts = list(without_suffix.parts)
    if parts[-1] == "index":
        parts = parts[:-1]

    return "/" + "/".join(parts)
