from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from eledoctl.internal.docs.uploader import (
    SyncAction,
    SyncItem,
    SyncMessage,
    SyncOptions,
    SyncStatus,
    TransformStatus,
    _ensure_parent_articles,
    _metadata_title,
    build_sync_plan,
    summarize_results,
    sync_missing_cms_children,
    sync_one_document,
    write_inspection_file,
    write_log_file,
)
from pyeledo import EledoApiError, EledoInvalidResponseError
from pyeledo.internal.cms import CmsArticle, CmsArticleChild, CmsArticleCreateRequest, CmsArticleRetrieveResponse


class FakeCmsClient:
    def __init__(self, existing: dict[tuple[str, ...], CmsArticleRetrieveResponse] | None = None) -> None:
        self.existing = existing or {}
        self.created: list[dict[str, Any]] = []
        self.updated: list[dict[str, Any]] = []

    async def retrieve_article(self, path: tuple[str, ...]) -> CmsArticleRetrieveResponse:
        try:
            return self.existing[path]
        except KeyError as exc:
            raise FakeInvalidPathError("Invalid path") from exc

    async def create_article(
        self,
        *,
        path: tuple[str, ...],
        request: Any,
        label: str | None = None,
    ) -> dict[str, Any]:
        self.created.append({"path": path, "request": request, "label": label})

        self.existing[path] = cms_response(
            title=request.title,
            slug=request.slug,
            markdown=request.markdown,
            ordr=getattr(request, "ord", None),
        )

        return {"ok": True}

    async def update_article(
        self,
        *,
        path: tuple[str, ...],
        request: Any,
        label: str | None = None,
    ) -> dict[str, Any]:
        self.updated.append({"path": path, "request": request, "label": label})

        existing = self.existing.get(path)

        self.existing[path] = cms_response(
            title=request.title,
            slug=request.slug,
            markdown=request.markdown,
            ordr=getattr(request, "ordr", None),
            description=getattr(request, "description", None),
            published=getattr(request, "published", None)
            if getattr(request, "published", None) is not None
            else (existing.article.published if existing is not None else True),
            children=existing.children if existing is not None else (),
        )

        return {"ok": True}


class FakeMalformedCmsClient(FakeCmsClient):
    async def retrieve_article(self, path: tuple[str, ...]) -> CmsArticleRetrieveResponse:
        raise EledoInvalidResponseError("Invalid Articles API response: expected article.markdown string.")


class FakeNotFoundError(EledoApiError):
    status_code = 404


class FakeInvalidPathError(EledoApiError):
    def __init__(self, message: str) -> None:
        Exception.__init__(self, message)


class FakeParentCmsClient:
    def __init__(self, existing_paths: set[tuple[str, ...]]) -> None:
        self.existing_paths = set(existing_paths)
        self.created: list[tuple[tuple[str, ...], str | None, CmsArticleCreateRequest]] = []

    async def retrieve_article(self, path: tuple[str, ...]) -> object:
        if path in self.existing_paths:
            return object()

        raise EledoApiError("Invalid path")

    async def create_article(
        self,
        path: tuple[str, ...],
        *,
        label: str | None = None,
        request: CmsArticleCreateRequest,
    ) -> object:
        self.existing_paths.add(path)
        self.created.append((path, label, request))
        return object()


def cms_response(
    *,
    title: str,
    slug: str,
    markdown: str | None,
    ordr: int | None = None,
    description: str | None = None,
    published: bool = True,
    children: Sequence[CmsArticleChild] = (),
) -> CmsArticleRetrieveResponse:
    return CmsArticleRetrieveResponse(
        article=CmsArticle(
            id=f"article-{slug}",
            version=1,
            title=title,
            slug=slug,
            parent_id=None,
            ordr=ordr or 0,
            published=published,
            platform=None,
            nomenu=False,
            index=False,
            description=description,
            markdown=markdown,
        ),
        children=tuple(children),
    )


def cms_child(*, slug: str) -> CmsArticleChild:
    return CmsArticleChild(
        id=f"child-{slug}",
        version=1,
        slug=slug,
    )


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
    cms = FakeCmsClient(
        existing={
            ("documentation",): cms_response(
                title="Documentation",
                slug="documentation",
                markdown="",
                ordr=0,
            ),
            ("documentation", "api"): cms_response(
                title="Api",
                slug="api",
                markdown="",
                ordr=0,
            ),
            ("documentation", "api", "documents"): cms_response(
                title="Documents",
                slug="documents",
                markdown="",
                ordr=0,
            ),
        }
    )

    monkeypatch.setattr("eledoctl.internal.docs.uploader._is_missing_article_error", lambda exc: True)

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
    cms = FakeCmsClient(
        existing={
            ("documentation",): cms_response(
                title="Documentation",
                slug="documentation",
                markdown="",
                ordr=0,
            ),
            ("documentation", "api"): cms_response(
                title="Api",
                slug="api",
                markdown="",
                ordr=0,
            ),
            ("documentation", "api", "documents"): cms_response(
                title="Documents",
                slug="documents",
                markdown="",
                ordr=0,
            ),
        }
    )

    monkeypatch.setattr("eledoctl.internal.docs.uploader._is_missing_article_error", lambda exc: True)

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


@pytest.mark.asyncio
async def test_sync_one_document_treats_invalid_path_retrieve_error_as_missing_article(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "docs"
    write_file(root / "api" / "documents" / "download.mdx", "# Download\n")

    plan = build_sync_plan(sync_options(root))
    item = plan.items[0]

    cms = FakeCmsClient(
        existing={
            ("documentation",): cms_response(
                title="Documentation",
                slug="documentation",
                markdown="",
                ordr=0,
            ),
            ("documentation", "api"): cms_response(
                title="Api",
                slug="api",
                markdown="",
                ordr=0,
            ),
            ("documentation", "api", "documents"): cms_response(
                title="Documents",
                slug="documents",
                markdown="",
                ordr=0,
            ),
        }
    )

    original_retrieve_article = cms.retrieve_article

    async def fake_retrieve_article(path: tuple[str, ...]) -> CmsArticleRetrieveResponse:
        if path == item.target_segments:
            raise FakeInvalidPathError("Invalid path")

        return await original_retrieve_article(path)

    monkeypatch.setattr(cms, "retrieve_article", fake_retrieve_article)

    result = await sync_one_document(
        cms=cms,
        item=item,
        options=sync_options(root),
    )

    assert result.action == SyncAction.CREATE
    assert result.status == SyncStatus.WARNING
    assert result.uploaded is True

    assert len(cms.created) == 1
    assert cms.created[0]["path"] == ("documentation", "api", "documents", "download")
    assert cms.updated == []


@pytest.mark.asyncio
async def test_ensure_parent_articles_creates_missing_intermediate_parents() -> None:
    cms = FakeParentCmsClient(existing_paths={("documentation",)})
    messages: list[SyncMessage] = []

    result = await _ensure_parent_articles(
        cms=cms,  # type: ignore[arg-type]
        target_segments=("documentation", "api", "documents", "download"),
        destination_root_segments=("documentation",),
        label="docs-sync-test",
        dry_run=False,
        messages=messages,
    )

    assert result is True

    assert [created[0] for created in cms.created] == [
        ("documentation", "api"),
        ("documentation", "api", "documents"),
    ]

    assert [created[1] for created in cms.created] == [
        "docs-sync-test",
        "docs-sync-test",
    ]

    assert cms.created[0][2].slug == "api"
    assert cms.created[0][2].title == "Api"
    assert cms.created[0][2].markdown == ""
    assert cms.created[0][2].ord is None

    assert cms.created[1][2].slug == "documents"
    assert cms.created[1][2].title == "Documents"
    assert cms.created[1][2].markdown == ""
    assert cms.created[1][2].ord is None

    assert [message.code for message in messages] == [
        "cms_parent_created",
        "cms_parent_created",
    ]


@pytest.mark.asyncio
async def test_ensure_parent_articles_refuses_to_create_destination_root() -> None:
    cms = FakeParentCmsClient(existing_paths=set())
    messages: list[SyncMessage] = []

    result = await _ensure_parent_articles(
        cms=cms,  # type: ignore[arg-type]
        target_segments=("documentation", "api", "documents", "download"),
        destination_root_segments=("documentation",),
        label="docs-sync-test",
        dry_run=False,
        messages=messages,
    )

    assert result is False
    assert cms.created == []

    assert [message.code for message in messages] == [
        "destination_root_missing",
    ]


@pytest.mark.asyncio
async def test_sync_one_document_fails_when_destination_root_is_missing(tmp_path: Path) -> None:
    source_root = tmp_path / "docs"
    source_root.mkdir()

    source_file = source_root / "download.mdx"
    source_file.write_text(
        "---\ntitle: Download\nsidebar_position: 4\n---\n\n# Download\n",
        encoding="utf-8",
    )

    item = SyncItem(
        source_path=source_file,
        target_segments=("documentation", "download"),
        target_path="/documentation/download",
    )

    cms = FakeCmsClient(existing=None)

    result = await sync_one_document(
        cms=cms,  # type: ignore[arg-type]
        item=item,
        options=SyncOptions(
            source_root=source_root,
            selection=source_file,
            destination_root="/documentation",
            tag="docs-sync-test",
        ),
    )

    assert result.action == SyncAction.FAILED
    assert result.status == TransformStatus.FAILURE
    assert result.uploaded is False
    assert [message.code for message in result.messages] == [
        "missing_reference_doc",
        "destination_root_missing",
    ]


@pytest.mark.asyncio
async def test_sync_one_document_creates_missing_intermediate_parents(tmp_path: Path) -> None:
    source_root = tmp_path / "docs"
    source_file = source_root / "api" / "documents" / "download.mdx"
    source_file.parent.mkdir(parents=True)

    source_file.write_text(
        "---\ntitle: Download\nsidebar_position: 4\n---\n\n# Download\n",
        encoding="utf-8",
    )

    item = SyncItem(
        source_path=source_file,
        target_segments=("documentation", "api", "documents", "download"),
        target_path="/documentation/api/documents/download",
    )

    cms = FakeCmsClient(
        existing={
            ("documentation",): cms_response(
                title="Documentation",
                slug="documentation",
                markdown="",
                ordr=None,
            ),
        }
    )

    result = await sync_one_document(
        cms=cms,  # type: ignore[arg-type]
        item=item,
        options=SyncOptions(
            source_root=source_root,
            selection=source_file,
            destination_root="/documentation",
            tag="docs-sync-test",
        ),
    )

    assert result.action == SyncAction.CREATE
    assert result.uploaded is True

    assert [entry["path"] for entry in cms.created] == [
        ("documentation", "api"),
        ("documentation", "api", "documents"),
        ("documentation", "api", "documents", "download"),
    ]

    assert [entry["request"].markdown for entry in cms.created] == [
        "",
        "",
        "# Download\n",
    ]


@pytest.mark.asyncio
async def test_sync_one_document_updates_when_description_changes(tmp_path: Path) -> None:
    root = tmp_path / "docs"

    write_file(
        root / "api" / "authentication.mdx",
        (
            "---\n"
            "title: Authentication\n"
            "sidebar_position: 2\n"
            "description: New SEO description.\n"
            "---\n\n"
            "# Authentication\n"
        ),
    )

    plan = build_sync_plan(sync_options(root))
    item = plan.items[0]

    cms = FakeCmsClient(
        existing={
            item.target_segments: cms_response(
                title="Authentication",
                slug="authentication",
                markdown="# Authentication\n",
                ordr=2,
                description="Old SEO description.",
            ),
        }
    )

    result = await sync_one_document(
        cms=cms,
        item=item,
        options=sync_options(root),
    )

    assert result.action == SyncAction.UPDATE
    assert result.uploaded is True
    assert cms.created == []
    assert len(cms.updated) == 1
    assert cms.updated[0]["request"].description == "New SEO description."


def test_metadata_title_uses_category_label_for_index_document(tmp_path: Path) -> None:
    directory = tmp_path / "docs" / "integrations" / "make"
    directory.mkdir(parents=True)

    source_path = directory / "index.mdx"
    source_path.write_text("---\ntitle: Overview\n---\n\n# Overview\n", encoding="utf-8")

    (directory / "_category_.yml").write_text(
        "label: Make\nposition: 2\n",
        encoding="utf-8",
    )

    item = SyncItem(
        source_path=source_path,
        target_segments=("documentation", "integrations", "make"),
        target_path="/documentation/integrations/make",
    )

    assert _metadata_title({"title": "Overview"}, item) == "Make"


def test_metadata_title_uses_target_segment_for_index_without_category(tmp_path: Path) -> None:
    directory = tmp_path / "docs" / "integrations" / "make"
    directory.mkdir(parents=True)

    source_path = directory / "index.mdx"
    source_path.write_text("---\ntitle: Overview\n---\n\n# Overview\n", encoding="utf-8")

    item = SyncItem(
        source_path=source_path,
        target_segments=("documentation", "integrations", "make"),
        target_path="/documentation/integrations/make",
    )

    assert _metadata_title({"title": "Overview"}, item) == "Make"


def test_metadata_title_uses_frontmatter_for_non_index_document(tmp_path: Path) -> None:
    source_path = tmp_path / "docs" / "api" / "authentication.mdx"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("---\ntitle: Authentication\n---\n\n# Authentication\n", encoding="utf-8")

    item = SyncItem(
        source_path=source_path,
        target_segments=("documentation", "api", "authentication"),
        target_path="/documentation/api/authentication",
    )

    assert _metadata_title({"title": "Authentication"}, item) == "Authentication"


@pytest.mark.asyncio
async def test_sync_missing_cms_children_dry_run_reports_stale_child(tmp_path: Path) -> None:
    source_root = tmp_path / "docs"
    write_file(source_root / "api" / "authentication.mdx", "# Authentication\n")

    plan = build_sync_plan(
        SyncOptions(
            source_root=source_root,
            selection=source_root / "api",
            destination_root="/documentation",
            tag="docs-sync-test",
            dry_run=True,
            unpublish_missing=True,
        )
    )

    cms = FakeCmsClient(
        existing={
            ("documentation", "api"): cms_response(
                title="Api",
                slug="api",
                markdown="# API\n",
                children=(
                    cms_child(slug="authentication"),
                    cms_child(slug="old-page"),
                ),
            ),
            ("documentation", "api", "authentication"): cms_response(
                title="Authentication",
                slug="authentication",
                markdown="# Authentication\n",
            ),
            ("documentation", "api", "old-page"): cms_response(
                title="Old Page",
                slug="old-page",
                markdown="# Old Page\n",
            ),
        }
    )

    results = await sync_missing_cms_children(
        cms=cms,  # type: ignore[arg-type]
        items=plan.items,
        options=SyncOptions(
            source_root=source_root,
            selection=source_root / "api",
            destination_root="/documentation",
            tag="docs-sync-test",
            dry_run=True,
            unpublish_missing=True,
        ),
    )

    assert len(results) == 1

    result = results[0]

    assert result.source_path is None
    assert result.target_path == "/documentation/api/old-page"
    assert result.action == SyncAction.UNPUBLISH
    assert result.status == SyncStatus.WARNING
    assert result.dry_run is True
    assert result.uploaded is False
    assert [message.code for message in result.messages] == [
        "cms_child_would_be_unpublished",
    ]

    assert cms.updated == []


@pytest.mark.asyncio
async def test_sync_missing_cms_children_unpublishes_stale_child(tmp_path: Path) -> None:
    source_root = tmp_path / "docs"
    write_file(source_root / "api" / "authentication.mdx", "# Authentication\n")

    options = SyncOptions(
        source_root=source_root,
        selection=source_root / "api",
        destination_root="/documentation",
        tag="docs-sync-test",
        dry_run=False,
        unpublish_missing=True,
    )

    plan = build_sync_plan(options)

    cms = FakeCmsClient(
        existing={
            ("documentation", "api"): cms_response(
                title="Api",
                slug="api",
                markdown="# API\n",
                children=(
                    cms_child(slug="authentication"),
                    cms_child(slug="old-page"),
                ),
            ),
            ("documentation", "api", "authentication"): cms_response(
                title="Authentication",
                slug="authentication",
                markdown="# Authentication\n",
            ),
            ("documentation", "api", "old-page"): cms_response(
                title="Old Page",
                slug="old-page",
                markdown="# Old Page\n",
                published=True,
            ),
        }
    )

    results = await sync_missing_cms_children(
        cms=cms,  # type: ignore[arg-type]
        items=plan.items,
        options=options,
    )

    assert len(results) == 1

    result = results[0]

    assert result.source_path is None
    assert result.target_path == "/documentation/api/old-page"
    assert result.action == SyncAction.UNPUBLISH
    assert result.status == SyncStatus.WARNING
    assert result.dry_run is False
    assert result.uploaded is True

    assert len(cms.updated) == 1
    assert cms.updated[0]["path"] == ("documentation", "api", "old-page")
    assert cms.updated[0]["request"].published is False


@pytest.mark.asyncio
async def test_sync_missing_cms_children_skips_single_file_selection(tmp_path: Path) -> None:
    source_root = tmp_path / "docs"
    source_file = source_root / "api" / "authentication.mdx"
    write_file(source_file, "# Authentication\n")

    options = SyncOptions(
        source_root=source_root,
        selection=source_file,
        destination_root="/documentation",
        tag="docs-sync-test",
        dry_run=False,
        unpublish_missing=True,
    )

    plan = build_sync_plan(options)

    cms = FakeCmsClient(
        existing={
            ("documentation", "api"): cms_response(
                title="Api",
                slug="api",
                markdown="# API\n",
                children=(
                    cms_child(slug="authentication"),
                    cms_child(slug="old-page"),
                ),
            ),
            ("documentation", "api", "old-page"): cms_response(
                title="Old Page",
                slug="old-page",
                markdown="# Old Page\n",
            ),
        }
    )

    results = await sync_missing_cms_children(
        cms=cms,  # type: ignore[arg-type]
        items=plan.items,
        options=options,
    )

    assert results == ()
    assert cms.updated == []
