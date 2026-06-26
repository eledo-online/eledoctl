from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pyeledo.exceptions import EledoApiError, EledoInvalidResponseError
from pyeledo.internal.cms import CmsClient

_MARKDOWN_REFERENCE_RE = re.compile(
    r"(?P<image>!)?"
    r"\[(?P<label>(?:\\.|[^]\\])*)]"
    r"\((?P<url>[^)\n]+)\)"
    r"(?P<article_id_suffix>\{[^{}\s]+})?"
)


@dataclass(frozen=True, slots=True)
class CmsValidationWarning:
    target_path: str
    code: str
    message: str
    label: str | None = None
    url: str | None = None


@dataclass(frozen=True, slots=True)
class CmsValidationResult:
    checked_articles: int
    warnings: tuple[CmsValidationWarning, ...]

    @property
    def warning_count(self) -> int:
        return len(self.warnings)


@dataclass(frozen=True, slots=True)
class _MarkdownReference:
    kind: str
    label: str
    url: str


async def validate_cms_tree(
    *,
    cms: CmsClient,
    remote_path: str,
) -> CmsValidationResult:
    """Validate CMS articles for suspicious leftover Docusaurus references."""
    target_segments = _cms_path_segments(remote_path)

    checked_articles, warnings = await _validate_cms_subtree(
        cms=cms,
        target_segments=target_segments,
    )

    return CmsValidationResult(
        checked_articles=checked_articles,
        warnings=warnings,
    )


def validate_cms_markdown(
    *,
    target_segments: tuple[str, ...],
    markdown: str | None,
) -> tuple[CmsValidationWarning, ...]:
    """Validate one CMS markdown document for suspicious references."""
    if markdown is None or markdown == "":
        return ()

    warnings: list[CmsValidationWarning] = []

    for reference in _extract_markdown_references(markdown):
        warnings.extend(
            _validate_markdown_reference(
                target_segments=target_segments,
                reference=reference,
            )
        )

    return tuple(warnings)


def write_validation_log(
    *,
    path: Path,
    result: CmsValidationResult,
) -> None:
    """Write CMS validation warnings as JSON Lines."""
    with path.open("w", encoding="utf-8") as file:
        for warning in result.warnings:
            file.write(json.dumps(asdict(warning), ensure_ascii=False, sort_keys=True))
            file.write("\n")


async def _validate_cms_subtree(
    *,
    cms: CmsClient,
    target_segments: tuple[str, ...],
) -> tuple[int, tuple[CmsValidationWarning, ...]]:
    """Validate one CMS article and recurse into its children."""
    try:
        response = await cms.retrieve_article(target_segments)
    except (EledoApiError, EledoInvalidResponseError) as exc:
        return (
            0,
            (
                CmsValidationWarning(
                    target_path=_target_path(target_segments),
                    code="cms_article_read_warning",
                    message=f"CMS article could not be read during validation: {exc}",
                ),
            ),
        )

    warnings = list(
        validate_cms_markdown(
            target_segments=target_segments,
            markdown=response.article.markdown,
        )
    )
    checked_articles = 1

    for child in response.children:
        child_checked_articles, child_warnings = await _validate_cms_subtree(
            cms=cms,
            target_segments=(*target_segments, child.slug),
        )

        checked_articles += child_checked_articles
        warnings.extend(child_warnings)

    return checked_articles, tuple(warnings)


def _extract_markdown_references(content: str) -> tuple[_MarkdownReference, ...]:
    """Extract Markdown links and images from content."""
    references: list[_MarkdownReference] = []

    for match in _MARKDOWN_REFERENCE_RE.finditer(content):
        references.append(
            _MarkdownReference(
                kind="image" if match.group("image") else "link",
                label=match.group("label"),
                url=match.group("url"),
            )
        )

    return tuple(references)


def _validate_markdown_reference(
    *,
    target_segments: tuple[str, ...],
    reference: _MarkdownReference,
) -> tuple[CmsValidationWarning, ...]:
    """Validate one Markdown reference."""
    target_path = _target_path(target_segments)

    if reference.kind == "link" and _is_source_markdown_link(reference.url):
        return (
            CmsValidationWarning(
                target_path=target_path,
                code="cms_markdown_source_link",
                message="CMS article contains a Markdown link that still points to a source .md/.mdx file.",
                label=reference.label,
                url=reference.url,
            ),
        )

    if reference.kind == "link" and _is_docusaurus_asset_link(reference.url):
        return (
            CmsValidationWarning(
                target_path=target_path,
                code="cms_docusaurus_asset_link",
                message="CMS article contains a Docusaurus asset link.",
                label=reference.label,
                url=reference.url,
            ),
        )

    if reference.kind == "image" and _is_docusaurus_image_link(reference.url):
        return (
            CmsValidationWarning(
                target_path=target_path,
                code="cms_docusaurus_image_link",
                message="CMS article contains a Docusaurus image URL.",
                label=reference.label,
                url=reference.url,
            ),
        )

    return ()


def _is_source_markdown_link(url: str) -> bool:
    """Return whether a URL still points to a source Markdown/MDX file."""
    path = _url_path(url).lower()
    return path.endswith(".md") or path.endswith(".mdx")


def _is_docusaurus_asset_link(url: str) -> bool:
    """Return whether a URL looks like a Docusaurus static asset link."""
    path = _url_path(url)
    return path.startswith("/assets/") and _has_file_extension(path)


def _is_docusaurus_image_link(url: str) -> bool:
    """Return whether an image URL looks like a Docusaurus image asset."""
    path = _url_path(url)
    return path.startswith("/img/") and _has_file_extension(path)


def _url_path(url: str) -> str:
    """Return URL without query string or fragment."""
    return url.split("#", 1)[0].split("?", 1)[0]


def _has_file_extension(url: str) -> bool:
    """Return whether URL path appears to point to a file."""
    filename = _url_path(url).rsplit("/", 1)[-1]

    if filename in {"", ".", ".."}:
        return False

    return "." in filename and not filename.startswith(".") and not filename.endswith(".")


def _cms_path_segments(path: str) -> tuple[str, ...]:
    """Split a CMS path such as /documentation/api into path segments."""
    return tuple(part for part in path.strip("/").split("/") if part)


def _target_path(target_segments: Sequence[str]) -> str:
    """Format CMS target path."""
    return "/" + "/".join(target_segments)


def validation_warning_to_record(warning: CmsValidationWarning) -> dict[str, Any]:
    """Convert validation warning to a JSON-serializable record."""
    return asdict(warning)
