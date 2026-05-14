"""Markdown transformation utilities for Git-to-CMS synchronization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import frontmatter


@dataclass(frozen=True)
class GitDocument:
    """Parsed Git document content."""

    content: str
    frontmatter: dict[str, Any] = field(default_factory=dict)


def parse_git_document(raw_markdown: str) -> GitDocument:
    """Strip and preserve frontmatter from a Git Markdown document."""
    post = frontmatter.loads(raw_markdown)
    return GitDocument(content=post.content, frontmatter=dict(post.metadata))
