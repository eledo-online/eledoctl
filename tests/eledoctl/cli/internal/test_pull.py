"""Tests for internal documentation pull CLI."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from click.testing import CliRunner

from eledoctl.cli.internal.pull import _pull_docs, pull_docs
from eledoctl.config.settings import ConnectionSettings
from eledoctl.internal.docs.reverse import PullAction, PullResult
from eledoctl.internal.docs.uploader import SyncItem


def test_pull_reports_dry_run_without_writing(tmp_path: Path, monkeypatch: Any) -> None:
    source_root = tmp_path / "docs"
    source_root.mkdir()
    item = source_root / "api.mdx"
    item.write_text("# API\n", encoding="utf-8")
    log = tmp_path / "pull.jsonl"
    captured: list[dict[str, Any]] = []

    def fake_plan(options: Any) -> Any:
        assert options.source_root == source_root
        assert options.selection == item
        assert options.destination_root == "/docs"
        return SimpleNamespace(source_root=source_root, selection=item, items=(object(),))

    async def fake_pull(**kwargs: Any) -> list[PullResult]:
        captured.append(kwargs)
        return [PullResult(item, "/docs/api", PullAction.UPDATED, True, False)]

    monkeypatch.setattr(
        "eledoctl.cli.internal.pull.require_connection_settings",
        lambda: ConnectionSettings("https://example.test", "test"),
    )
    monkeypatch.setattr("eledoctl.cli.internal.pull.build_sync_plan", fake_plan)
    monkeypatch.setattr("eledoctl.cli.internal.pull._pull_docs", fake_pull)

    output = CliRunner().invoke(
        pull_docs,
        [
            str(source_root),
            str(item),
            "--destination-root",
            "/docs",
            "--dry-run",
            "--log-file",
            str(log),
            "--no-progress",
        ],
    )
    assert output.exit_code == 0, output.output
    assert "updated: 1" in output.output
    assert "failures: 0" in output.output
    assert log.exists()
    assert captured[0]["dry_run"] is True
    assert captured[0]["show_progress"] is False


def test_pull_returns_nonzero_for_unreliable_recovery(tmp_path: Path, monkeypatch: Any) -> None:
    source_root = tmp_path / "docs"
    source_root.mkdir()
    item = source_root / "index.mdx"
    item.write_text("# Docs\n", encoding="utf-8")

    monkeypatch.setattr(
        "eledoctl.cli.internal.pull.require_connection_settings",
        lambda: ConnectionSettings("https://example.test", "test"),
    )
    monkeypatch.setattr(
        "eledoctl.cli.internal.pull.build_sync_plan",
        lambda options: SimpleNamespace(source_root=source_root, selection=item, items=(object(),)),
    )

    async def fake_pull(**kwargs: Any) -> list[PullResult]:
        return [PullResult(item, "/documentation", PullAction.FAILED, True, False, ("Ambiguous link mapping",))]

    monkeypatch.setattr("eledoctl.cli.internal.pull._pull_docs", fake_pull)
    output = CliRunner().invoke(pull_docs, [str(source_root), "--dry-run", "--no-progress"])
    assert output.exit_code != 0
    assert "failures: 1" in output.output
    assert "Ambiguous link mapping" in output.output


def test_pull_is_registered_beside_sync_under_internal_docs() -> None:
    from eledoctl.cli.internal.root import internal_group

    output = CliRunner().invoke(internal_group, ["docs", "pull", "--help"])
    assert output.exit_code == 0, output.output
    assert "--dry-run" in output.output
    assert "--destination-root" in output.output


def test_pull_reports_cms_only_articles_in_summary_and_log(tmp_path: Path, monkeypatch: Any) -> None:
    source_root = tmp_path / "docs"
    source_root.mkdir()
    local_file = source_root / "index.mdx"
    local_file.write_text("# Docs\n", encoding="utf-8")
    log = tmp_path / "pull.jsonl"

    monkeypatch.setattr(
        "eledoctl.cli.internal.pull.require_connection_settings",
        lambda: ConnectionSettings("https://example.test", "token"),
    )
    monkeypatch.setattr(
        "eledoctl.cli.internal.pull.build_sync_plan",
        lambda options: SimpleNamespace(source_root=source_root, selection=source_root, items=(object(),)),
    )

    async def fake_pull(**kwargs: Any) -> list[PullResult]:
        return [
            PullResult(local_file, "/documentation", PullAction.UNCHANGED, True, False),
            PullResult(
                None,
                "/documentation/new",
                PullAction.FAILED,
                True,
                False,
                ("CMS-only article /documentation/new",),
                error_code="cms_only_article",
            ),
        ]

    monkeypatch.setattr("eledoctl.cli.internal.pull._pull_docs", fake_pull)
    output = CliRunner().invoke(
        pull_docs,
        [str(source_root), "--dry-run", "--log-file", str(log), "--no-progress"],
    )
    assert output.exit_code != 0
    assert "total: 1" in output.output
    assert "cms_only: 1" in output.output
    assert "failures: 1" in output.output
    assert "CMS-only article" in output.output
    records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert records[1]["source_path"] is None
    assert records[1]["error_code"] == "cms_only_article"


def test_pull_blocks_changed_cms_index_hierarchy_but_keeps_sibling_pullable(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    root = tmp_path / "docs"
    monday = root / "integrations" / "monday_com"
    monday.mkdir(parents=True)
    index_path = monday / "index.mdx"
    guide_path = monday / "guide.mdx"
    index_path.write_text("# Original index\n", encoding="utf-8")
    guide_path.write_text("# Existing guide\n", encoding="utf-8")
    index = SyncItem(
        index_path, ("documentation", "integrations", "monday_com"), "/documentation/integrations/monday_com"
    )
    guide = SyncItem(
        guide_path,
        ("documentation", "integrations", "monday_com", "guide"),
        "/documentation/integrations/monday_com/guide",
    )

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

    class FakeCms:
        async def retrieve_article(self, path: tuple[str, ...]) -> Any:
            children = {
                index.target_segments: ("guide", "introduction"),
                (*index.target_segments, "guide"): (),
                (*index.target_segments, "introduction"): (),
            }[path]
            return SimpleNamespace(children=tuple(SimpleNamespace(slug=slug) for slug in children))

    pulled: list[Path] = []

    async def fake_pull_one_document(*, cms: Any, item: Any, dry_run: bool) -> PullResult:
        pulled.append(item.source_path)
        return PullResult(item.source_path, item.target_path, PullAction.UNCHANGED, dry_run, False)

    monkeypatch.setattr("eledoctl.cli.internal.pull.EledoClient", FakeClient)
    monkeypatch.setattr("eledoctl.cli.internal.pull.CmsClient", lambda client: FakeCms())
    monkeypatch.setattr("eledoctl.cli.internal.pull.pull_one_document", fake_pull_one_document)
    results = asyncio.run(
        _pull_docs(
            settings=ConnectionSettings("https://example.test", "token"),
            items=(index, guide),
            source_root=root,
            selection=monday,
            destination_root="/documentation",
            dry_run=False,
            show_progress=False,
        )
    )
    assert [row.error_code for row in results if row.action == PullAction.FAILED] == [
        "cms_only_article",
        "cms_hierarchy_changed",
    ]
    assert pulled == [guide_path]
    assert index_path.read_text(encoding="utf-8") == "# Original index\n"
