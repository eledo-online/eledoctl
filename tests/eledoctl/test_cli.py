from click.testing import CliRunner

from eledoctl.cli.main import main


def test_cli_top_level_help_lists_command_tree() -> None:
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "templates" in result.output
    assert "pdf" in result.output
    assert "internal" in result.output


def test_internal_docs_sync_stub() -> None:
    result = CliRunner().invoke(main, ["internal", "docs", "sync", "docs", "--dry-run"])

    assert result.exit_code == 0
    assert "implementation is pending" in result.output
    assert "dry_run=True" in result.output
