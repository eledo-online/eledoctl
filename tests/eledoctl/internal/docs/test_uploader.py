from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from eledoctl.internal.docs.uploader import (
    SyncAction,
    SyncOptions,
    SyncStatus,
    build_sync_plan,
    summarize_results,
    sync_one_document,
    write_inspection_file,
    write_log_file,
)
from pyeledo import EledoApiError, EledoInvalidResponseError
from pyeledo.internal.cms import CmsArticle, CmsArticleRetrieveResponse


class FakeCmsClient:
    def __init__(self, existing: dict[tuple[str, ...], CmsArticleRetrieveResponse] | None = None) -> None:
        self.existing = existing or {}
        self.created: list[dict[str, Any]] = []
        self.updated: list[dict[str, Any]] = []

    async def retrieve_article(self, path: tuple[str, ...]) -> CmsArticleRetrieveResponse:
        try:
            return self.existing[path]
        except KeyError as exc:
            raise FakeNotFoundError("not found") from exc

    async def create_article(self, *, path: tuple[str, ...], request: Any, label: str | None = None) -> dict[str, Any]:
        self.created.append({"path": path, "request": request, "label": label})
        return {"ok": True}

    async def update_article(self, *, path: tuple[str, ...], request: Any, label: str | None = None) -> dict[str, Any]:
        self.updated.append({"path": path, "request": request, "label": label})
        return {"ok": True}


class FakeMalformedCmsClient(FakeCmsClient):
    async def retrieve_article(self, path: tuple[str, ...]) -> CmsArticleRetrieveResponse:
        raise EledoInvalidResponseError("Invalid Articles API response: expected article.markdown string.")


class FakeNotFoundError(EledoApiError):
    status_code = 404


def article_response(
    *,
    path_slug: str,
    title: str,
    markdown: str,
    ordr: int = 1,
) -> CmsArticleRetrieveResponse:
    return CmsArticleRetrieveResponse(
        article=CmsArticle(
            id="article-id",
            version=1,
            title=title,
            slug=path_slug,
            parent_id=None,
            ordr=ordr,
            published=False,
            platform=None,
            nomenu=False,
            index=False,
            description=None,
            markdown=markdown,
        ),
        children=(),
    )


def write_file(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def sync_options(root: Path, *, dry_run: bool = False, skip_unchanged: bool = True) -> SyncOptions:
    return SyncOptions(
        source_root=root,
        selection=None,
        destination_root="/documentation",
        tag="test-sync",
        dry_run=dry_run,
        skip_unchanged=skip_unchanged,
    )


def test_build_sync_plan_maps_regular_mdx_file_to_destination_path(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    write_file(root / "api" / "documents" / "download.mdx", "# Download\n")

    plan = build_sync_plan(sync_options(root))

    assert len(plan.items) == 1
    assert plan.items[0].source_path == (root / "api" / "documents" / "download.mdx").resolve()
    assert plan.items[0].target_segments == ("documentation", "api", "documents", "download")
    assert plan.items[0].target_path == "/documentation/api/documents/download"


def test_build_sync_plan_maps_index_file_to_parent_destination_path(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    write_file(root / "api" / "documents" / "index.mdx", "# Documents\n")

    plan = build_sync_plan(sync_options(root))

    assert len(plan.items) == 1
    assert plan.items[0].target_segments == ("documentation", "api", "documents")
    assert plan.items[0].target_path == "/documentation/api/documents"


def test_build_sync_plan_maps_root_index_to_destination_root(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    write_file(root / "index.mdx", "# Documentation\n")

    plan = build_sync_plan(sync_options(root))

    assert len(plan.items) == 1
    assert plan.items[0].target_segments == ("documentation",)
    assert plan.items[0].target_path == "/documentation"


def test_build_sync_plan_supports_directory_selection(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    write_file(root / "api" / "documents" / "download.mdx", "# Download\n")
    write_file(root / "guides" / "make.mdx", "# Make\n")

    options = SyncOptions(
        source_root=root,
        selection=root / "api",
        destination_root="/documentation",
        tag="test-sync",
    )

    plan = build_sync_plan(options)

    assert [item.target_path for item in plan.items] == ["/documentation/api/documents/download"]


def test_build_sync_plan_supports_single_file_selection(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    selected = write_file(root / "api" / "documents" / "download.mdx", "# Download\n")
    write_file(root / "guides" / "make.mdx", "# Make\n")

    options = SyncOptions(
        source_root=root,
        selection=selected,
        destination_root="/documentation",
        tag="test-sync",
    )

    plan = build_sync_plan(options)

    assert len(plan.items) == 1
    assert plan.items[0].target_path == "/documentation/api/documents/download"


def test_build_sync_plan_rejects_selection_outside_source_root(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()

    options = SyncOptions(
        source_root=root,
        selection=outside,
        destination_root="/documentation",
        tag="test-sync",
    )

    with pytest.raises(ValueError, match="Selection must be inside source root"):
        build_sync_plan(options)


def test_build_sync_plan_rejects_duplicate_target_paths(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    write_file(root / "api" / "documents.mdx", "# Documents\n")
    write_file(root / "api" / "documents" / "index.mdx", "# Documents Index\n")

    with pytest.raises(ValueError, match="same CMS target path"):
        build_sync_plan(sync_options(root))


@pytest.mark.asyncio
async def test_sync_one_document_creates_missing_article(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "docs"
    write_file(
        root / "api" / "documents" / "download.mdx",
        """---
title: Download
sidebar_position: 5
---

# Download
""",
    )
    plan = build_sync_plan(sync_options(root))
    cms = FakeCmsClient()

    monkeypatch.setattr("eledoctl.internal.docs.uploader._is_not_found_error", lambda exc: True)

    result = await sync_one_document(cms=cms, item=plan.items[0], options=sync_options(root))

    assert result.action == SyncAction.CREATE
    assert result.status == SyncStatus.WARNING
    assert result.uploaded is True
    assert result.title == "Download"
    assert result.order == 5

    assert len(cms.created) == 1
    created = cms.created[0]
    assert created["path"] == ("documentation", "api", "documents", "download")
    assert created["label"] == "test-sync"
    assert created["request"].title == "Download"
    assert created["request"].slug == "download"
    assert created["request"].ord == 5
    assert created["request"].markdown == "# Download\n"

    assert cms.updated == []


@pytest.mark.asyncio
async def test_sync_one_document_updates_existing_article(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    write_file(
        root / "api" / "documents" / "download.mdx",
        """---
title: Download
sidebar_position: 5
---

# Download v2
""",
    )
    plan = build_sync_plan(sync_options(root))
    existing = {
        ("documentation", "api", "documents", "download"): article_response(
            path_slug="download",
            title="Download",
            markdown="# Download v1\n",
            ordr=5,
        )
    }
    cms = FakeCmsClient(existing)

    result = await sync_one_document(cms=cms, item=plan.items[0], options=sync_options(root))

    assert result.action == SyncAction.UPDATE
    assert result.status == SyncStatus.SUCCESS
    assert result.uploaded is True

    assert cms.created == []
    assert len(cms.updated) == 1
    updated = cms.updated[0]
    assert updated["path"] == ("documentation", "api", "documents", "download")
    assert updated["label"] == "test-sync"
    assert updated["request"].title == "Download"
    assert updated["request"].slug == "download"
    assert updated["request"].ordr == 5
    assert updated["request"].markdown == "# Download v2\n"


@pytest.mark.asyncio
async def test_sync_one_document_skips_unchanged_existing_article(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    write_file(
        root / "api" / "documents" / "download.mdx",
        """---
title: Download
sidebar_position: 5
---

# Download
""",
    )
    plan = build_sync_plan(sync_options(root))
    existing = {
        ("documentation", "api", "documents", "download"): article_response(
            path_slug="download",
            title="Download",
            markdown="# Download\n",
            ordr=5,
        )
    }
    cms = FakeCmsClient(existing)

    result = await sync_one_document(cms=cms, item=plan.items[0], options=sync_options(root))

    assert result.action == SyncAction.SKIP_UNCHANGED
    assert result.status == SyncStatus.SUCCESS
    assert result.uploaded is False
    assert cms.created == []
    assert cms.updated == []


@pytest.mark.asyncio
async def test_sync_one_document_updates_unchanged_content_when_order_changed(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    write_file(
        root / "api" / "documents" / "download.mdx",
        """---
title: Download
sidebar_position: 7
---

# Download
""",
    )
    plan = build_sync_plan(sync_options(root))
    existing = {
        ("documentation", "api", "documents", "download"): article_response(
            path_slug="download",
            title="Download",
            markdown="# Download\n",
            ordr=5,
        )
    }
    cms = FakeCmsClient(existing)

    result = await sync_one_document(cms=cms, item=plan.items[0], options=sync_options(root))

    assert result.action == SyncAction.UPDATE
    assert result.status == SyncStatus.SUCCESS
    assert result.uploaded is True
    assert len(cms.updated) == 1
    assert cms.updated[0]["request"].ordr == 7


@pytest.mark.asyncio
async def test_sync_one_document_dry_run_does_not_upload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "docs"
    write_file(root / "api" / "documents" / "download.mdx", "# Download\n")
    plan = build_sync_plan(sync_options(root, dry_run=True))
    cms = FakeCmsClient()

    monkeypatch.setattr("eledoctl.internal.docs.uploader._is_not_found_error", lambda exc: True)

    result = await sync_one_document(
        cms=cms,
        item=plan.items[0],
        options=sync_options(root, dry_run=True),
    )

    assert result.action == SyncAction.CREATE
    assert result.status == SyncStatus.WARNING
    assert result.dry_run is True
    assert result.uploaded is False
    assert cms.created == []
    assert cms.updated == []


def test_summarize_results_counts_actions_and_statuses(tmp_path: Path) -> None:
    results = [
        _result(tmp_path, action=SyncAction.CREATE, status=SyncStatus.SUCCESS),
        _result(tmp_path, action=SyncAction.UPDATE, status=SyncStatus.WARNING),
        _result(tmp_path, action=SyncAction.SKIP_UNCHANGED, status=SyncStatus.SUCCESS),
        _result(tmp_path, action=SyncAction.FAILED, status=SyncStatus.FAILURE),
    ]

    summary = summarize_results(results, dry_run=True)

    assert summary.total == 4
    assert summary.created == 1
    assert summary.updated == 1
    assert summary.skipped == 1
    assert summary.warnings == 1
    assert summary.failures == 1
    assert summary.dry_run is True


def test_write_log_file_writes_json_lines(tmp_path: Path) -> None:
    log_file = tmp_path / "logs" / "sync.jsonl"
    results = [_result(tmp_path, action=SyncAction.CREATE, status=SyncStatus.SUCCESS)]

    write_log_file(log_file, results)

    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["action"] == "create"
    assert record["status"] == "success"
    assert record["target"] == "/documentation/test"


def test_write_inspection_file_writes_only_warning_and_failure_results(tmp_path: Path) -> None:
    inspect_file = tmp_path / "inspect.txt"
    success = _result(tmp_path, action=SyncAction.CREATE, status=SyncStatus.SUCCESS)
    warning = _result(tmp_path, action=SyncAction.UPDATE, status=SyncStatus.WARNING)
    failure = _result(tmp_path, action=SyncAction.FAILED, status=SyncStatus.FAILURE)

    write_inspection_file(inspect_file, [success, warning, failure])

    content = inspect_file.read_text(encoding="utf-8")

    assert "status: success" not in content
    assert "status: warning" in content
    assert "status: failure" in content


def _result(tmp_path: Path, *, action: SyncAction, status: SyncStatus):
    from eledoctl.internal.docs.uploader import SyncFileResult

    return SyncFileResult(
        source_path=tmp_path / f"{action.value}.mdx",
        target_path="/documentation/test",
        action=action,
        status=status,
        dry_run=False,
        uploaded=action in {SyncAction.CREATE, SyncAction.UPDATE},
    )


@pytest.mark.asyncio
async def test_sync_one_document_marks_invalid_cms_reference_response_as_failure(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    write_file(
        root / "api" / "documents" / "malformed.mdx",
        """---
title: Malformed
sidebar_position: 9
---

# Malformed
""",
    )
    plan = build_sync_plan(sync_options(root))
    cms = FakeMalformedCmsClient()

    result = await sync_one_document(
        cms=cms,
        item=plan.items[0],
        options=sync_options(root),
    )

    assert result.action == SyncAction.FAILED
    assert result.status == SyncStatus.FAILURE
    assert result.uploaded is False
    assert result.requires_inspection is True

    assert len(result.messages) == 1
    assert result.messages[0].level == "error"
    assert result.messages[0].code == "cms_invalid_reference_response"
    assert "expected article.markdown string" in result.messages[0].message

    assert cms.created == []
    assert cms.updated == []
