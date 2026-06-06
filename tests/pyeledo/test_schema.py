import pytest

from pyeledo import EledoClient, PrimitiveField, PrimitiveType, pick_primitive_fields


@pytest.mark.asyncio
async def test_get_schema_without_version_requests_latest_schema(mock_transport) -> None:
    seen_path = None

    def handler(request):
        nonlocal seen_path
        seen_path = request.url.path
        import httpx

        return httpx.Response(
            200,
            json={"schema": {"type": "object", "properties": {"Name": {"type": "String"}}}},
        )

    async with EledoClient(transport=mock_transport(handler)) as client:
        schema = await client.get_schema("template-id")

    assert seen_path == "/api/RESTv1/Schema/template-id"
    assert schema["properties"]["Name"]["type"] == "String"


@pytest.mark.asyncio
async def test_get_schema_with_version_requests_versioned_schema(mock_transport) -> None:
    seen_path = None

    def handler(request):
        nonlocal seen_path
        seen_path = request.url.path
        import httpx

        return httpx.Response(200, json={"schema": {"type": "object", "properties": {}}})

    async with EledoClient(transport=mock_transport(handler)) as client:
        await client.get_schema("template-id", template_version=3)

    assert seen_path == "/api/RESTv1/Schema/template-id/3"


@pytest.mark.asyncio
async def test_get_schema_rejects_non_positive_version() -> None:
    client = EledoClient()

    with pytest.raises(ValueError, match="greater than zero"):
        await client.get_schema("template-id", template_version=0)


def test_pick_primitive_fields_returns_only_top_level_primitives() -> None:
    schema = {
        "type": "object",
        "properties": {
            "text": {"type": "String"},
            "number": {"type": "Number"},
            "person": {"type": "object", "properties": {"name": {"type": "String"}}},
            "items": {"type": "array", "items": {"Name": {"type": "String"}}},
        },
    }

    fields = pick_primitive_fields(schema)

    assert fields == [
        PrimitiveField("text", PrimitiveType.STRING),
        PrimitiveField("number", PrimitiveType.NUMBER),
    ]
