"""MDX to Eledo CMS Markdown transformer."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeGuard

import yaml

type FrontmatterValue = (
    None
    | bool
    | int
    | float
    | str
    | list["FrontmatterValue"]
    | dict[str, "FrontmatterValue"]
)
type Frontmatter = dict[str, FrontmatterValue]

_ADMONITION_START_RE = re.compile(r"^:::(?P<kind>[a-zA-Z]+)(?:\s+(?P<title>.*))?\s*$")
_ADMONITION_CLOSE_RE = re.compile(r"^:::\s*$")
_IMPORT_LINE_RE = re.compile(r"^\s*import\s+.+$")
_UNSUPPORTED_JSX_LINE_RE = re.compile(r"^\s*</?[A-Z][A-Za-z0-9_.]*(?:\s+[^>]*)?/?>\s*$")

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
        content = normalize_line_endings(content)

    if options.strip_frontmatter:
        content, metadata = strip_frontmatter(content, messages)

    if options.remove_imports:
        content = remove_imports(content)

    if options.convert_admonitions:
        content = convert_admonitions(content, messages)

    if options.convert_supported_images:
        content = convert_supported_images(content, messages)

    if options.remove_unsupported_jsx:
        content = remove_unsupported_jsx(content, messages)

    if has_reference(reference_doc) and (options.patch_links_from_reference or options.patch_images_from_reference):
        content = patch_from_reference(
            content=content,
            reference_doc=reference_doc or "",
            messages=messages,
        )

    result_messages = tuple(messages)

    return TransformResult(
        content=content,
        status=status_for(result_messages),
        metadata=metadata,
        messages=result_messages,
    )


def normalize_line_endings(content: str) -> str:
    """Normalize all line endings to LF."""
    return content.replace("\r\n", "\n").replace("\r", "\n")


def strip_frontmatter(content: str, messages: list[TransformMessage]) -> tuple[str, Frontmatter]:
    """Strip a leading YAML frontmatter block and return parsed metadata."""
    lines = content.splitlines(keepends=True)

    if not lines or lines[0].strip() != "---":
        return content, {}

    for closing_index in range(1, len(lines)):
        if lines[closing_index].strip() == "---":
            raw_frontmatter = "".join(lines[1:closing_index])
            remaining_content = "".join(lines[closing_index + 1 :])

            if remaining_content.startswith("\n"):
                remaining_content = remaining_content[1:]

            return remaining_content, parse_frontmatter(raw_frontmatter, messages)

    messages.append(
        TransformMessage(
            level=TransformMessageLevel.WARNING,
            code="unterminated_frontmatter",
            message="Frontmatter opening marker was found, but no closing marker exists.",
        )
    )
    return content, {}


def parse_frontmatter(raw_frontmatter: str, messages: list[TransformMessage]) -> Frontmatter:
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

        if not is_frontmatter_value(raw_value):
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


def is_frontmatter_value(value: object) -> TypeGuard[FrontmatterValue]:
    """Return whether a value can be stored in TransformResult metadata."""
    if value is None or isinstance(value, bool | int | float | str):
        return True

    if isinstance(value, list):
        return all(is_frontmatter_value(item) for item in value)

    if isinstance(value, dict):
        return all(isinstance(key, str) and is_frontmatter_value(item) for key, item in value.items())

    return False


def remove_imports(content: str) -> str:
    """Remove single-line MDX import statements."""
    return "".join(line for line in content.splitlines(keepends=True) if not _IMPORT_LINE_RE.match(line))


def convert_admonitions(content: str, messages: list[TransformMessage]) -> str:
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

        label = format_admonition_label(kind=kind, title=title)

        output.append(f"> **{label}**")
        output.append(">")

        index += 1
        closed = False

        while index < len(lines):
            current_line = lines[index]

            if _ADMONITION_CLOSE_RE.match(current_line.strip()):
                closed = True
                index += 1
                break

            output.append(">" if current_line == "" else f"> {current_line}")
            index += 1

        if not closed:
            messages.append(
                TransformMessage(
                    level=TransformMessageLevel.WARNING,
                    code="unterminated_admonition",
                    message=f"The {kind} admonition was not closed.",
                )
            )

    return "\n".join(output)


def format_admonition_label(*, kind: str, title: str | None) -> str:
    """Format an admonition label for blockquote output."""
    normalized_kind = kind.capitalize()

    if title is None or title.strip() == "":
        return normalized_kind

    return f"{normalized_kind} — {title.strip()}"


def convert_supported_images(content: str, messages: list[TransformMessage]) -> str:
    """Convert supported MDX image components.

    This is intentionally a no-op until real image fixtures define the supported
    component shapes.
    """
    _ = messages
    return content


def remove_unsupported_jsx(content: str, messages: list[TransformMessage]) -> str:
    """Remove standalone unsupported JSX component lines."""
    output: list[str] = []

    for line in content.splitlines(keepends=True):
        if _UNSUPPORTED_JSX_LINE_RE.match(line.strip()):
            messages.append(
                TransformMessage(
                    level=TransformMessageLevel.WARNING,
                    code="unsupported_jsx_removed",
                    message=f"Removed unsupported JSX component line: {line.strip()}",
                )
            )
            continue

        output.append(line)

    return "".join(output)


def has_reference(reference_doc: str | None) -> bool:
    """Return whether a usable CMS reference document exists."""
    return reference_doc is not None and reference_doc.strip() != ""


def patch_from_reference(
    *,
    content: str,
    reference_doc: str,
    messages: list[TransformMessage],
) -> str:
    """Patch CMS-specific mappings from the reference document.

    This is intentionally a no-op until real reference fixtures define link and
    image preservation behavior.
    """
    _ = reference_doc, messages
    return content


def status_for(messages: Sequence[TransformMessage]) -> TransformStatus:
    """Derive the overall transform status from messages."""
    if any(message.level == TransformMessageLevel.ERROR for message in messages):
        return TransformStatus.FAILURE

    if any(message.level == TransformMessageLevel.WARNING for message in messages):
        return TransformStatus.WARNING

    return TransformStatus.SUCCESS