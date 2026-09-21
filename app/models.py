"""Data models for the sample API.

These models are the source of truth for the OpenAPI contract: FastAPI derives
the spec from them, and `scripts/export_openapi.py` writes that spec to
`openapi.yaml`. Changing a field here changes the contract, which is exactly
what api-guard exists to notice.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class User(BaseModel):
    """A user as returned by the API."""

    id: int = Field(description="Unique identifier.", examples=[1])
    name: str = Field(description="Display name.", examples=["Sohan"])
    email: str = Field(description="Contact email address.", examples=["sohan@example.com"])
    created_at: datetime = Field(description="When the user record was created.")


class UserCreate(BaseModel):
    """The payload accepted when creating a user."""

    name: str = Field(description="Display name.", examples=["Sohan"])
    email: str = Field(description="Contact email address.", examples=["sohan@example.com"])


class Error(BaseModel):
    """A problem report returned with non-2xx responses."""

    detail: str = Field(description="Human-readable description of the problem.")
