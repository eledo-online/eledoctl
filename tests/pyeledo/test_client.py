from pyeledo import EledoClient


def test_client_normalizes_base_url() -> None:
    client = EledoClient(base_url="https://example.com/")

    assert client.base_url == "https://example.com"
