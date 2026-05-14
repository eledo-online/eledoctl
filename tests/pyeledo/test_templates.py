import pytest

from pyeledo import EledoClient, EledoInvalidResponseError, TemplateScope


@pytest.mark.asyncio
async def test_get_templates_maps_private_scope_to_mine(mock_transport) -> None:
    seen_url = None

    def handler(request):
        nonlocal seen_url
        seen_url = request.url
        import httpx

        return httpx.Response(
            200,
            json={
                "total": 1,
                "templates": [
                    {
                        "id": "template-id",
                        "date": 1763113932000,
                        "name": "Copy of Quote",
                        "thumbnailUrl": "https://example.com/thumb.png",
                        "type": 0,
                        "version": 1,
                        "bulk": False,
                    }
                ],
            },
        )

    async with EledoClient(transport=mock_transport(handler)) as client:
        result = await client.get_templates(scope=TemplateScope.PRIVATE)

    assert seen_url is not None
    assert seen_url.params["scope"] == "Mine"
    assert result.total == 1
    assert result.templates[0].id == "template-id"
    assert result.templates[0].name == "Copy of Quote"
    assert result.templates[0].thumbnail_url == "https://example.com/thumb.png"


@pytest.mark.asyncio
async def test_get_templates_maps_public_scope_to_public(mock_transport) -> None:
    seen_url = None

    def handler(request):
        nonlocal seen_url
        seen_url = request.url
        import httpx

        return httpx.Response(200, json={"total": 0, "templates": []})

    async with EledoClient(transport=mock_transport(handler)) as client:
        await client.get_templates(scope=TemplateScope.PUBLIC)

    assert seen_url is not None
    assert seen_url.params["scope"] == "Public"


@pytest.mark.asyncio
async def test_get_templates_accepts_missing_template_id(mock_transport) -> None:
    def handler(request):
        import httpx

        return httpx.Response(
            200,
            json={
                "total": 1,
                "templates": [{"name": "Copy of Quote", "version": 1, "bulk": False}],
            },
        )

    async with EledoClient(transport=mock_transport(handler)) as client:
        result = await client.get_templates()

    assert result.templates[0].id is None


@pytest.mark.asyncio
async def test_get_templates_rejects_invalid_shape(mock_transport) -> None:
    def handler(request):
        import httpx

        return httpx.Response(200, json={"total": 1})

    async with EledoClient(transport=mock_transport(handler)) as client:
        with pytest.raises(EledoInvalidResponseError, match="templates array"):
            await client.get_templates()
