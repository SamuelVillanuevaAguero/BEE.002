from pydantic import BaseModel
from typing import Any, Dict, Optional

class ExecutionResponse(BaseModel):
    """Standard response for execution/transaction endpoints"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
