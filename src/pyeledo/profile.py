"""Profile API helpers."""

from dataclasses import dataclass

from pyeledo.exceptions import EledoInvalidResponseError
from pyeledo.types import JsonObject


@dataclass(frozen=True, slots=True)
class Profile:
    """Authenticated Eledo profile."""

    account: str


def parse_profile_response(data: JsonObject) -> Profile:
    """Parse and validate a native Eledo profile response."""

    account = data.get("account")
    if not isinstance(account, str):
        raise EledoInvalidResponseError("Invalid response from Eledo API: expected account.")
    return Profile(account=account)
