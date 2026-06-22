from __future__ import annotations

import json

import httpx
import pytest

from pyeledo import EledoClient, EledoInvalidResponseError
from pyeledo.internal.cms import (
    CmsArticleCreateRequest,
    CmsArticleUpdateRequest,
    CmsClient,
    article_path,
    build_create_article_payload,
    build_update_article_payload,
    parse_article,
)


def test_article_path_builds_articles_api_path() -> None:
    assert article_path(("documentation", "guides", "make_com")) == "/api/articles/documentation/guides/make_com"


def test_article_path_quotes_segments() -> None:
    assert article_path(("documentation", "hello world")) == "/api/articles/documentation/hello%20world"


def test_article_path_rejects_empty_path() -> None:
    with pytest.raises(ValueError, match="at least one segment"):
        article_path(())


def test_article_path_rejects_empty_segment() -> None:
    with pytest.raises(ValueError, match="empty segments"):
        article_path(("documentation", ""))


def test_build_create_article_payload_uses_ord() -> None:
    payload = build_create_article_payload(
        CmsArticleCreateRequest(
            title="Make Guides",
            slug="make_com",
            ord=10,
            markdown="## make.com guides\n - version 4",
        )
    )

    assert payload == {
        "title": "Make Guides",
        "slug": "make_com",
        "ord": 10,
        "markdown": "## make.com guides\n - version 4",
        "description": None,
    }


def test_build_create_article_payload_omits_missing_ord() -> None:
    payload = build_create_article_payload(
        CmsArticleCreateRequest(
            title="Make Guides",
            slug="make_com",
            markdown="content",
        )
    )

    assert payload == {
        "title": "Make Guides",
        "slug": "make_com",
        "markdown": "content",
        "description": None,
    }


def test_build_update_article_payload_uses_ordr() -> None:
    payload = build_update_article_payload(
        CmsArticleUpdateRequest(
            title="Make Guides",
            slug="make_com",
            ordr=10,
            markdown="## make.com guides\n - version 4",
        )
    )

    assert payload == {
        "title": "Make Guides",
        "slug": "make_com",
        "ordr": 10,
        "markdown": "## make.com guides\n - version 4",
        "description": None,
    }


@pytest.mark.asyncio
async def test_create_article_posts_to_articles_api(mock_transport) -> None:
    seen_method = None
    seen_path = None
    seen_label = None
    seen_payload = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_method, seen_path, seen_label, seen_payload
        seen_method = request.method
        seen_path = request.url.path
        seen_label = request.url.params.get("label")
        seen_payload = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"ok": True})

    async with EledoClient(transport=mock_transport(handler)) as client:
        cms = CmsClient(client)
        result = await cms.create_article(
            path=("documentation", "guides", "make_com"),
            label="deploy1",
            request=CmsArticleCreateRequest(
                title="Make Guides",
                slug="make_com",
                ord=10,
                markdown="## make.com guides\n - version 4",
            ),
        )

    assert seen_method == "POST"
    assert seen_path == "/api/articles/documentation/guides/make_com"
    assert seen_label == "deploy1"
    assert seen_payload == {
        "title": "Make Guides",
        "slug": "make_com",
        "ord": 10,
        "markdown": "## make.com guides\n - version 4",
        "description": None,
    }
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_update_article_puts_to_articles_api(mock_transport) -> None:
    seen_method = None
    seen_path = None
    seen_label = None
    seen_payload = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_method, seen_path, seen_label, seen_payload
        seen_method = request.method
        seen_path = request.url.path
        seen_label = request.url.params.get("label")
        seen_payload = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"updated": True})

    async with EledoClient(transport=mock_transport(handler)) as client:
        cms = CmsClient(client)
        result = await cms.update_article(
            path=("documentation", "guides", "make_com"),
            label="deploy1",
            request=CmsArticleUpdateRequest(
                title="Make Guides",
                slug="make_com",
                ordr=10,
                markdown="## make.com guides\n - version 4",
            ),
        )

    assert seen_method == "PUT"
    assert seen_path == "/api/articles/documentation/guides/make_com"
    assert seen_label == "deploy1"
    assert seen_payload == {
        "title": "Make Guides",
        "slug": "make_com",
        "ordr": 10,
        "markdown": "## make.com guides\n - version 4",
        "description": None,
    }
    assert result == {"updated": True}


@pytest.mark.asyncio
async def test_retrieve_article_parses_article_and_children(mock_transport) -> None:
    seen_method = None
    seen_path = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_method, seen_path
        seen_method = request.method
        seen_path = request.url.path
        return httpx.Response(
            200,
            json={
                "article": {
                    "id": "646159b922695689c1db4339",
                    "version": 5,
                    "title": "Documentation",
                    "slug": "documentation",
                    "parentId": None,
                    "ordr": 0,
                    "published": False,
                    "platform": None,
                    "nomenu": False,
                    "index": False,
                    "description": None,
                    "markdown": "# Get started with Eledo\nLearn the basics.",
                },
                "children": [
                    {
                        "id": "69970b566345ea85b9732935",
                        "version": 2,
                        "slug": "integrations",
                    }
                ],
            },
        )

    async with EledoClient(transport=mock_transport(handler)) as client:
        cms = CmsClient(client)
        result = await cms.retrieve_article(("documentation",))

    assert seen_method == "GET"
    assert seen_path == "/api/articles/documentation"

    assert result.article.id == "646159b922695689c1db4339"
    assert result.article.version == 5
    assert result.article.title == "Documentation"
    assert result.article.slug == "documentation"
    assert result.article.parent_id is None
    assert result.article.ordr == 0
    assert result.article.published is False
    assert result.article.platform is None
    assert result.article.nomenu is False
    assert result.article.index is False
    assert result.article.description is None
    assert result.article.markdown == "# Get started with Eledo\nLearn the basics."

    assert len(result.children) == 1
    assert result.children[0].id == "69970b566345ea85b9732935"
    assert result.children[0].version == 2
    assert result.children[0].slug == "integrations"


@pytest.mark.asyncio
async def test_retrieve_article_rejects_missing_article_object(mock_transport) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"children": []})

    async with EledoClient(transport=mock_transport(handler)) as client:
        cms = CmsClient(client)

        with pytest.raises(EledoInvalidResponseError, match="article object"):
            await cms.retrieve_article(("documentation",))


@pytest.mark.asyncio
async def test_retrieve_article_rejects_missing_children_array(mock_transport) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "article": {
                    "id": "646159b922695689c1db4339",
                    "version": 5,
                    "title": "Documentation",
                    "slug": "documentation",
                    "parentId": None,
                    "ordr": 0,
                    "published": False,
                    "platform": None,
                    "nomenu": False,
                    "index": False,
                    "description": None,
                    "markdown": "# Get started",
                }
            },
        )

    async with EledoClient(transport=mock_transport(handler)) as client:
        cms = CmsClient(client)

        with pytest.raises(EledoInvalidResponseError, match="children array"):
            await cms.retrieve_article(("documentation",))


@pytest.mark.asyncio
async def test_write_response_may_be_empty(mock_transport) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    async with EledoClient(transport=mock_transport(handler)) as client:
        cms = CmsClient(client)
        result = await cms.update_article(
            path=("documentation",),
            request=CmsArticleUpdateRequest(
                title="Documentation",
                slug="documentation",
                markdown="# Documentation",
            ),
        )

    assert result == {}


def test_parse_article_allows_null_markdown() -> None:
    article = parse_article(
        {
            "id": "article-1",
            "version": 1,
            "title": "Download",
            "slug": "download",
            "parentId": None,
            "ordr": 4,
            "published": False,
            "platform": None,
            "nomenu": False,
            "index": False,
            "description": None,
            "markdown": None,
        }
    )

    assert article.markdown is None


def test_parse_article_rejects_invalid_markdown_type() -> None:
    with pytest.raises(EledoInvalidResponseError):
        parse_article(
            {
                "id": "article-1",
                "version": 1,
                "title": "Download",
                "slug": "download",
                "parentId": None,
                "ordr": 4,
                "published": False,
                "platform": None,
                "nomenu": False,
                "index": False,
                "description": None,
                "markdown": 123,
            }
        )
