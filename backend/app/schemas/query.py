"""Query foundation contracts."""

from typing import Annotated, Literal
from pydantic import BaseModel, StringConstraints


class QueryRequest(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]


class QueryResponse(BaseModel):
    status: Literal["not_implemented"] = "not_implemented"
    message: str = "Agent query processing will be implemented in a later phase."
