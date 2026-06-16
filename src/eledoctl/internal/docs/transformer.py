"""MDX to Eledo CMS Markdown transformer."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeGuard

import yaml

__all__ = [
    "Frontmatter",
    "FrontmatterValue",
    "TransformMessage",
    "TransformMessageLevel",
    "TransformOptions",
    "TransformResult",
    "TransformStatus",
    "transform_document",
]

type FrontmatterValue = None | bool | int | float | str | list["FrontmatterValue"] | dict[str, "FrontmatterValue"]
type Frontmatter = dict[str, FrontmatterValue]

_ADMONITION_START_RE = re.compile(r"^:::(?P<kind>[a-zA-Z]+)(?:\s+(?P<title>.*))?\s*$")
_ADMONITION_CLOSE_RE = re.compile(r"^:::\s*$")
_IMPORT_LINE_RE = re.compile(r"^\s*import\s+.+$")
_UNSUPPORTED_JSX_LINE_RE = re.compile(r"^\s*</?(?P<component>[A-Z][A-Za-z0-9_.]*)(?:\s+[^>]*)?/?>\s*$")
_SUPPORTED_JSX_COMPONENTS = {"ImageWithCaption"}
_IMAGE_WITH_CAPTION_RE = re.compile(
    r"<ImageWithCaption\b(?P<attrs>[\s\S]*?)/>",
    re.MULTILINE,
)

_JSX_ATTRIBUTE_RE = re.compile(
    r"""(?P<name>[A-Za-z_:][A-Za-z0-9_:.-]*)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    re.DOTALL,
)

_MARKDOWN_URL_RE = re.compile(r"(?P<image>!)?\[(?P<label>(?:\\.|[^\]\\])*)\]\((?P<url>[^)\n]+)\)")

type _MarkdownReferenceKey = tuple[str, str]

_ADMONITION_KINDS = {
    "caution",
    "danger",
    "info",
    "important",
    "note",
    "tip",
    "warning",
}


class TransformStatus(StrEnum):
    """Overall transformation status."""

    SUCCESS = "success"
    WARNING = "warning"
    FAILURE = "failure"


class TransformMessageLevel(StrEnum):
    """Transformation message level."""

    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class TransformMessage:
    """A warning or error produced during transformation."""

    level: TransformMessageLevel
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class TransformOptions:
    """Options controlling which transformation stages are applied."""

    normalize_line_endings: bool = True
    strip_frontmatter: bool = True
    remove_imports: bool = True
    convert_admonitions: bool = True
    convert_supported_images: bool = True
    remove_unsupported_jsx: bool = True
    patch_links_from_reference: bool = True
    patch_images_from_reference: bool = True


@dataclass(frozen=True, slots=True)
class TransformResult:
    """Result of transforming one source document."""

    content: str
    status: TransformStatus
    metadata: Mapping[str, FrontmatterValue] = field(default_factory=dict)
    messages: tuple[TransformMessage, ...] = ()


@dataclass(frozen=True, slots=True)
class _MarkdownReference:
    kind: str
    label: str
    url: str

    @property
    def key(self) -> _MarkdownReferenceKey:
        return self.kind, self.label


def transform_document(
    *,
    source_doc: str,
    reference_doc: str | None = None,
    options: TransformOptions = TransformOptions(),  # noqa: B008
) -> TransformResult:
    """Transform MDX-like source content into Eledo CMS Markdown."""
    messages: list[TransformMessage] = []
    metadata: Frontmatter = {}
    content = source_doc

    if options.normalize_line_endings:
        content = _normalize_line_endings(content)

    content, metadata = _extract_frontmatter(
        content,
        messages,
        strip=options.strip_frontmatter,
    )

    if options.remove_imports:
        content = _remove_imports(content)

    if options.convert_admonitions:
        content = _convert_admonitions(content, messages)

    if options.convert_supported_images:
        content = _convert_supported_images(content, messages)

    if options.remove_unsupported_jsx:
        content = _remove_unsupported_jsx(content, messages)

    if options.patch_links_from_reference or options.patch_images_from_reference:
        content = _patch_from_reference(
            content=content,
            reference_doc=reference_doc or "",
            messages=messages,
            patch_links=options.patch_links_from_reference,
            patch_images=options.patch_images_from_reference,
        )

    result_messages = tuple(messages)

    return TransformResult(
        content=content,
        status=_status_for(result_messages),
        metadata=metadata,
        messages=result_messages,
    )


def _normalize_line_endings(content: str) -> str:
    """Normalize all line endings to LF."""
    return content.replace("\r\n", "\n").replace("\r", "\n")


def _extract_frontmatter(
    content: str,
    messages: list[TransformMessage],
    *,
    strip: bool,
) -> tuple[str, Frontmatter]:
    """Parse leading YAML frontmatter and optionally strip it from content."""
    lines = content.splitlines(keepends=True)

    if not lines or lines[0].strip() != "---":
        return content, {}

    for closing_index in range(1, len(lines)):
        if lines[closing_index].strip() == "---":
            raw_frontmatter = "".join(lines[1:closing_index])
            metadata = _parse_frontmatter(raw_frontmatter, messages)

            if not strip:
                return content, metadata

            remaining_content = "".join(lines[closing_index + 1 :])

            if remaining_content.startswith("\n"):
                remaining_content = remaining_content[1:]

            return remaining_content, metadata

    messages.append(
        TransformMessage(
            level=TransformMessageLevel.WARNING,
            code="unterminated_frontmatter",
            message="Frontmatter opening marker was found, but no closing marker exists.",
        )
    )
    return content, {}


def _parse_frontmatter(raw_frontmatter: str, messages: list[TransformMessage]) -> Frontmatter:
    """Parse YAML frontmatter into metadata."""
    try:
        loaded: object = yaml.safe_load(raw_frontmatter)
    except yaml.YAMLError as exc:
        messages.append(
            TransformMessage(
                level=TransformMessageLevel.ERROR,
                code="invalid_frontmatter_yaml",
                message=f"Frontmatter YAML could not be parsed: {exc}",
            )
        )
        return {}

    if loaded is None:
        return {}

    if not isinstance(loaded, dict):
        messages.append(
            TransformMessage(
                level=TransformMessageLevel.WARNING,
                code="unsupported_frontmatter_root",
                message="Frontmatter root must be a YAML mapping/object.",
            )
        )
        return {}

    metadata: Frontmatter = {}

    for raw_key, raw_value in loaded.items():
        if not isinstance(raw_key, str):
            messages.append(
                TransformMessage(
                    level=TransformMessageLevel.WARNING,
                    code="unsupported_frontmatter_key",
                    message=f"Ignored frontmatter key because it is not a string: {raw_key!r}",
                )
            )
            continue

        if not _is_frontmatter_value(raw_value):
            messages.append(
                TransformMessage(
                    level=TransformMessageLevel.WARNING,
                    code="unsupported_frontmatter_value",
                    message=f"Ignored unsupported frontmatter value for key: {raw_key}",
                )
            )
            continue

        metadata[raw_key] = raw_value

    return metadata


def _is_frontmatter_value(value: object) -> TypeGuard[FrontmatterValue]:
    """Return whether a value can be stored in TransformResult metadata."""
    if value is None or isinstance(value, bool | int | float | str):
        return True

    if isinstance(value, list):
        return all(_is_frontmatter_value(item) for item in value)

    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_frontmatter_value(item) for key, item in value.items())

    return False


def _remove_imports(content: str) -> str:
    """Remove single-line MDX import statements."""
    return "".join(line for line in content.splitlines(keepends=True) if not _IMPORT_LINE_RE.match(line))


def _convert_admonitions(content: str, messages: list[TransformMessage]) -> str:
    """Convert Docusaurus-style admonitions to Markdown blockquotes."""
    lines = content.split("\n")
    output: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        match = _ADMONITION_START_RE.match(line.strip())

        if match is None:
            output.append(line)
            index += 1
            continue

        kind = match.group("kind").lower()
        title = match.group("title")

        if kind not in _ADMONITION_KINDS:
            output.append(line)
            index += 1
            continue

        index += 1
        closed = False
        body_lines: list[str] = []

        while index < len(lines):
            current_line = lines[index]

            if _ADMONITION_CLOSE_RE.match(current_line.strip()):
                closed = True
                index += 1
                break

            body_lines.append(current_line)
            index += 1

        body_lines = _trim_blank_lines(body_lines)

        label = _format_admonition_label(kind=kind, title=title)
        output.append(f"> **{label}**")

        for body_line in body_lines:
            output.append(">" if body_line == "" else f"> {body_line}")

        if not closed:
            messages.append(
                TransformMessage(
                    level=TransformMessageLevel.WARNING,
                    code="unterminated_admonition",
                    message=f"The {kind} admonition was not closed.",
                )
            )

    return "\n".join(output)


def _trim_blank_lines(lines: list[str]) -> list[str]:
    """Remove blank lines from the start and end of a line block."""
    start = 0
    end = len(lines)

    while start < end and lines[start].strip() == "":
        start += 1

    while end > start and lines[end - 1].strip() == "":
        end -= 1

    return lines[start:end]


def _format_admonition_label(*, kind: str, title: str | None) -> str:
    """Format an admonition label for blockquote output."""
    normalized_kind = kind.capitalize()

    if title is None or title.strip() == "":
        return normalized_kind

    return f"{normalized_kind} — {title.strip()}"


def _convert_supported_images(content: str, messages: list[TransformMessage]) -> str:
    """Convert supported MDX image components to Markdown images."""

    def replace(match: re.Match[str]) -> str:
        attrs = _parse_jsx_string_attributes(match.group("attrs"))
        src = attrs.get("src")

        if src is None or src.strip() == "":
            messages.append(
                TransformMessage(
                    level=TransformMessageLevel.WARNING,
                    code="image_with_caption_missing_src",
                    message="Skipped ImageWithCaption because it does not contain a src attribute.",
                )
            )
            return match.group(0)

        alt = attrs.get("alt")
        if alt is None or alt.strip() == "":
            alt = "Image"

        return f"![{_escape_markdown_alt_text(alt)}]({src})"

    return _IMAGE_WITH_CAPTION_RE.sub(replace, content)


def _parse_jsx_string_attributes(raw_attrs: str) -> dict[str, str]:
    """Parse simple JSX string attributes from a component body."""
    return {match.group("name"): match.group("value") for match in _JSX_ATTRIBUTE_RE.finditer(raw_attrs)}


def _escape_markdown_alt_text(value: str) -> str:
    """Escape characters that would break Markdown image alt text."""
    return value.replace("]", r"\]")


def _remove_unsupported_jsx(content: str, messages: list[TransformMessage]) -> str:
    """Remove standalone unsupported JSX component lines."""
    _ = messages

    output: list[str] = []

    for line in content.splitlines(keepends=True):
        match = _UNSUPPORTED_JSX_LINE_RE.match(line.strip())

        if match is None:
            output.append(line)
            continue

        component = match.group("component")

        if component in _SUPPORTED_JSX_COMPONENTS:
            output.append(line)
            continue

        continue

    return "".join(output)


def _has_reference(reference_doc: str | None) -> bool:
    """Return whether a usable CMS reference document exists."""
    return reference_doc is not None and reference_doc.strip() != ""


def _patch_from_reference(
    *,
    content: str,
    reference_doc: str | None,
    messages: list[TransformMessage],
    patch_links: bool,
    patch_images: bool,
) -> str:
    """Patch Markdown link/image URLs from a CMS reference document."""
    if reference_doc is None or reference_doc.strip() == "":
        messages.append(
            TransformMessage(
                level=TransformMessageLevel.WARNING,
                code="missing_reference_doc",
                message="Reference document is missing; skipped URL patching.",
            )
        )
        return content

    source_references = _extract_markdown_references(
        content,
        include_links=patch_links,
        include_images=patch_images,
    )
    reference_references = _extract_markdown_references(
        reference_doc,
        include_links=patch_links,
        include_images=patch_images,
    )

    source_counts = Counter(reference.key for reference in source_references)
    reference_groups = _group_reference_urls(reference_references)

    source_keys = set(source_counts)
    reference_keys = set(reference_groups)
    reference_only_keys = reference_keys - source_keys

    if reference_only_keys:
        messages.append(
            TransformMessage(
                level=TransformMessageLevel.WARNING,
                code="reference_urls_not_in_source",
                message=_format_reference_urls_not_in_source_message(
                    reference_references,
                    reference_only_keys,
                ),
            )
        )

    direct_url_map: dict[_MarkdownReferenceKey, str] = {}
    positional_url_map: dict[_MarkdownReferenceKey, tuple[str, ...]] = {}
    blocked_keys: set[_MarkdownReferenceKey] = set()
    missing_keys: set[_MarkdownReferenceKey] = set()

    for key, source_count in source_counts.items():
        reference_urls = reference_groups.get(key)

        if reference_urls is None:
            missing_keys.add(key)
            blocked_keys.add(key)
            continue

        if source_count == 1 and len(reference_urls) == 1:
            direct_url_map[key] = reference_urls[0]
            continue

        if source_count == len(reference_urls):
            positional_url_map[key] = reference_urls
            continue

        blocked_keys.add(key)

        kind, label = key
        messages.append(
            TransformMessage(
                level=TransformMessageLevel.WARNING,
                code="ambiguous_reference_url_count_mismatch",
                message=(
                    f"Reference document contains {len(reference_urls)} {kind} URL(s) for label {label!r}, "
                    f"but source document contains {source_count}; skipped this mapping."
                ),
            )
        )

    occurrence_counter: Counter[_MarkdownReferenceKey] = Counter()

    def replace(match: re.Match[str]) -> str:
        markdown_reference = _markdown_reference_from_match(match)

        if markdown_reference.kind == "link" and not patch_links:
            return match.group(0)

        if markdown_reference.kind == "image" and not patch_images:
            return match.group(0)

        key = markdown_reference.key

        reference_url = direct_url_map.get(key)
        if reference_url is not None:
            return _format_markdown_reference(markdown_reference, reference_url)

        positional_urls = positional_url_map.get(key)
        if positional_urls is not None:
            occurrence_index = occurrence_counter[key]
            occurrence_counter[key] += 1

            if occurrence_index < len(positional_urls):
                return _format_markdown_reference(markdown_reference, positional_urls[occurrence_index])

            return match.group(0)

        return match.group(0)

    patched_content = _MARKDOWN_URL_RE.sub(replace, content)

    if missing_keys:
        messages.append(
            TransformMessage(
                level=TransformMessageLevel.WARNING,
                code="missing_reference_urls",
                message=_format_missing_reference_urls_message(source_references, missing_keys),
            )
        )

    return patched_content


def _format_reference_urls_not_in_source_message(
    reference_references: Sequence[_MarkdownReference],
    reference_only_keys: set[_MarkdownReferenceKey],
) -> str:
    """Format warning for CMS reference URLs that no longer exist in source."""
    missing_from_source = [reference for reference in reference_references if reference.key in reference_only_keys]

    details = ", ".join(
        f"{reference.kind} {reference.label!r} -> {reference.url!r}" for reference in missing_from_source
    )

    return (
        f"CMS reference document contains {len(missing_from_source)} Markdown reference(s) "
        f"that are not present in the source document: {details}"
    )


def _extract_markdown_references(
    content: str,
    *,
    include_links: bool,
    include_images: bool,
) -> tuple[_MarkdownReference, ...]:
    """Extract Markdown links/images from content in document order."""
    references: list[_MarkdownReference] = []

    for match in _MARKDOWN_URL_RE.finditer(content):
        markdown_reference = _markdown_reference_from_match(match)

        if markdown_reference.kind == "link" and not include_links:
            continue

        if markdown_reference.kind == "image" and not include_images:
            continue

        references.append(markdown_reference)

    return tuple(references)


def _markdown_reference_from_match(match: re.Match[str]) -> _MarkdownReference:
    """Create a Markdown reference object from a regex match."""
    return _MarkdownReference(
        kind="image" if match.group("image") else "link",
        label=match.group("label"),
        url=match.group("url"),
    )


def _group_reference_urls(
    references: Sequence[_MarkdownReference],
) -> dict[_MarkdownReferenceKey, tuple[str, ...]]:
    """Group reference URLs by Markdown reference key while preserving order."""
    grouped: defaultdict[_MarkdownReferenceKey, list[str]] = defaultdict(list)

    for reference in references:
        grouped[reference.key].append(reference.url)

    return {key: tuple(urls) for key, urls in grouped.items()}


def _format_markdown_reference(reference: _MarkdownReference, url: str) -> str:
    """Render a Markdown link or image with a patched URL."""
    if reference.kind == "image":
        return f"![{reference.label}]({url})"

    return f"[{reference.label}]({url})"


def _format_missing_reference_urls_message(
    source_references: Sequence[_MarkdownReference],
    missing_keys: set[_MarkdownReferenceKey],
) -> str:
    """Format missing reference URL warning message."""
    missing_references = [reference for reference in source_references if reference.key in missing_keys]

    details = ", ".join(
        f"{reference.kind} {reference.label!r} -> {reference.url!r}" for reference in missing_references
    )

    return f"No matching CMS reference URLs found for {len(missing_references)} Markdown reference(s): {details}"


def _status_for(messages: Sequence[TransformMessage]) -> TransformStatus:
    """Derive the overall transform status from messages."""
    if any(message.level == TransformMessageLevel.ERROR for message in messages):
        return TransformStatus.FAILURE

    if any(message.level == TransformMessageLevel.WARNING for message in messages):
        return TransformStatus.WARNING

    return TransformStatus.SUCCESS
