"""Main API router — aggregates all sub-routers under /api prefix."""
from __future__ import annotations

from fastapi import APIRouter

from .health import router as health_router
from .setup import router as setup_router
from .auth import router as auth_router
from .instances import router as instances_router
from .dashboard import router as dashboard_router
from .library import router as library_router
from .requests import router as requests_router
from .nomenclature import router as nomenclature_router
from .season_pack import router as season_pack_router
from .uploads import router as uploads_router
from .logs import router as logs_router
from .diagnostics import router as diagnostics_router
from .maintenance import router as maintenance_router
from .arr_health import router as arr_health_router
from .request_readiness import router as request_readiness_router
from .settings import router as settings_router
from .integration_tests import router as integration_tests_router
from .notifications import router as notifications_router
from .scheduled_tasks import router as scheduled_tasks_router
from .system import router as system_router
from .eventos import router as eventos_router
from .widget import router as widget_router
from .estadisticas import router as estadisticas_router

api_router = APIRouter(prefix="/api")

api_router.include_router(health_router)
api_router.include_router(setup_router)
api_router.include_router(auth_router)
api_router.include_router(instances_router)
api_router.include_router(dashboard_router)
# arr_health_router must come before library_router so /library/diagnostics
# and /library/recommendations/refresh don't get swallowed by /library/{item_id}
api_router.include_router(arr_health_router)
api_router.include_router(library_router)
# request_readiness_router must come before requests_router so /requests/readiness,
# /requests/prioritized and /requests/{id}/readiness|candidates don't collide with
# the parameterized /requests/{request_id} route.
api_router.include_router(request_readiness_router)
api_router.include_router(requests_router)
api_router.include_router(nomenclature_router)
api_router.include_router(season_pack_router)
api_router.include_router(uploads_router)
api_router.include_router(logs_router)
api_router.include_router(diagnostics_router)
api_router.include_router(maintenance_router)
api_router.include_router(settings_router)
api_router.include_router(integration_tests_router)
api_router.include_router(notifications_router)
api_router.include_router(scheduled_tasks_router)
api_router.include_router(system_router)
api_router.include_router(eventos_router)
api_router.include_router(widget_router)
api_router.include_router(estadisticas_router)
