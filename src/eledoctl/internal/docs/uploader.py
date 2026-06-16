"""Internal documentation uploader for syncing source Markdown into Eledo CMS."""

from __future__ import annotations

import json
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

DOC_EXTENSIONS = {".md", ".mdx"}


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

    items = tuple(
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

    _validate_unique_targets(items)

    return SyncPlan(
        source_root=source_root,
        selection=selection,
        items=items,
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
        existing = await cms.retrieve_article(item.target_segments)
        reference_doc = existing.article.markdown
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

    messages = _transform_messages(transform_result.messages)

    title = _metadata_title(transform_result.metadata, item)
    order = _metadata_order(transform_result.metadata)

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
            messages=messages,
        )

    status = SyncStatus.WARNING if transform_result.status == TransformStatus.WARNING else SyncStatus.SUCCESS

    if (
        existing is not None
        and options.skip_unchanged
        and _is_unchanged(
            existing=existing,
            markdown=transform_result.content,
            title=title,
            order=order,
        )
    ):
        return SyncFileResult(
            source_path=item.source_path,
            target_path=item.target_path,
            action=SyncAction.SKIP_UNCHANGED,
            status=status,
            dry_run=options.dry_run,
            uploaded=False,
            title=title,
            order=order,
            messages=messages,
        )

    if options.dry_run:
        return SyncFileResult(
            source_path=item.source_path,
            target_path=item.target_path,
            action=SyncAction.UPDATE if existing is not None else SyncAction.CREATE,
            status=status,
            dry_run=True,
            uploaded=False,
            title=title,
            order=order,
            messages=messages,
        )

    try:
        if existing is None:
            await cms.create_article(
                path=item.target_segments,
                label=options.tag,
                request=CmsArticleCreateRequest(
                    title=title,
                    slug=item.target_segments[-1],
                    ord=order,
                    markdown=transform_result.content,
                ),
            )
            action = SyncAction.CREATE
        else:
            await cms.update_article(
                path=item.target_segments,
                label=options.tag,
                request=CmsArticleUpdateRequest(
                    title=title,
                    slug=item.target_segments[-1],
                    ordr=order,
                    markdown=transform_result.content,
                ),
            )
            action = SyncAction.UPDATE
    except EledoApiError as exc:
        return SyncFileResult(
            source_path=item.source_path,
            target_path=item.target_path,
            action=SyncAction.FAILED,
            status=SyncStatus.FAILURE,
            dry_run=options.dry_run,
            uploaded=False,
            title=title,
            order=order,
            messages=(
                *messages,
                SyncMessage(
                    level=TransformMessageLevel.ERROR.value,
                    code="cms_upload_failed",
                    message=str(exc),
                ),
            ),
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
        messages=messages,
    )


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
    return path.is_file() and path.suffix.lower() in DOC_EXTENSIONS


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

    return (*destination_segments, *parts)


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
    value = metadata.get("title")

    if isinstance(value, str) and value.strip():
        return value.strip()

    return _title_from_slug(item.target_segments[-1])


def _metadata_order(metadata: Mapping[str, FrontmatterValue]) -> int | None:
    value = metadata.get("sidebar_position")

    if isinstance(value, int) and not isinstance(value, bool):
        return value

    return None


def _title_from_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").strip().title()


def _is_unchanged(
    *,
    existing: CmsArticleRetrieveResponse,
    markdown: str,
    title: str,
    order: int | None,
) -> bool:
    if existing.article.markdown != markdown:
        return False

    if existing.article.title != title:
        return False

    return not (order is not None and existing.article.ordr != order)


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
