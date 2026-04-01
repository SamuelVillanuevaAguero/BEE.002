"""
main.py
========
Main script: Launches the FastAPI service, includes all routes, origins, methods, etc.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.routes import router
from app.core.scheduler import start_scheduler, stop_scheduler

from app.core.logger import setup_logging
from app.middlewares.observability import observability_middleware

setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("▶  Starting application...")
    
    start_scheduler()
    
    yield
    
    logger.info("⏹  Stopping application...")
    stop_scheduler()

app = FastAPI(
    title="BEE.002 API",
    description="Monitoring automation API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(BaseHTTPMiddleware, dispatch=observability_middleware)

app.include_router(router.router)