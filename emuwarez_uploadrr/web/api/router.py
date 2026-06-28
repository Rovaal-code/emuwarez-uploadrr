"""Main API router — aggregates all sub-routers under /api prefix."""
from __future__ import annotations

from fastapi import APIRouter

from .health import router as health_router
from .setup import router as setup_router
from .auth import router as auth_router
from .contract import router as contract_router
from .placeholders import router as placeholders_router

api_router = APIRouter(prefix="/api")

api_router.include_router(health_router)
api_router.include_router(setup_router)
api_router.include_router(auth_router)
api_router.include_router(contract_router)
api_router.include_router(placeholders_router)
