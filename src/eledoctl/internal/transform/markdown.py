"""Markdown transformation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class GitDocument:
    """Parsed Git document with frontmatter separated from body."""

    frontmatter: dict[str, Any]
    content: str


def parse_git_document(text: str) -> GitDocument:
    """Parse a Markdown document and strip simple YAML frontmatter.

    This intentionally avoids depending on a full YAML parser in the scaffold.
    Complex frontmatter support can be added later if needed.
    """
    if not text.startswith("---\n"):
        return GitDocument(frontmatter={}, content=text.strip())

    marker = "\n---\n"
    end = text.find(marker, 4)
    if end == -1:
        return GitDocument(frontmatter={}, content=text.strip())

    raw_frontmatter = text[4:end]
    body = text[end + len(marker) :]
    frontmatter: dict[str, Any] = {}
    for line in raw_frontmatter.splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip().strip('"\'')
    return GitDocument(frontmatter=frontmatter, content=body.strip())
