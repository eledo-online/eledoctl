from click.testing import CliRunner

from eledoctl.cli.main import main


def test_internal_docs_sync_stub() -> None:
    result = CliRunner().invoke(main, ["internal", "docs", "sync", "docs", "--dry-run"])

    assert result.exit_code == 0
    assert "implementation is pending" in result.output
    assert "dry_run=True" in result.output
