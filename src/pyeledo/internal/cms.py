"""Internal Eledo Articles/CMS API wrapper."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import httpx

from pyeledo.client import EledoClient
from pyeledo.exceptions import EledoInvalidResponseError
from pyeledo.types import JsonObject, JsonValue
from pyeledo.utils import quote_path_part


@dataclass(frozen=True, slots=True)
class CmsArticleCreateRequest:
    """Request body for POST /api/articles/{path...}."""

    title: str
    slug: str
    markdown: str
    ord: int | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class CmsArticleUpdateRequest:
    """Request body for PUT /api/articles/{path...}."""

    title: str
    slug: str
    markdown: str
    ordr: int | None = None
    description: str | None = None
    published: bool | None = None


@dataclass(frozen=True, slots=True)
class CmsArticle:
    """Article returned by the Eledo Articles API."""

    id: str
    version: int
    title: str
    slug: str
    parent_id: str | None
    ordr: int
    published: bool
    platform: str | None
    nomenu: bool
    index: bool
    description: str | None
    markdown: str | None


@dataclass(frozen=True, slots=True)
class CmsArticleChild:
    """Child article summary returned by the Eledo Articles API."""

    id: str
    version: int
    slug: str


@dataclass(frozen=True, slots=True)
class CmsArticleRetrieveResponse:
    """Response from GET /api/articles/{path...}."""

    article: CmsArticle
    children: tuple[CmsArticleChild, ...]


class CmsClient:
    """Client for private Eledo Articles/CMS endpoints."""

    def __init__(self, client: EledoClient) -> None:
        self._client = client

    async def create_article(
        self,
        *,
        path: Sequence[str],
        request: CmsArticleCreateRequest,
        label: str | None = None,
    ) -> JsonObject:
        """Create an article.

        This mirrors the API directly. The caller is responsible for keeping
        path[-1] and request.slug consistent.
        """
        response = await self._client.request(
            "POST",
            article_path(path),
            params=_label_params(label),
            json=build_create_article_payload(request),
        )
        return _response_json_object_or_empty(response)

    async def retrieve_article(self, path: Sequence[str]) -> CmsArticleRetrieveResponse:
        """Retrieve an article and its child summaries."""
        response = await self._client.request("GET", article_path(path))
        return parse_article_retrieve_response(_response_json_object(response))

    async def update_article(
        self,
        *,
        path: Sequence[str],
        request: CmsArticleUpdateRequest,
        label: str | None = None,
    ) -> JsonObject:
        """Update an article.

        The Eledo API currently behaves as an upsert: PUT auto-creates the
        article when it does not exist.
        """
        response = await self._client.request(
            "PUT",
            article_path(path),
            params=_label_params(label),
            json=build_update_article_payload(request),
        )
        return _response_json_object_or_empty(response)


def article_path(path: Sequence[str]) -> str:
    """Build an Eledo Articles API path."""
    if not path:
        raise ValueError("Article path must contain at least one segment.")

    segments: list[str] = []
    for segment in path:
        if segment == "":
            raise ValueError("Article path cannot contain empty segments.")
        segments.append(quote_path_part(segment))

    return "/api/articles/" + "/".join(segments)


def build_create_article_payload(request: CmsArticleCreateRequest) -> JsonObject:
    """Build the POST article payload."""
    payload: JsonObject = {
        "title": request.title,
        "slug": request.slug,
        "markdown": request.markdown,
        "description": request.description,
    }

    if request.ord is not None:
        payload["ord"] = request.ord

    return payload


def build_update_article_payload(request: CmsArticleUpdateRequest) -> JsonObject:
    """Build the PUT article payload."""
    payload: JsonObject = {
        "title": request.title,
        "slug": request.slug,
        "markdown": request.markdown,
        "description": request.description,
    }

    if request.ordr is not None:
        payload["ordr"] = request.ordr

    if request.published is not None:
        payload["published"] = request.published

    return payload


def parse_article_retrieve_response(data: JsonObject) -> CmsArticleRetrieveResponse:
    """Parse GET /api/articles/{path...} response."""
    raw_article = data.get("article")
    if not isinstance(raw_article, dict):
        raise EledoInvalidResponseError("Invalid Articles API response: expected article object.")

    raw_children = data.get("children")
    if not isinstance(raw_children, list):
        raise EledoInvalidResponseError("Invalid Articles API response: expected children array.")

    children: list[CmsArticleChild] = []
    for raw_child in raw_children:
        if not isinstance(raw_child, dict):
            raise EledoInvalidResponseError("Invalid Articles API response: expected child object.")
        children.append(parse_article_child(raw_child))

    return CmsArticleRetrieveResponse(
        article=parse_article(raw_article),
        children=tuple(children),
    )


def parse_article(data: JsonObject) -> CmsArticle:
    """Parse an article object."""
    return CmsArticle(
        id=_required_string(data, "id", "article"),
        version=_required_int(data, "version", "article"),
        title=_required_string(data, "title", "article"),
        slug=_required_string(data, "slug", "article"),
        parent_id=_optional_string(data, "parentId", "article"),
        ordr=_required_int(data, "ordr", "article"),
        published=_required_bool(data, "published", "article"),
        platform=_optional_string(data, "platform", "article"),
        nomenu=_required_bool(data, "nomenu", "article"),
        index=_required_bool(data, "index", "article"),
        description=_optional_string(data, "description", "article"),
        markdown=_optional_string(data, "markdown", "article"),
    )


def parse_article_child(data: JsonObject) -> CmsArticleChild:
    """Parse a child article summary."""
    return CmsArticleChild(
        id=_required_string(data, "id", "child"),
        version=_required_int(data, "version", "child"),
        slug=_required_string(data, "slug", "child"),
    )


def _label_params(label: str | None) -> dict[str, str] | None:
    if label is None:
        return None
    return {"label": label}


def _response_json_object(response: httpx.Response) -> JsonObject:
    try:
        data: JsonValue = response.json()
    except ValueError as exc:
        raise EledoInvalidResponseError("Invalid JSON response from Eledo Articles API.") from exc

    if not isinstance(data, dict):
        raise EledoInvalidResponseError("Invalid Articles API response: expected JSON object.")

    return data


def _response_json_object_or_empty(response: httpx.Response) -> JsonObject:
    if response.content == b"":
        return {}
    return _response_json_object(response)


def _required_string(data: JsonObject, key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise EledoInvalidResponseError(f"Invalid Articles API response: expected {context}.{key} string.")
    return value


def _optional_string(data: JsonObject, key: str, context: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise EledoInvalidResponseError(f"Invalid Articles API response: expected {context}.{key} string or null.")
    return value


def _required_int(data: JsonObject, key: str, context: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise EledoInvalidResponseError(f"Invalid Articles API response: expected {context}.{key} integer.")
    return value


def _required_bool(data: JsonObject, key: str, context: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise EledoInvalidResponseError(f"Invalid Articles API response: expected {context}.{key} boolean.")
    return value
