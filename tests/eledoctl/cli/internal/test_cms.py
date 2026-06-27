from __future__ import annotations

from eledoctl.cli.internal.cms import _is_ci_environment, _should_show_progress


def test_is_ci_environment_detects_ci(monkeypatch) -> None:
    monkeypatch.setenv("CI", "true")

    assert _is_ci_environment() is True


def test_is_ci_environment_detects_github_actions(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    assert _is_ci_environment() is True


def test_is_ci_environment_returns_false_without_ci_markers(monkeypatch) -> None:
    for name in (
        "CI",
        "GITHUB_ACTIONS",
        "GITLAB_CI",
        "BUILDKITE",
        "CIRCLECI",
        "JENKINS_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    assert _is_ci_environment() is False


def test_should_show_progress_returns_false_when_disabled(monkeypatch) -> None:
    monkeypatch.delenv("CI", raising=False)

    assert _should_show_progress(False) is False
