"""Common Pydantic models: Response Envelope, Pagination, and Metadata."""

import math
from typing import Any, Generic, TypeVar
from pydantic import BaseModel, ConfigDict, Field
from app.core.errors import ProblemDetail

T = TypeVar("T")


class PaginationMeta(BaseModel):
    """Pagination metadata container."""

    model_config = ConfigDict(extra="ignore")

    page: int = Field(default=1, ge=1, description="Current page number (1-indexed)")
    per_page: int = Field(default=50, ge=1, le=1000, description="Items per page")
    total: int = Field(default=0, ge=0, description="Total matching items")
    total_pages: int = Field(default=1, ge=0, description="Total number of pages")

    @classmethod
    def create(cls, page: int, per_page: int, total: int) -> "PaginationMeta":
        total_pages = max(1, math.ceil(total / per_page)) if total > 0 else 1
        return cls(page=page, per_page=per_page, total=total, total_pages=total_pages)


class ResponseEnvelope(BaseModel, Generic[T]):
    """Unified API response envelope matching platform specification."""

    model_config = ConfigDict(extra="ignore")

    data: T | None = Field(default=None, description="Response payload")
    meta: PaginationMeta | dict[str, Any] | None = Field(default=None, description="Metadata or pagination details")
    error: ProblemDetail | None = Field(default=None, description="RFC 7807 problem details if failure occurred")

    @classmethod
    def success(
        cls,
        data: T,
        meta: PaginationMeta | dict[str, Any] | None = None,
    ) -> "ResponseEnvelope[T]":
        return cls(data=data, meta=meta, error=None)

    @classmethod
    def paginated(
        cls,
        data: T,
        page: int,
        per_page: int,
        total: int,
    ) -> "ResponseEnvelope[T]":
        meta = PaginationMeta.create(page=page, per_page=per_page, total=total)
        return cls(data=data, meta=meta, error=None)


class PaginationParams(BaseModel):
    """Query parameter helper for paginated requests."""

    page: int = Field(default=1, ge=1, description="Page number")
    per_page: int = Field(default=50, ge=1, le=500, description="Items per page")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page
