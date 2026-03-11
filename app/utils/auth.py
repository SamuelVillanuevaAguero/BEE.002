import os
from fastapi import Header, HTTPException, status
from dotenv import load_dotenv

load_dotenv()
VALID_API_KEY = os.getenv("BEE_API_KEY")

def verify_api_key(x_api_key: str = Header(..., alias="x-api-key")) -> str:
    """
    FastAPI dependency that validates the x-api-key header.
    Raises HTTP 401 if the key is invalid or missing.
    """
    if x_api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key
