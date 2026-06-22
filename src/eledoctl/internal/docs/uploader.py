"""Internal documentation uploader for syncing source Markdown into Eledo CMS."""

from __future__ import annotations

import json
import yaml
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from eledoctl.internal.docs.transformer import (
    FrontmatterValue,
    TransformMessage,
    TransformMessageLevel,
    TransformOptions,
    TransformStatus,
    transform_document,
)
from pyeledo import EledoApiError, EledoInvalidResponseError
from pyeledo.internal.cms import (
    CmsArticleCreateRequest,
    CmsArticleRetrieveResponse,
    CmsArticleUpdateRequest,
    CmsClient,
)

_DOC_EXTENSIONS = {".md", ".mdx"}
_CATEGORY_FILENAMES = ("_category_.yml", "_category_.yaml")


class SyncAction(StrEnum):
    """Action planned or performed for one source document."""

    CREATE = "create"
    UPDATE = "update"
    SKIP_UNCHANGED = "skip-unchanged"
    FAILED = "failed"


class SyncStatus(StrEnum):
    """Uploader-level status for one source document."""

    SUCCESS = "success"
    WARNING = "warning"
    FAILURE = "failure"


@dataclass(frozen=True, slots=True)
class SyncMessage:
    """Uploader or transformer message attached to a sync result."""

    level: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class SyncOptions:
    """Options used by the uploader."""

    source_root: Path
    selection: Path | None
    destination_root: str = "/documentation"
    tag: str = ""
    dry_run: bool = False
    skip_unchanged: bool = True
    transform_options: TransformOptions = field(default_factory=TransformOptions)


@dataclass(frozen=True, slots=True)
class SyncItem:
    """One source file and its derived CMS destination path."""

    source_path: Path
    target_segments: tuple[str, ...]
    target_path: str


@dataclass(frozen=True, slots=True)
class SyncPlan:
    """Prepared sync plan."""

    source_root: Path
    selection: Path
    items: tuple[SyncItem, ...]


@dataclass(frozen=True, slots=True)
class SyncFileResult:
    """Result for one synced source file."""

    source_path: Path
    target_path: str
    action: SyncAction
    status: SyncStatus
    dry_run: bool
    uploaded: bool
    title: str | None = None
    order: int | None = None
    messages: tuple[SyncMessage, ...] = ()

    @property
    def requires_inspection(self) -> bool:
        """Return whether this file should be manually inspected."""
        return self.status in {SyncStatus.WARNING, SyncStatus.FAILURE}


@dataclass(frozen=True, slots=True)
class SyncSummary:
    """Summary for a sync run."""

    total: int
    created: int
    updated: int
    skipped: int
    warnings: int
    failures: int
    dry_run: bool


def build_sync_plan(options: SyncOptions) -> SyncPlan:
    """Build a deterministic list of files to sync."""
    source_root = options.source_root.expanduser().resolve()
    selection = (options.selection or source_root).expanduser().resolve()

    if not source_root.exists():
        raise ValueError(f"Source root does not exist: {source_root}")

    if not source_root.is_dir():
        raise ValueError(f"Source root must be a directory: {source_root}")

    if not selection.exists():
        raise ValueError(f"Selection does not exist: {selection}")

    try:
        selection.relative_to(source_root)
    except ValueError as exc:
        raise ValueError(f"Selection must be inside source root: {selection}") from exc

    files = _discover_files(selection)
    destination_segments = _destination_segments(options.destination_root)

    items = list(
        SyncItem(
            source_path=file,
            target_segments=_target_segments(
                source_root=source_root,
                source_path=file,
                destination_segments=destination_segments,
            ),
            target_path=_target_path(
                _target_segments(
                    source_root=source_root,
                    source_path=file,
                    destination_segments=destination_segments,
                )
            ),
        )
        for file in files
    )

    items.sort(key=lambda item: (len(item.target_segments), item.target_segments, item.source_path))

    _validate_unique_targets(items)

    return SyncPlan(
        source_root=source_root,
        selection=selection,
        items=tuple(items),
    )


async def sync_one_document(
    *,
    cms: CmsClient,
    item: SyncItem,
    options: SyncOptions,
) -> SyncFileResult:
    """Synchronize one source document into Eledo CMS."""
    existing: CmsArticleRetrieveResponse | None = None
    reference_doc: str | None = None

    try:
        retrieved = await cms.retrieve_article(item.target_segments)
        existing = retrieved
        reference_doc = retrieved.article.markdown
    except EledoApiError as exc:
        if not _is_missing_article_error(exc):
            return _failure_result(
                item=item,
                dry_run=options.dry_run,
                code="cms_retrieve_failed",
                message=str(exc),
            )
    except EledoInvalidResponseError as exc:
        return _failure_result(
            item=item,
            dry_run=options.dry_run,
            code="cms_invalid_reference_response",
            message=str(exc),
        )

    try:
        source_doc = item.source_path.read_text(encoding="utf-8")
    except OSError as exc:
        return _failure_result(
            item=item,
            dry_run=options.dry_run,
            code="source_read_failed",
            message=str(exc),
        )

    transform_result = transform_document(
        source_doc=source_doc,
        reference_doc=reference_doc,
        options=options.transform_options,
    )

    messages = list(_transform_messages(transform_result.messages))

    title = _metadata_title(transform_result.metadata, item)
    order = _metadata_order(transform_result.metadata)
    description = _metadata_description(transform_result.metadata)

    if transform_result.status == TransformStatus.FAILURE:
        return SyncFileResult(
            source_path=item.source_path,
            target_path=item.target_path,
            action=SyncAction.FAILED,
            status=SyncStatus.FAILURE,
            dry_run=options.dry_run,
            uploaded=False,
            title=title,
            order=order,
            messages=tuple(messages),
        )

    if (
        existing is not None
        and options.skip_unchanged
        and _is_unchanged(
            existing=existing,
            markdown=transform_result.content,
            title=title,
            order=order,
            description=description,
        )
    ):
        return SyncFileResult(
            source_path=item.source_path,
            target_path=item.target_path,
            action=SyncAction.SKIP_UNCHANGED,
            status=_status_from_messages(messages),
            dry_run=options.dry_run,
            uploaded=False,
            title=title,
            order=order,
            messages=tuple(messages),
        )

    action = SyncAction.UPDATE if existing is not None else SyncAction.CREATE

    if action == SyncAction.CREATE:
        parents_ready = await _ensure_parent_articles(
            cms=cms,
            target_segments=item.target_segments,
            destination_root_segments=_cms_path_segments(options.destination_root),
            label=options.tag,
            dry_run=options.dry_run,
            messages=messages,
        )

        if not parents_ready:
            return SyncFileResult(
                source_path=item.source_path,
                target_path=item.target_path,
                action=SyncAction.FAILED,
                status=SyncStatus.FAILURE,
                dry_run=options.dry_run,
                uploaded=False,
                title=title,
                order=order,
                messages=tuple(messages),
            )

    status = _status_from_messages(messages)

    if options.dry_run:
        return SyncFileResult(
            source_path=item.source_path,
            target_path=item.target_path,
            action=action,
            status=status,
            dry_run=True,
            uploaded=False,
            title=title,
            order=order,
            messages=tuple(messages),
        )

    try:
        if action == SyncAction.CREATE:
            await cms.create_article(
                path=item.target_segments,
                label=options.tag,
                request=CmsArticleCreateRequest(
                    title=title,
                    slug=item.target_segments[-1],
                    ord=order,
                    markdown=transform_result.content,
                    description=description,
                ),
            )
        else:
            await cms.update_article(
                path=item.target_segments,
                label=options.tag,
                request=CmsArticleUpdateRequest(
                    title=title,
                    slug=item.target_segments[-1],
                    ordr=order,
                    markdown=transform_result.content,
                    description=description,
                ),
            )
    except EledoApiError as exc:
        messages.append(
            SyncMessage(
                level=TransformMessageLevel.ERROR.value,
                code="cms_upload_failed",
                message=str(exc),
            )
        )

        return SyncFileResult(
            source_path=item.source_path,
            target_path=item.target_path,
            action=SyncAction.FAILED,
            status=SyncStatus.FAILURE,
            dry_run=options.dry_run,
            uploaded=False,
            title=title,
            order=order,
            messages=tuple(messages),
        )

    return SyncFileResult(
        source_path=item.source_path,
        target_path=item.target_path,
        action=action,
        status=status,
        dry_run=False,
        uploaded=True,
        title=title,
        order=order,
        messages=tuple(messages),
    )


def _status_from_messages(messages: Sequence[SyncMessage]) -> SyncStatus:
    """Derive sync status from accumulated messages."""
    if any(message.level == TransformMessageLevel.ERROR.value for message in messages):
        return SyncStatus.FAILURE

    if any(message.level == TransformMessageLevel.WARNING.value for message in messages):
        return SyncStatus.WARNING

    return SyncStatus.SUCCESS


def summarize_results(results: Sequence[SyncFileResult], *, dry_run: bool) -> SyncSummary:
    """Build a summary from file results."""
    return SyncSummary(
        total=len(results),
        created=sum(1 for result in results if result.action == SyncAction.CREATE),
        updated=sum(1 for result in results if result.action == SyncAction.UPDATE),
        skipped=sum(1 for result in results if result.action == SyncAction.SKIP_UNCHANGED),
        warnings=sum(1 for result in results if result.status == SyncStatus.WARNING),
        failures=sum(1 for result in results if result.status == SyncStatus.FAILURE),
        dry_run=dry_run,
    )


def write_log_file(path: Path, results: Sequence[SyncFileResult]) -> None:
    """Write JSON Lines sync log."""
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        for result in results:
            file.write(json.dumps(_result_to_log_record(result), ensure_ascii=False, sort_keys=True))
            file.write("\n")


def write_inspection_file(path: Path, results: Sequence[SyncFileResult]) -> None:
    """Write plain-text manual inspection list."""
    path.parent.mkdir(parents=True, exist_ok=True)

    inspection_results = [result for result in results if result.requires_inspection]

    with path.open("w", encoding="utf-8") as file:
        for result in inspection_results:
            file.write(f"{result.source_path}\n")
            file.write(f"  target: {result.target_path}\n")
            file.write(f"  status: {result.status.value}\n")
            file.write(f"  action: {result.action.value}\n")

            for message in result.messages:
                file.write(f"  - {message.level}: {message.code}: {message.message}\n")

            file.write("\n")


def _discover_files(selection: Path) -> tuple[Path, ...]:
    if selection.is_file():
        if not _is_document_file(selection):
            raise ValueError(f"Selection file must be Markdown or MDX: {selection}")

        return (selection,)

    if not selection.is_dir():
        raise ValueError(f"Selection must be a file or directory: {selection}")

    files = [path for path in selection.rglob("*") if _is_document_file(path)]
    return tuple(sorted(files, key=lambda path: (len(path.parts), path.as_posix())))


def _is_document_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in _DOC_EXTENSIONS


def _destination_segments(destination_root: str) -> tuple[str, ...]:
    segments = tuple(segment for segment in destination_root.strip("/").split("/") if segment)

    if not segments:
        raise ValueError("Destination root must contain at least one path segment.")

    return segments


def _target_segments(
    *,
    source_root: Path,
    source_path: Path,
    destination_segments: tuple[str, ...],
) -> tuple[str, ...]:
    relative_path = source_path.relative_to(source_root)
    parts = list(relative_path.parts)

    stem = Path(parts[-1]).stem

    if stem == "index":
        parts = parts[:-1]
    else:
        parts[-1] = stem

    return *destination_segments, *parts


def _target_path(segments: Sequence[str]) -> str:
    return "/" + "/".join(segments)


def _validate_unique_targets(items: Sequence[SyncItem]) -> None:
    seen: dict[str, Path] = {}

    for item in items:
        previous_source = seen.get(item.target_path)

        if previous_source is not None:
            raise ValueError(
                "Multiple source files map to the same CMS target path: "
                f"{previous_source} and {item.source_path} -> {item.target_path}"
            )

        seen[item.target_path] = item.source_path


def _metadata_title(metadata: Mapping[str, FrontmatterValue], item: SyncItem) -> str:
    """Resolve CMS article title from source metadata and file location."""
    if _is_index_document(item.source_path):
        category_label = _category_label(item.source_path.parent)

        if category_label is not None:
            return category_label

        return _title_from_slug(item.target_segments[-1])

    value = metadata.get("title")

    if isinstance(value, str):
        title = value.strip()

        if title:
            return title

    return _title_from_slug(item.target_segments[-1])


def _is_index_document(path: Path) -> bool:
    """Return whether the source document is an index document."""
    return path.stem == "index" and path.suffix in {".md", ".mdx"}


def _category_label(directory: Path) -> str | None:
    """Read Docusaurus category label from _category_.yml when available."""
    for filename in _CATEGORY_FILENAMES:
        path = directory / filename

        if not path.is_file():
            continue

        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            return None

        if not isinstance(data, dict):
            return None

        label = data.get("label")

        if not isinstance(label, str):
            return None

        label = label.strip()

        if label:
            return label

    return None


def _metadata_order(metadata: Mapping[str, FrontmatterValue]) -> int | None:
    value = metadata.get("sidebar_position")

    if isinstance(value, int) and not isinstance(value, bool):
        return value

    return None

def _metadata_description(metadata: Mapping[str, FrontmatterValue]) -> str | None:
    """Return SEO description from frontmatter, if present."""
    value = metadata.get("description")

    if not isinstance(value, str):
        return None

    description = value.strip()

    if description == "":
        return None

    return description


def _title_from_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").strip().title()


def _is_unchanged(
    *,
    existing: CmsArticleRetrieveResponse,
    markdown: str,
    title: str,
    order: int | None,
    description: str | None,
) -> bool:
    existing_markdown = existing.article.markdown or ""
    
    if existing_markdown != markdown:
        return False

    if existing.article.title != title:
        return False

    if order is not None and existing.article.ordr != order:
        return False

    if _normalize_optional_text(existing.article.description) != description:
        return False

    return True

def _normalize_optional_text(value: str | None) -> str | None:
    """Normalize optional CMS text fields for comparison."""
    if value is None:
        return None

    normalized = value.strip()

    if normalized == "":
        return None

    return normalized


def _transform_messages(messages: Sequence[TransformMessage]) -> tuple[SyncMessage, ...]:
    return tuple(
        SyncMessage(
            level=message.level.value,
            code=message.code,
            message=message.message,
        )
        for message in messages
    )


def _failure_result(
    *,
    item: SyncItem,
    dry_run: bool,
    code: str,
    message: str,
) -> SyncFileResult:
    return SyncFileResult(
        source_path=item.source_path,
        target_path=item.target_path,
        action=SyncAction.FAILED,
        status=SyncStatus.FAILURE,
        dry_run=dry_run,
        uploaded=False,
        messages=(
            SyncMessage(
                level=TransformMessageLevel.ERROR.value,
                code=code,
                message=message,
            ),
        ),
    )


def _is_missing_article_error(exc: EledoApiError) -> bool:
    status_code = getattr(exc, "status_code", None)

    if status_code == 404:
        return True

    response = getattr(exc, "response", None)
    response_status_code = getattr(response, "status_code", None)

    if response_status_code == 404:
        return True

    message = str(exc).lower()

    return "invalid path" in message


def _result_to_log_record(result: SyncFileResult) -> dict[str, Any]:
    return {
        "source": result.source_path.as_posix(),
        "target": result.target_path,
        "action": result.action.value,
        "status": result.status.value,
        "dry_run": result.dry_run,
        "uploaded": result.uploaded,
        "title": result.title,
        "order": result.order,
        "messages": [
            {
                "level": message.level,
                "code": message.code,
                "message": message.message,
            }
            for message in result.messages
        ],
    }


def _cms_path_segments(path: str) -> tuple[str, ...]:
    """Split a CMS path such as /documentation/api into path segments."""
    return tuple(part for part in path.strip("/").split("/") if part)


def _parent_paths(path: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """Return parent CMS paths for a target path, from root parent to direct parent."""
    return tuple(path[:index] for index in range(1, len(path)))


async def _ensure_parent_articles(
    *,
    cms: CmsClient,
    target_segments: tuple[str, ...],
    destination_root_segments: tuple[str, ...],
    label: str,
    dry_run: bool,
    messages: list[SyncMessage],
) -> bool:
    """Ensure parent CMS articles exist before creating a child article.

    Destination root must already exist. Intermediate parents may be created
    as empty placeholder articles so deep single-file uploads can succeed.
    """
    for parent_path in _parent_paths(target_segments):
        try:
            await cms.retrieve_article(parent_path)
            continue
        except EledoInvalidResponseError as exc:
            messages.append(
                SyncMessage(
                    level=TransformMessageLevel.ERROR,
                    code="cms_parent_invalid_response",
                    message=f"Invalid CMS response for parent path {_target_path(parent_path)}: {exc}",
                )
            )
            return False
        except EledoApiError as exc:
            if not _is_missing_article_error(exc):
                messages.append(
                    SyncMessage(
                        level=TransformMessageLevel.ERROR,
                        code="cms_parent_check_failed",
                        message=f"Failed to check parent path {_target_path(parent_path)}: {exc}",
                    )
                )
                return False

        if parent_path == destination_root_segments:
            messages.append(
                SyncMessage(
                    level=TransformMessageLevel.ERROR,
                    code="destination_root_missing",
                    message=(
                        f"Destination root {_target_path(parent_path)} does not exist. "
                        "Refusing to create it automatically."
                    ),
                )
            )
            return False

        slug = parent_path[-1]
        action_code = "cms_parent_would_be_created" if dry_run else "cms_parent_created"

        messages.append(
            SyncMessage(
                level=TransformMessageLevel.WARNING,
                code=action_code,
                message=f"Parent path {_target_path(parent_path)} did not exist.",
            )
        )

        if dry_run:
            continue

        try:
            await cms.create_article(
                path=parent_path,
                label=label,
                request=CmsArticleCreateRequest(
                    title=_title_from_slug(slug),
                    slug=slug,
                    markdown="",
                    ord=None,
                ),
            )
        except EledoApiError as exc:
            messages.append(
                SyncMessage(
                    level=TransformMessageLevel.ERROR,
                    code="cms_parent_upload_failed",
                    message=f"Failed to create parent path {_target_path(parent_path)}: {exc}",
                )
            )
            return False

    return True
