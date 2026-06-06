import pytest

from pyeledo import EledoApiError, EledoClient


def test_client_normalizes_base_url() -> None:
    client = EledoClient(base_url="https://eledo.online/")

    assert client.base_url == "https://eledo.online"


@pytest.mark.asyncio
async def test_get_profile_returns_account(mock_transport, json_response) -> None:
    transport = mock_transport(lambda request: json_response(payload={"account": "john.doe@example.com"}))

    async with EledoClient(token="secret", transport=transport) as client:
        profile = await client.get_profile()

    assert profile.account == "john.doe@example.com"


@pytest.mark.asyncio
async def test_client_sends_api_key_header(mock_transport, json_response) -> None:
    seen_headers = {}

    def handler(request):
        seen_headers.update(request.headers)
        return json_response(payload={"account": "john.doe@example.com"})

    async with EledoClient(token="secret", transport=mock_transport(handler)) as client:
        await client.get_profile()

    assert seen_headers["api-key"] == "secret"


@pytest.mark.asyncio
async def test_json_error_raises_api_error(mock_transport) -> None:
    import httpx

    transport = mock_transport(lambda request: httpx.Response(404, json={"error": "Template not found."}))

    async with EledoClient(transport=transport) as client:
        with pytest.raises(EledoApiError, match="Template not found"):
            await client.get_schema("missing")
