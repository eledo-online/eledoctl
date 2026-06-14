from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from click.testing import CliRunner

from eledoctl.cli.internal.docs import (
    _is_ci_environment,
    _should_show_progress,
    _transform_options,
    _validate_tag,
    sync_docs,
)
from eledoctl.config.settings import ConnectionSettings
from eledoctl.internal.docs.uploader import SyncAction, SyncFileResult, SyncStatus


def test_validate_tag_strips_value() -> None:
    assert _validate_tag("  docs-sync  ") == "docs-sync"


def test_validate_tag_rejects_empty_value() -> None:
    try:
        _validate_tag("   ")
    except Exception as exc:
        assert "Tag cannot be empty" in str(exc)
    else:
        raise AssertionError("Expected empty tag to fail.")


def test_transform_options_disables_selected_transforms() -> None:
    options = _transform_options(("remove-imports", "patch-links-from-reference"))

    assert options.normalize_line_endings is True
    assert options.strip_frontmatter is True
    assert options.remove_imports is False
    assert options.convert_admonitions is True
    assert options.convert_supported_images is True
    assert options.remove_unsupported_jsx is True
    assert options.patch_links_from_reference is False
    assert options.patch_images_from_reference is True


def test_is_ci_environment_detects_ci(monkeypatch) -> None:
    monkeypatch.setenv("CI", "true")

    assert _is_ci_environment() is True


def test_is_ci_environment_detects_github_actions(monkeypatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    assert _is_ci_environment() is True


def test_is_ci_environment_returns_false_without_ci_vars(monkeypatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    assert _is_ci_environment() is False


def test_should_show_progress_returns_false_in_ci(monkeypatch) -> None:
    monkeypatch.setenv("CI", "true")

    assert _should_show_progress() is False


def test_sync_docs_requires_tag(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()

    runner = CliRunner()
    result = runner.invoke(sync_docs, [str(root)])

    assert result.exit_code != 0
    assert "Missing option '--tag'" in result.output


def test_sync_docs_runs_uploader_and_prints_summary(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "index.mdx").write_text("# Documentation\n", encoding="utf-8")

    fake_item = object()
    fake_results = [
        SyncFileResult(
            source_path=root / "index.mdx",
            target_path="/documentation",
            action=SyncAction.CREATE,
            status=SyncStatus.SUCCESS,
            dry_run=True,
            uploaded=False,
        )
    ]

    class FakePlan:
        source_root = root
        selection = root
        items = (fake_item,)

    captured_options: list[Any] = []

    def fake_build_sync_plan(options: Any) -> FakePlan:
        captured_options.append(options)
        return FakePlan()

    async def fake_sync_docs(**kwargs: Any) -> list[SyncFileResult]:
        assert kwargs["settings"] == ConnectionSettings(base_url="https://example.com", token="token")
        assert kwargs["options"].tag == "docs-sync"
        assert kwargs["options"].dry_run is True
        assert kwargs["options"].destination_root == "/documentation"
        assert kwargs["show_progress"] is False
        return fake_results

    monkeypatch.setattr(
        "eledoctl.cli.internal.docs.require_connection_settings",
        lambda: ConnectionSettings("https://example.com", "token"),
    )
    monkeypatch.setattr("eledoctl.cli.internal.docs.build_sync_plan", fake_build_sync_plan)
    monkeypatch.setattr("eledoctl.cli.internal.docs._sync_docs", fake_sync_docs)

    runner = CliRunner()
    result = runner.invoke(sync_docs, [str(root), "--tag", "docs-sync", "--dry-run", "--no-progress"])

    assert result.exit_code == 0
    assert captured_options[0].source_root == root
    assert captured_options[0].selection is None
    assert captured_options[0].tag == "docs-sync"
    assert captured_options[0].dry_run is True
    assert "Files: 1" in result.output
    assert "created: 1" in result.output
    assert "failures: 0" in result.output


def test_sync_docs_accepts_selection_destination_and_disable_transform(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "docs"
    selection = root / "api"
    selection.mkdir(parents=True)
    (selection / "index.mdx").write_text("# API\n", encoding="utf-8")

    captured_options: list[Any] = []

    def fake_build_sync_plan(options: Any) -> Any:
        captured_options.append(options)
        return SimpleNamespace(
            source_root=root,
            selection=selection,
            items=(),
        )

    async def fake_sync_docs(**kwargs: Any) -> list[SyncFileResult]:
        return []

    monkeypatch.setattr(
        "eledoctl.cli.internal.docs.require_connection_settings",
        lambda: ConnectionSettings("https://example.com", "token"),
    )
    monkeypatch.setattr("eledoctl.cli.internal.docs.build_sync_plan", fake_build_sync_plan)
    monkeypatch.setattr("eledoctl.cli.internal.docs._sync_docs", fake_sync_docs)

    runner = CliRunner()
    result = runner.invoke(
        sync_docs,
        [
            str(root),
            str(selection),
            "--destination-root",
            "/custom-docs",
            "--tag",
            "docs-sync",
            "--disable-transform",
            "remove-imports",
            "--disable-transform",
            "patch-links-from-reference",
            "--no-progress",
        ],
    )

    assert result.exit_code == 0
    options = captured_options[0]
    assert options.source_root == root
    assert options.selection == selection
    assert options.destination_root == "/custom-docs"
    assert options.transform_options.remove_imports is False
    assert options.transform_options.patch_links_from_reference is False
    assert options.transform_options.convert_admonitions is True


def test_sync_docs_writes_log_and_inspection_files(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    log_file = tmp_path / "sync.jsonl"
    inspect_file = tmp_path / "inspect.txt"

    fake_results = [
        SyncFileResult(
            source_path=root / "index.mdx",
            target_path="/documentation",
            action=SyncAction.UPDATE,
            status=SyncStatus.WARNING,
            dry_run=False,
            uploaded=True,
        )
    ]

    class FakePlan:
        source_root = root
        selection = root
        items = (object(),)

    def fake_build_sync_plan(options: Any) -> FakePlan:
        return FakePlan()

    async def fake_sync_docs(**kwargs: Any) -> list[SyncFileResult]:
        return fake_results

    monkeypatch.setattr(
        "eledoctl.cli.internal.docs.require_connection_settings",
        lambda: ConnectionSettings("https://example.com", "token"),
    )
    monkeypatch.setattr("eledoctl.cli.internal.docs.build_sync_plan", fake_build_sync_plan)
    monkeypatch.setattr("eledoctl.cli.internal.docs._sync_docs", fake_sync_docs)

    runner = CliRunner()
    result = runner.invoke(
        sync_docs,
        [
            str(root),
            "--tag",
            "docs-sync",
            "--log-file",
            str(log_file),
            "--inspect-file",
            str(inspect_file),
            "--no-progress",
        ],
    )

    assert result.exit_code == 0
    assert log_file.exists()
    assert inspect_file.exists()
    assert "Sync log written to" in result.output
    assert "Manual inspection list written to" in result.output


def test_sync_docs_exits_nonzero_when_failures_exist(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "docs"
    root.mkdir()

    fake_results = [
        SyncFileResult(
            source_path=root / "index.mdx",
            target_path="/documentation",
            action=SyncAction.FAILED,
            status=SyncStatus.FAILURE,
            dry_run=False,
            uploaded=False,
        )
    ]

    class FakePlan:
        source_root = root
        selection = root
        items = (object(),)

    async def fake_sync_docs(**kwargs: Any) -> list[SyncFileResult]:
        return fake_results

    monkeypatch.setattr(
        "eledoctl.cli.internal.docs.require_connection_settings",
        lambda: ConnectionSettings("https://example.com", "token"),
    )
    monkeypatch.setattr("eledoctl.cli.internal.docs.build_sync_plan", lambda options: FakePlan())
    monkeypatch.setattr("eledoctl.cli.internal.docs._sync_docs", fake_sync_docs)

    runner = CliRunner()
    result = runner.invoke(sync_docs, [str(root), "--tag", "docs-sync", "--no-progress"])

    assert result.exit_code != 0
    assert "Documentation sync failed for 1 file" in result.output
