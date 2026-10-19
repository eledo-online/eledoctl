"""Conservative, manually reviewed Eledo CMS -> Git/MDX recovery.

No Git commands or CMS writes are performed. Original MDX-only structures are
kept verbatim. Ambiguous edits fail closed, leaving the local file untouched.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from enum import StrEnum
from pathlib import Path

from eledoctl.internal.docs.transformer import TransformOptions, TransformStatus, transform_document
from eledoctl.internal.docs.uploader import SyncItem
from pyeledo import EledoApiError, EledoInvalidResponseError
from pyeledo.internal.cms import CmsClient

_REFERENCE_RE = re.compile(
    r"(?P<image>!)?\[(?P<label>(?:\\.|[^\]\\])*)\]"
    r"\((?P<url>[^)\n]+)\)(?P<suffix>\{[^{}\s]+\})?"
)
_IMPORT_RE = re.compile(r"^\s*import\s+.+$")
_JSX_LINE_RE = re.compile(r"^\s*</?[A-Z][A-Za-z0-9_.]*(?:\s+[^>]*)?/?>\s*$")
_ADMONITION_RE = re.compile(r"^:::(note|tip|info|important|warning|caution|danger)(?:\s+.*)?$")
_ADMONITION_END_RE = re.compile(r"^:::\s*$")

# Only transformer stages that are safe for the comparisons below are used.
_NO_URL_PATCH = TransformOptions(
    patch_links_from_reference=False,
    patch_images_from_reference=False,
)


class PullAction(StrEnum):
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PullResult:
    source_path: Path | None
    target_path: str
    action: PullAction
    dry_run: bool
    written: bool
    messages: tuple[str, ...] = ()
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class PullSummary:
    total: int
    updated: int
    unchanged: int
    failed: int
    cms_only: int
    dry_run: bool


@dataclass(frozen=True, slots=True)
class Recovery:
    content: str | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class _Unit:
    raw: str
    projected: tuple[str, ...]
    editable: bool
    mode: str = "plain"


@dataclass(frozen=True, slots=True)
class _Reference:
    kind: str
    label: str
    url: str
    full: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.kind, _normalize_label(self.label))


def recover_document(*, local_mdx: str, cms_markdown: str) -> Recovery:
    """Merge CMS editorial text into original MDX, preserving Git-only syntax.

    Returns an error instead of content if the merge cannot be verified. No
    file system or server side effects occur in this function.
    """
    frontmatter, body = _split_frontmatter(local_mdx)
    units, unit_error = _source_units(body)
    if unit_error is not None:
        return Recovery(None, unit_error)

    projected_lines = [line for unit in units for line in unit.projected]
    baseline = "".join(projected_lines)
    full_projection = transform_document(source_doc=local_mdx, options=_NO_URL_PATCH)
    if full_projection.status != TransformStatus.SUCCESS:
        return Recovery(None, "The existing forward transformer cannot process the Git source.")
    if baseline != full_projection.content:
        return Recovery(
            None,
            "The source contains an MDX transformation that cannot be mapped safely back to its original lines.",
        )

    normalized_cms, url_error = _restore_references(cms_markdown, baseline)
    if url_error is not None:
        return Recovery(None, url_error)
    assert normalized_cms is not None
    normalized_cms = _align_boundary_newlines(baseline, normalized_cms)

    if normalized_cms == baseline or normalized_cms.strip() == baseline.strip():
        return Recovery(local_mdx)

    incoming_lines = normalized_cms.splitlines(keepends=True)
    projected_indexes = [unit_index for unit_index, unit in enumerate(units) for _ in unit.projected]
    outputs = [unit.raw for unit in units]
    insert_before: defaultdict[int, list[str]] = defaultdict(list)
    matcher = SequenceMatcher(a=projected_lines, b=incoming_lines, autojunk=False)

    for opcode, start, end, new_start, new_end in matcher.get_opcodes():
        if opcode == "equal":
            continue
        replacement = "".join(incoming_lines[new_start:new_end])
        if start == end:  # insert without removing any original content
            where = (
                projected_indexes[start]
                if start < len(projected_indexes)
                else (projected_indexes[-1] + 1 if projected_indexes else len(units))
            )
            insert_before[where].append(replacement)
            continue

        touched = set(projected_indexes[start:end])
        if any(not units[index].editable for index in touched):
            return Recovery(None, "CMS changes overlap protected MDX constructs (JSX or admonition structure).")
        modes = {units[index].mode for index in touched}
        if len(modes) != 1:
            return Recovery(None, "CMS edit crosses structurally different MDX content.")
        if "admonition" in modes:
            unquoted = _unquote_admonition(replacement)
            if unquoted is None:
                return Recovery(None, "CMS admonition quote structure changed; manual merge required.")
            replacement = unquoted
        # An opcode must not split the transformed projection of a single unit.
        for index in touched:
            positions = [position for position, owner in enumerate(projected_indexes) if owner == index]
            if not all(start <= position < end for position in positions):
                return Recovery(None, "CMS edit splits an MDX source construct; manual merge required.")
        first = projected_indexes[start]
        last = projected_indexes[end - 1]
        # JSX or imports between replaced paragraphs have no CMS representation.
        # Do not move them implicitly across a replaced range.
        if any(not units[index].projected for index in range(first + 1, last)):
            return Recovery(None, "CMS edit crosses MDX-only source lines; manual merge required.")
        outputs[first] = replacement
        for index in touched:
            if index != first:
                outputs[index] = ""

    merged_body = "".join("".join(insert_before[index]) + outputs[index] for index in range(len(units))) + "".join(
        insert_before[len(units)]
    )
    candidate = frontmatter + merged_body

    # This is the essential safety assertion: forward representation of the
    # recovered source must agree with the CMS after URL de-resolution.
    projected_candidate = transform_document(source_doc=candidate, options=_NO_URL_PATCH)
    if projected_candidate.status != TransformStatus.SUCCESS or projected_candidate.content != normalized_cms:
        return Recovery(None, "Recovered MDX failed the forward-transform round-trip check.")
    return Recovery(candidate)


def _align_boundary_newlines(baseline: str, incoming: str) -> str:
    """Ignore only leading/trailing empty-line differences from CMS editing.

    Original MDX contains some blank lines left by removed imports and JSX.
    These layout-only boundary differences should not churn the Git diff.
    """
    if baseline.strip() == "" or incoming.strip() == "":
        return incoming
    original_left = len(baseline) - len(baseline.lstrip("\n"))
    original_right = len(baseline) - len(baseline.rstrip("\n"))
    core = incoming.strip("\n")
    return "\n" * original_left + core + "\n" * original_right


def _split_frontmatter(source: str) -> tuple[str, str]:
    lines = source.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return "", source
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            # Keep the entire frontmatter and its separator byte-for-byte.
            end = i + 1
            if end < len(lines) and lines[end].strip() == "":
                end += 1
            return "".join(lines[:end]), "".join(lines[end:])
    return "", source  # The forward-transform check will reject invalid YAML.


def _source_units(content: str) -> tuple[tuple[_Unit, ...], str | None]:
    lines = content.splitlines(keepends=True)
    units: list[_Unit] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if _IMPORT_RE.match(line) or (_JSX_LINE_RE.match(line) and "ImageWithCaption" not in line):
            units.append(_Unit(line, (), False))
            i += 1
            continue
        if _ADMONITION_RE.match(line.strip()):
            end = i + 1
            while end < len(lines) and not _ADMONITION_END_RE.match(lines[end].strip()):
                end += 1
            if end >= len(lines):
                return (), "Unclosed Docusaurus admonition; manual merge required."
            block = "".join(lines[i : end + 1])
            output = transform_document(source_doc=block, options=_NO_URL_PATCH)
            if output.status != TransformStatus.SUCCESS:
                return (), "Could not project a Docusaurus admonition."
            units.extend(_admonition_units(lines[i : end + 1], output.content))
            i = end + 1
            continue
        if "<ImageWithCaption" in line:
            end = i
            while end < len(lines) and "/>" not in lines[end]:
                end += 1
            if end >= len(lines):
                return (), "Unclosed ImageWithCaption component; manual merge required."
            block = "".join(lines[i : end + 1])
            output = transform_document(source_doc=block, options=_NO_URL_PATCH)
            if output.status != TransformStatus.SUCCESS:
                return (), "Could not project ImageWithCaption; manual merge required."
            units.append(_Unit(block, tuple(output.content.splitlines(keepends=True)), False))
            i = end + 1
            continue
        units.append(_Unit(line, (line,), True))
        i += 1
    return tuple(units), None


def _admonition_units(lines: list[str], projected: str) -> tuple[_Unit, ...]:
    """Map editable blockquote body lines onto their original admonition lines.

    Any case that cannot be represented one-to-one remains an atomic protected
    unit, so the reverse algorithm fails rather than corrupting the wrapper.
    """
    content_lines = lines[1:-1]
    start = 0
    end = len(content_lines)
    while start < end and not content_lines[start].strip():
        start += 1
    while end > start and not content_lines[end - 1].strip():
        end -= 1
    projection = projected.splitlines(keepends=True)
    if len(projection) != 1 + end - start:
        return (_Unit("".join(lines), tuple(projection), False),)

    result = [_Unit(lines[0], (projection[0],), False)]
    for index, line in enumerate(content_lines):
        if start <= index < end:
            result.append(_Unit(line, (projection[1 + index - start],), True, "admonition"))
        else:
            result.append(_Unit(line, (), False))
    result.append(_Unit(lines[-1], (), False))
    return tuple(result)


def _unquote_admonition(text: str) -> str | None:
    """Turn the CMS Markdown blockquote body back into admonition body lines."""
    body: list[str] = []
    for line in text.splitlines(keepends=True):
        if line.startswith("> "):
            body.append(line[2:])
        elif line.strip("\n") == ">":
            body.append(line[1:])
        else:
            return None
    return "".join(body)


def _normalize_label(text: str) -> str:
    text = re.sub(r"\\(.)", r"\1", text.strip())
    previous: str | None = None
    while text != previous:
        previous = text
        for marker in ("**", "__", "`", "*", "_"):
            if text.startswith(marker) and text.endswith(marker) and len(text) > len(marker) * 2:
                text = text[len(marker) : -len(marker)].strip()
    return text


def _references(markdown: str) -> tuple[_Reference, ...]:
    return tuple(
        _Reference(
            kind="image" if match.group("image") else "link",
            label=match.group("label"),
            url=match.group("url"),
            full=match.group(0),
        )
        for match in _REFERENCE_RE.finditer(markdown)
    )


def _restore_references(cms: str, baseline: str) -> tuple[str | None, str | None]:
    local = _references(baseline)
    remote = _references(cms)
    local_groups: defaultdict[tuple[str, str], list[_Reference]] = defaultdict(list)
    remote_groups: defaultdict[tuple[str, str], list[_Reference]] = defaultdict(list)
    for ref in local:
        local_groups[ref.key].append(ref)
    for ref in remote:
        remote_groups[ref.key].append(ref)

    if Counter(ref.key for ref in local) != Counter(ref.key for ref in remote):
        missing = sorted(set(local_groups) ^ set(remote_groups))
        count_differences = sorted(
            key for key in (set(local_groups) & set(remote_groups)) if len(local_groups[key]) != len(remote_groups[key])
        )
        return None, f"Cannot reliably match CMS links/images to Git references: {missing + count_differences!r}"

    replacement_by_key: dict[tuple[str, str], tuple[str, ...]] = {}
    for key, group in local_groups.items():
        # Different URLs with duplicate labels cannot be linked to individual
        # remote references reliably without a prior CMS baseline.
        if len(group) > 1 and len({item.url for item in group}) > 1:
            return None, f"Ambiguous repeated link/image label {key!r}; manual URL reconciliation required."
        replacement_by_key[key] = tuple(item.full for item in group)

    seen: Counter[tuple[str, str]] = Counter()

    def replace(match: re.Match[str]) -> str:
        reference = _Reference(
            kind="image" if match.group("image") else "link",
            label=match.group("label"),
            url=match.group("url"),
            full=match.group(0),
        )
        index = seen[reference.key]
        seen[reference.key] += 1
        return replacement_by_key[reference.key][index]

    return _REFERENCE_RE.sub(replace, cms), None


async def pull_one_document(*, cms: CmsClient, item: SyncItem, dry_run: bool) -> PullResult:
    """Retrieve and merge one CMS article into an existing local file."""

    def failure(reason: str) -> PullResult:
        return PullResult(item.source_path, item.target_path, PullAction.FAILED, dry_run, False, (reason,))

    try:
        remote = await cms.retrieve_article(item.target_segments)
    except (EledoApiError, EledoInvalidResponseError) as exc:
        return failure(f"CMS retrieval failed: {exc}")
    if remote.article.markdown is None:
        return failure("CMS article has null Markdown; refusing to overwrite Git source.")
    try:
        original = item.source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return failure(f"Cannot read Git file: {exc}")

    recovery = recover_document(local_mdx=original, cms_markdown=remote.article.markdown)
    if recovery.error is not None or recovery.content is None:
        return failure(recovery.error or "Unknown reverse transformation failure")
    if recovery.content == original:
        return PullResult(item.source_path, item.target_path, PullAction.UNCHANGED, dry_run, False)
    if not dry_run:
        try:
            item.source_path.write_text(recovery.content, encoding="utf-8", newline="")
        except OSError as exc:
            return failure(f"Could not write Git file: {exc}")
    return PullResult(item.source_path, item.target_path, PullAction.UPDATED, dry_run, not dry_run)


def summarize_pull(results: Sequence[PullResult], *, dry_run: bool) -> PullSummary:
    return PullSummary(
        total=sum(x.source_path is not None for x in results),
        updated=sum(x.action == PullAction.UPDATED for x in results),
        unchanged=sum(x.action == PullAction.UNCHANGED for x in results),
        failed=sum(x.action == PullAction.FAILED for x in results),
        cms_only=sum(x.error_code == "cms_only_article" for x in results),
        dry_run=dry_run,
    )


def write_pull_log(path: Path, results: Sequence[PullResult]) -> None:
    """Write a machine-readable JSONL record, including manual-review errors."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output:
        for result in results:
            record = asdict(result)
            record["source_path"] = str(result.source_path) if result.source_path is not None else None
            record["action"] = result.action.value
            record["status"] = "failure" if result.action == PullAction.FAILED else "success"
            output.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
