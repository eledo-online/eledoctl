"""Tests for internal documentation pull CLI."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from click.testing import CliRunner

from eledoctl.cli.internal.pull import pull_docs
from eledoctl.config.settings import ConnectionSettings
from eledoctl.internal.docs.reverse import PullAction, PullResult


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
