import pytest

from pyeledo.exceptions import EledoInvalidResponseError
from pyeledo.utils import api_path, extract_filename, parse_json_object


def test_api_path_normalizes_restv1_prefix() -> None:
    assert api_path("/List") == "/api/RESTv1/List"
    assert api_path("List") == "/api/RESTv1/List"


def test_extract_filename_supports_filename() -> None:
    assert extract_filename('attachment; filename="file.pdf"') == "file.pdf"


def test_extract_filename_supports_rfc5987_filename() -> None:
    assert extract_filename("attachment; filename*=UTF-8''hello%20world.pdf") == "hello world.pdf"


def test_parse_json_object_allows_empty_text() -> None:
    assert parse_json_object("  ") == {}


def test_parse_json_object_rejects_arrays() -> None:
    with pytest.raises(EledoInvalidResponseError, match="object"):
        parse_json_object("[]")
