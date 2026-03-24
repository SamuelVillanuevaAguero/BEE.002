import time
import uuid
import logging
from contextvars import ContextVar
from fastapi import Request

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default=None)
logger = logging.getLogger("api.request")

async def observability_middleware(request: Request, call_next):
    req_id = str(uuid.uuid4())
    correlation_id_var.set(req_id)
    
    start_time = time.time()
    logger.info("Incoming request", extra={
        "http_method": request.method,
        "http_path": request.url.path,
        "client_ip": request.client.host if request.client else None
    })
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        
        logger.info("Request completed", extra={
            "http_status": response.status_code,
            "duration_ms": round(process_time * 1000, 2)
        })
        response.headers["X-Correlation-ID"] = req_id
        return response
    except Exception as e:
        process_time = time.time() - start_time
        logger.exception("Unhandled Exception in Request", extra={
            "http_status": 500,
            "duration_ms": round(process_time * 1000, 2)
        })
        raise
