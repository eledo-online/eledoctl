"""PDF generation API helpers."""

import base64
from dataclasses import dataclass

import httpx

from pyeledo.exceptions import EledoApiError, EledoInvalidResponseError
from pyeledo.types import JsonObject
from pyeledo.utils import extract_error_message, extract_filename, response_json_object


@dataclass(frozen=True, slots=True)
class GeneratedPdf:
    """Generated PDF returned by Eledo."""

    content: bytes
    filename: str = "document.pdf"
    mime_type: str = "application/pdf"

    def as_bytes(self) -> bytes:
        """Return the raw PDF bytes.

        Raw bytes are the primary representation because the Eledo Generate
        endpoint returns binary PDF data on success.
        """
        return self.content

    def as_base64(self) -> str:
        """Return the PDF content as a base64-encoded string."""
        return base64.b64encode(self.content).decode("ascii")

    def as_json(self) -> JsonObject:
        """Return a JSON-serializable payload with metadata and base64 content.

        This is a presentation helper for CLI/integration layers. It does not
        change the primary in-memory representation, which remains raw bytes.
        """
        return {
            "filename": self.filename,
            "mimeType": self.mime_type,
            "data": self.as_base64(),
        }


def build_generate_payload(
    *,
    template_id: str,
    file_data: JsonObject | None = None,
    template_version: int | None = None,
) -> JsonObject:
    """Build a payload for the Eledo Generate endpoint."""
    if not template_id:
        raise ValueError("template_id is required.")
    if template_version is not None and template_version <= 0:
        raise ValueError("template_version must be greater than zero.")

    payload: JsonObject = {"templateId": template_id, "file": file_data}
    if template_version is not None:
        payload["templateVersion"] = template_version

    return payload


def parse_generate_response(response: httpx.Response) -> GeneratedPdf:
    """Parse and validate a Generate endpoint response."""
    content_type = response.headers.get("content-type", "").lower()
    if "application/pdf" in content_type:
        filename = extract_filename(response.headers.get("content-disposition")) or "document.pdf"
        return GeneratedPdf(
            content=response.content,
            filename=filename,
            mime_type="application/pdf",
        )
    if "application/json" in content_type:
        data = response_json_object(response)
        message = extract_error_message(data)
        raise EledoApiError(message, status_code=response.status_code)
    raise EledoInvalidResponseError(
        f"Invalid response from Eledo API: expected PDF or JSON error, got {content_type!r}."
    )
