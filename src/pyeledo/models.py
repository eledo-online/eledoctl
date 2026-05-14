"""Shared pyeledo data models."""

from pydantic import BaseModel, ConfigDict


class EledoModel(BaseModel):
    """Base model for Eledo API DTOs."""

    model_config = ConfigDict(extra="allow")
