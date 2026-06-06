import base64

import pytest

from pyeledo import EledoApiError, EledoClient, EledoInvalidResponseError


@pytest.mark.asyncio
async def test_generate_pdf_sends_minimal_payload_with_file_null(mock_transport) -> None:
    seen_body = None

    def handler(request):
        nonlocal seen_body
        seen_body = request.read()
        import httpx

        return httpx.Response(
            200,
            content=b"%PDF fake",
            headers={
                "content-type": "application/pdf",
                "content-disposition": 'attachment; filename="0_0.pdf"; filename*=UTF-80_0.pdf',
            },
        )

    async with EledoClient(transport=mock_transport(handler)) as client:
        result = await client.generate_pdf(template_id="template-id")

    assert seen_body == b'{"templateId":"template-id","file":null}'
    assert result.filename == "0_0.pdf"
    assert result.content == b"%PDF fake"


@pytest.mark.asyncio
async def test_generate_pdf_includes_template_version_and_file_data(mock_transport) -> None:
    seen_body = None

    def handler(request):
        nonlocal seen_body
        seen_body = request.read()
        import httpx

        return httpx.Response(200, content=b"pdf", headers={"content-type": "application/pdf"})

    async with EledoClient(transport=mock_transport(handler)) as client:
        await client.generate_pdf(
            template_id="template-id",
            template_version=2,
            file_data={"Name": "ACME"},
        )

    assert seen_body == b'{"templateId":"template-id","file":{"Name":"ACME"},"templateVersion":2}'


@pytest.mark.asyncio
async def test_generate_pdf_json_error_raises_api_error(mock_transport) -> None:
    def handler(request):
        import httpx

        return httpx.Response(
            200,
            json={"error": "No file data have been provided."},
            headers={"content-type": "application/json"},
        )

    async with EledoClient(transport=mock_transport(handler)) as client:
        with pytest.raises(EledoApiError, match="No file data"):
            await client.generate_pdf(template_id="template-id")


@pytest.mark.asyncio
async def test_generate_pdf_rejects_unexpected_content_type(mock_transport) -> None:
    def handler(request):
        import httpx

        return httpx.Response(200, text="html", headers={"content-type": "text/html"})

    async with EledoClient(transport=mock_transport(handler)) as client:
        with pytest.raises(EledoInvalidResponseError, match="expected PDF or JSON"):
            await client.generate_pdf(template_id="template-id")


def test_generated_pdf_base64_payload() -> None:
    from pyeledo import GeneratedPdf

    pdf = GeneratedPdf(content=b"hello", filename="x.pdf")

    assert pdf.as_base64() == base64.b64encode(b"hello").decode("ascii")
    assert pdf.as_json() == {
        "filename": "x.pdf",
        "mimeType": "application/pdf",
        "data": "aGVsbG8=",
    }
