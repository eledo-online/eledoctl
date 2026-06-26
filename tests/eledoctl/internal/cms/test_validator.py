from __future__ import annotations

import pytest

from eledoctl.internal.cms.validator import (
    validate_cms_markdown,
    validate_cms_tree,
)
from pyeledo.exceptions import EledoApiError
from pyeledo.internal.cms import CmsArticle, CmsArticleChild, CmsArticleRetrieveResponse


def cms_child(*, slug: str) -> CmsArticleChild:
    return CmsArticleChild(
        id=f"child-{slug}",
        version=1,
        slug=slug,
    )


def cms_response(
    *,
    title: str,
    slug: str,
    markdown: str | None,
    children: tuple[CmsArticleChild, ...] = (),
) -> CmsArticleRetrieveResponse:
    return CmsArticleRetrieveResponse(
        article=CmsArticle(
            id=f"article-{slug}",
            version=1,
            title=title,
            slug=slug,
            parent_id=None,
            ordr=0,
            published=True,
            platform=None,
            nomenu=False,
            index=False,
            description=None,
            markdown=markdown,
        ),
        children=children,
    )


class FakeCmsClient:
    def __init__(self, existing: dict[tuple[str, ...], CmsArticleRetrieveResponse]) -> None:
        self.existing = existing

    async def retrieve_article(self, path: tuple[str, ...]) -> CmsArticleRetrieveResponse:
        try:
            return self.existing[path]
        except KeyError as exc:
            raise EledoApiError("Invalid path") from exc


def test_validate_cms_markdown_warns_for_mdx_link() -> None:
    warnings = validate_cms_markdown(
        target_segments=("documentation", "api"),
        markdown="Read [Authentication](./authentication.mdx).\n",
    )

    assert len(warnings) == 1
    assert warnings[0].target_path == "/documentation/api"
    assert warnings[0].code == "cms_markdown_source_link"
    assert warnings[0].label == "Authentication"
    assert warnings[0].url == "./authentication.mdx"


def test_validate_cms_markdown_warns_for_md_link() -> None:
    warnings = validate_cms_markdown(
        target_segments=("documentation", "api"),
        markdown="Read [Authentication](./authentication.md#setup).\n",
    )

    assert len(warnings) == 1
    assert warnings[0].code == "cms_markdown_source_link"
    assert warnings[0].url == "./authentication.md#setup"


def test_validate_cms_markdown_warns_for_docusaurus_asset_link() -> None:
    warnings = validate_cms_markdown(
        target_segments=("documentation", "integrations", "pdf-form"),
        markdown="Download a sample PDF from [this link](/assets/integrations/pdf-form.pdf).\n",
    )

    assert len(warnings) == 1
    assert warnings[0].code == "cms_docusaurus_asset_link"
    assert warnings[0].label == "this link"
    assert warnings[0].url == "/assets/integrations/pdf-form.pdf"


def test_validate_cms_markdown_warns_for_docusaurus_image_link() -> None:
    warnings = validate_cms_markdown(
        target_segments=("documentation", "product", "template-editor"),
        markdown="![Text Box](/img/product/template-editor/components/text-box-configuration.png)\n",
    )

    assert len(warnings) == 1
    assert warnings[0].code == "cms_docusaurus_image_link"
    assert warnings[0].label == "Text Box"
    assert warnings[0].url == "/img/product/template-editor/components/text-box-configuration.png"


def test_validate_cms_markdown_accepts_cms_link_with_article_id_suffix() -> None:
    warnings = validate_cms_markdown(
        target_segments=("documentation", "api"),
        markdown="[Authentication](/documentation/authentication){6a3810d171e935939fd17c49}\n",
    )

    assert warnings == ()


def test_validate_cms_markdown_accepts_null_link_with_article_id_suffix() -> None:
    warnings = validate_cms_markdown(
        target_segments=("documentation", "api"),
        markdown="[Authentication](null){6a3810d171e935939fd17c49}\n",
    )

    assert warnings == ()


def test_validate_cms_markdown_accepts_eledo_image_url() -> None:
    warnings = validate_cms_markdown(
        target_segments=("documentation", "product"),
        markdown=(
            "![Text Box](https://eledo.online/images/download/"
            "687ec6190ab282fdd0fed676?t=1bdrtnbp1asy2yec040y8jsqg1uief58b9amnvj2gok4e9lbuo)\n"
        ),
    )

    assert warnings == ()


@pytest.mark.asyncio
async def test_validate_cms_tree_traverses_children() -> None:
    cms = FakeCmsClient(
        existing={
            ("documentation",): cms_response(
                title="Documentation",
                slug="documentation",
                markdown="# Documentation\n",
                children=(cms_child(slug="api"),),
            ),
            ("documentation", "api"): cms_response(
                title="Api",
                slug="api",
                markdown="Read [Authentication](./authentication.mdx).\n",
            ),
        }
    )

    result = await validate_cms_tree(
        cms=cms,  # type: ignore[arg-type]
        remote_path="documentation",
    )

    assert result.checked_articles == 2
    assert result.warning_count == 1
    assert result.warnings[0].target_path == "/documentation/api"
    assert result.warnings[0].code == "cms_markdown_source_link"


@pytest.mark.asyncio
async def test_validate_cms_tree_reports_read_problem_as_warning() -> None:
    cms = FakeCmsClient(existing={})

    result = await validate_cms_tree(
        cms=cms,  # type: ignore[arg-type]
        remote_path="documentation/missing",
    )

    assert result.checked_articles == 0
    assert result.warning_count == 1
    assert result.warnings[0].target_path == "/documentation/missing"
    assert result.warnings[0].code == "cms_article_read_warning"
