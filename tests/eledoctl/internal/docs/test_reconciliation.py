"""Read-only reverse-pull reconciliation of remote-only CMS articles."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from eledoctl.internal.docs.reconciliation import detect_cms_only_articles
from eledoctl.internal.docs.reverse import PullAction, summarize_pull, write_pull_log
from eledoctl.internal.docs.uploader import SyncItem
from pyeledo import EledoApiError
from pyeledo.internal.cms import CmsClient


class FakeCmsClient:
    def __init__(self, children: dict[tuple[str, ...], tuple[str, ...]]) -> None:
        self.children = children
        self.reads: list[tuple[str, ...]] = []

    async def retrieve_article(self, path: tuple[str, ...]) -> SimpleNamespace:
        self.reads.append(path)
        if path not in self.children:
            raise EledoApiError("Invalid path")
        return SimpleNamespace(
            children=tuple(SimpleNamespace(slug=slug) for slug in self.children[path]),
        )


def local_item(root: Path, relative: str) -> SyncItem:
    source = root / relative
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Local\n", encoding="utf-8")
    parts = source.relative_to(root).with_suffix("").parts
    if parts[-1] == "index":
        parts = parts[:-1]
    target = ("documentation", *parts)
    return SyncItem(source, target, "/" + "/".join(target))


@pytest.mark.asyncio
async def test_detects_new_cms_article_and_all_descendants_without_creating_files(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    index = local_item(root, "integrations/monday_com/index.mdx")
    guide = local_item(root, "integrations/monday_com/guide.mdx")
    cms = FakeCmsClient(
        {
            ("documentation",): ("integrations",),
            ("documentation", "integrations"): ("monday_com",),
            ("documentation", "integrations", "monday_com"): ("guide", "introduction"),
            ("documentation", "integrations", "monday_com", "guide"): (),
            ("documentation", "integrations", "monday_com", "introduction"): ("new-subpage",),
            ("documentation", "integrations", "monday_com", "introduction", "new-subpage"): (),
        }
    )
    before = sorted(path.relative_to(root) for path in root.rglob("*.mdx"))
    results = await detect_cms_only_articles(
        cms=cast(CmsClient, cms),
        items=(index, guide),
        source_root=root,
        selection=root,
        destination_root="/documentation",
        dry_run=False,
    )
    assert [row.target_path for row in results] == [
        "/documentation/integrations/monday_com/introduction",
        "/documentation/integrations/monday_com/introduction/new-subpage",
    ]
    assert all(row.action == PullAction.FAILED and row.error_code == "cms_only_article" for row in results)
    assert all(row.source_path is None and not row.written for row in results)
    assert sorted(path.relative_to(root) for path in root.rglob("*.mdx")) == before


@pytest.mark.asyncio
async def test_subtree_scan_does_not_inspect_siblings_and_allows_structural_nodes(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    guide = local_item(root, "api/documents/download.mdx")
    cms = FakeCmsClient(
        {
            ("documentation", "api"): ("documents", "old-page"),
            ("documentation", "api", "documents"): ("download",),
            ("documentation", "api", "documents", "download"): (),
            ("documentation", "api", "old-page"): (),
            ("documentation", "product"): ("unrelated",),
        }
    )
    results = await detect_cms_only_articles(
        cms=cast(CmsClient, cms),
        items=(guide,),
        source_root=root,
        selection=root / "api",
        destination_root="documentation",
        dry_run=True,
    )
    assert [row.target_path for row in results] == ["/documentation/api/old-page"]
    assert all(path[:2] != ("documentation", "product") for path in cms.reads)


@pytest.mark.asyncio
async def test_single_file_selection_does_not_scan_cms_siblings(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    guide = local_item(root, "api/download.mdx")
    cms = FakeCmsClient({})
    assert (
        await detect_cms_only_articles(
            cms=cast(CmsClient, cms),
            items=(guide,),
            source_root=root,
            selection=guide.source_path,
            destination_root="/documentation",
            dry_run=False,
        )
        == ()
    )
    assert cms.reads == []


@pytest.mark.asyncio
async def test_unreadable_remote_hierarchy_produces_failure_not_false_empty_tree(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    guide = local_item(root, "api/download.mdx")
    cms = FakeCmsClient({})
    rows = await detect_cms_only_articles(
        cms=cast(CmsClient, cms),
        items=(guide,),
        source_root=root,
        selection=root / "api",
        destination_root="/documentation",
        dry_run=True,
    )
    assert len(rows) == 1
    assert rows[0].error_code == "cms_tree_read_failed"
    assert rows[0].target_path == "/documentation/api"
    assert rows[0].action == PullAction.FAILED


def test_cms_only_jsonl_result_and_summary_keep_original_local_file_count(tmp_path: Path) -> None:
    from eledoctl.internal.docs.reverse import PullResult

    local = PullResult(tmp_path / "index.mdx", "/documentation", PullAction.UNCHANGED, True, False)
    remote_only = PullResult(
        None,
        "/documentation/new",
        PullAction.FAILED,
        True,
        False,
        ("CMS-only article /documentation/new",),
        error_code="cms_only_article",
    )
    summary = summarize_pull((local, remote_only), dry_run=True)
    assert summary.total == 1
    assert summary.failed == 1
    assert summary.cms_only == 1
    output = tmp_path / "pull.jsonl"
    write_pull_log(output, (local, remote_only))
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert records[1]["source_path"] is None
    assert records[1]["error_code"] == "cms_only_article"
    assert records[1]["status"] == "failure"
