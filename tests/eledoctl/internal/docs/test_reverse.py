"""Tests for conservative CMS -> Git recovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from eledoctl.internal.docs.reverse import (
    PullAction,
    pull_one_document,
    recover_document,
    summarize_pull,
    write_pull_log,
)
from eledoctl.internal.docs.uploader import SyncItem
from pyeledo.internal.cms import CmsArticle, CmsArticleRetrieveResponse, CmsClient


def test_unchanged_mdx_round_trip_preserves_verbatim_source() -> None:
    original = (
        "---\ntitle: Authentication\nsidebar_position: 2\n---\n\n"
        "import DocFeedbackForm from '@site/src/components/DocFeedbackForm';\n\n"
        "# Authentication\n\n"
        "Read [**Templates**](./templates/index.mdx).\n\n"
        "<DocFeedbackForm />\n"
    )
    cms = "\n# Authentication\n\nRead [Templates](null){abc123}.\n\n"
    assert recover_document(local_mdx=original, cms_markdown=cms).content == original


def test_edit_only_one_sentence_preserves_frontmatter_imports_and_links() -> None:
    original = (
        "---\ntitle: Authentication\nsidebar_position: 2\n---\n\n"
        "import DocFeedbackForm from '@site/src/components/DocFeedbackForm';\n\n"
        "# Authentication\n\nEledo uses an API key.\n\n"
        "Read [**Templates**](./templates/index.mdx).\n\n<DocFeedbackForm />\n"
    )
    cms = "# Authentication\n\nEledo uses an API key in the HTTP header.\n\nRead [Templates](null){abc123}.\n\n"
    result = recover_document(local_mdx=original, cms_markdown=cms)
    assert result.error is None
    assert result.content == original.replace("Eledo uses an API key.", "Eledo uses an API key in the HTTP header.")


def test_restore_cms_image_and_pdf_link_without_source_churn() -> None:
    original = "# Guide\n\nRead [Sample PDF](/assets/example.pdf).\n\n![Screen](/img/example.png)\n\nEnd.\n"
    cms = (
        "# Guide\n\nRead [Sample PDF](null){pdfid}.\n\n"
        "![Screen](https://eledo.online/images/download/123?t=abc)\n\nEnd updated.\n"
    )
    result = recover_document(local_mdx=original, cms_markdown=cms)
    assert result.error is None
    assert result.content == original.replace("End.", "End updated.")


def test_mismatched_link_labels_fail_without_guesswork() -> None:
    result = recover_document(
        local_mdx="# Guide\n\n[Authentication](./auth.mdx)\n",
        cms_markdown="# Guide\n\n[New Topic](null){id}\n",
    )
    assert result.content is None
    assert result.error is not None
    assert "Cannot reliably match" in result.error


def test_ambiguous_duplicate_label_fails() -> None:
    result = recover_document(
        local_mdx="[More](./one.mdx) and [More](./two.mdx)\n",
        cms_markdown="[More](null){one} and [More](null){two}\n",
    )
    assert result.content is None
    assert result.error is not None
    assert "Ambiguous" in result.error


def test_edit_inside_admonition_preserves_original_directive() -> None:
    original = "# Guide\n\n:::note\n\nOriginal.\n\n:::\n"
    cms = "# Guide\n\n> **Note**\n> Changed.\n"
    result = recover_document(local_mdx=original, cms_markdown=cms)
    assert result.error is None
    assert result.content == original.replace("Original.", "Changed.")


def test_edit_outside_admonition_preserves_admonition() -> None:
    original = "# Guide\n\nIntro.\n\n:::note\n\nOriginal.\n\n:::\n\nEnd.\n"
    cms = "# Guide\n\nIntro revised.\n\n> **Note**\n> Original.\n\nEnd.\n"
    result = recover_document(local_mdx=original, cms_markdown=cms)
    assert result.error is None
    assert result.content == original.replace("Intro.", "Intro revised.")


def _response(markdown: str | None) -> CmsArticleRetrieveResponse:
    return CmsArticleRetrieveResponse(
        article=CmsArticle(
            id="id",
            version=1,
            title="Guide",
            slug="guide",
            parent_id=None,
            ordr=0,
            published=True,
            platform=None,
            nomenu=False,
            index=False,
            description=None,
            markdown=markdown,
        ),
        children=(),
    )


class _FakeCms:
    def __init__(self, markdown: str | None) -> None:
        self.markdown = markdown
        self.calls = 0

    async def retrieve_article(self, path: tuple[str, ...]) -> CmsArticleRetrieveResponse:
        self.calls += 1
        return _response(self.markdown)


@pytest.mark.asyncio
async def test_pull_writes_only_changed_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "guide.mdx"
    path.write_text("# Guide\n\nOld.\n")
    item = SyncItem(path, ("documentation", "guide"), "/documentation/guide")
    cms = _FakeCms("# Guide\n\nNew.\n")
    result = await pull_one_document(cms=cast(CmsClient, cms), item=item, dry_run=False)
    assert result.action == PullAction.UPDATED
    assert result.written
    assert path.read_text() == "# Guide\n\nNew.\n"
    repeated = await pull_one_document(cms=cast(CmsClient, cms), item=item, dry_run=False)
    assert repeated.action == PullAction.UNCHANGED


@pytest.mark.asyncio
async def test_dry_run_does_not_write(tmp_path: Path) -> None:
    path = tmp_path / "guide.mdx"
    path.write_text("# Guide\n\nOld.\n")
    item = SyncItem(path, ("documentation", "guide"), "/documentation/guide")
    result = await pull_one_document(cms=cast(CmsClient, _FakeCms("# Guide\n\nNew.\n")), item=item, dry_run=True)
    assert result.action == PullAction.UPDATED
    assert not result.written
    assert path.read_text() == "# Guide\n\nOld.\n"


@pytest.mark.asyncio
async def test_null_cms_markdown_does_not_erase_git_file(tmp_path: Path) -> None:
    path = tmp_path / "guide.mdx"
    path.write_text("# Guide\n")
    item = SyncItem(path, ("documentation", "guide"), "/documentation/guide")
    result = await pull_one_document(cms=cast(CmsClient, _FakeCms(None)), item=item, dry_run=False)
    assert result.action == PullAction.FAILED
    assert path.read_text() == "# Guide\n"


def test_jsonl_log_and_summary(tmp_path: Path) -> None:
    result = recover_document(local_mdx="# Guide\n", cms_markdown="# Guide\n")
    assert result.content == "# Guide\n"
    from eledoctl.internal.docs.reverse import PullResult

    rows = [PullResult(tmp_path / "x.mdx", "/documentation/x", PullAction.FAILED, True, False, ("unmapped link",))]
    log = tmp_path / "results.jsonl"
    write_pull_log(log, rows)
    assert json.loads(log.read_text().strip())["messages"] == ["unmapped link"]
    assert summarize_pull(rows, dry_run=True).failed == 1


def test_preserve_image_with_caption_component_while_importing_text_edit() -> None:
    original = (
        "# Template Editor\n\nOld text.\n\n"
        '<ImageWithCaption\n  src="/img/screen.png"\n  alt="Screen"\n  caption="Editor UI"\n/>\n\n'
        "Final paragraph.\n"
    )
    cms = (
        "# Template Editor\n\nNew text.\n\n"
        "![Screen](https://eledo.online/images/download/123?t=token)\n\n"
        "Final paragraph.\n"
    )
    recovery = recover_document(local_mdx=original, cms_markdown=cms)
    assert recovery.error is None
    assert recovery.content == original.replace("Old text.", "New text.")


def test_inserting_paragraph_preserves_existing_lines() -> None:
    source = "# Guide\n\nIntro.\n\nConclusion.\n"
    cms = "# Guide\n\nIntro.\n\nNew paragraph.\n\nConclusion.\n"
    result = recover_document(local_mdx=source, cms_markdown=cms)
    assert result.error is None
    assert result.content == cms


@pytest.mark.asyncio
async def test_failed_link_recovery_does_not_write(tmp_path: Path) -> None:
    path = tmp_path / "guide.mdx"
    original = "# Guide\n\n[Existing](./existing.mdx)\n"
    path.write_text(original, encoding="utf-8")
    item = SyncItem(path, ("documentation", "guide"), "/documentation/guide")
    cms = _FakeCms("# Guide\n\n[Different](null){id}\n")
    result = await pull_one_document(cms=cast(CmsClient, cms), item=item, dry_run=False)
    assert result.action == PullAction.FAILED
    assert not result.written
    assert path.read_text(encoding="utf-8") == original
