from pydantic import BaseModel
from typing import Any, Dict, Optional, Generic, TypeVar, List

T = TypeVar("T")

class ExecutionResponse(BaseModel):
    """Standard response for execution/transaction endpoints"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None

class PaginatedResponse(BaseModel, Generic[T]):
    total: int
    page: int
    page_size: int
    items: List[T]
