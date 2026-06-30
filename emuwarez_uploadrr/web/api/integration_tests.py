"""External API connection test endpoints (Phase 10C).

POST /api/integrations/test/tmdb      — test TMDb API key
POST /api/integrations/test/emuwarez  — test eMuwarez API key
POST /api/integrations/test/arr       — test Radarr/Sonarr unsaved credentials

Safety guarantees (see services/integration_tests.py):
- All operations are read-only.
- No credentials are stored automatically.
- No eMuwarez requests are created.
- No torrent uploads.
- Uploadrr is completely excluded.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import (
    IntegrationTestResult,
    TestArrRequest,
    TestEmuwarezRequest,
    TestTmdbRequest,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _get_conn():
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(_db_path())
    init_db(conn)
    return conn


@router.post("/test/tmdb", response_model=IntegrationTestResult)
def test_tmdb(
    body: TestTmdbRequest,
    current_user: dict = Depends(require_auth),
) -> IntegrationTestResult:
    """Probe TMDb using the provided (or stored) API key. Never stores credentials."""
    from emuwarez_uploadrr.services.integration_tests import test_tmdb_connection
    with _get_conn() as conn:
        result = test_tmdb_connection(
            api_key=body.api_key or None,
            language=body.language or "es-ES",
            region=body.region or "ES",
            conn=conn,
        )
    return IntegrationTestResult(**result)


@router.post("/test/emuwarez", response_model=IntegrationTestResult)
def test_emuwarez(
    body: TestEmuwarezRequest,
    current_user: dict = Depends(require_auth),
) -> IntegrationTestResult:
    """Probe eMuwarez using the provided (or stored) credentials. Never stores credentials."""
    from emuwarez_uploadrr.services.integration_tests import test_emuwarez_connection
    with _get_conn() as conn:
        result = test_emuwarez_connection(
            api_key=body.api_key or None,
            base_url=body.base_url or None,
            conn=conn,
        )
    return IntegrationTestResult(**result)


@router.post("/test/arr", response_model=IntegrationTestResult)
def test_arr(
    body: TestArrRequest,
    current_user: dict = Depends(require_auth),
) -> IntegrationTestResult:
    """Probe Radarr/Sonarr with unsaved credentials. Never stores credentials."""
    from emuwarez_uploadrr.services.integration_tests import test_arr_connection
    result = test_arr_connection(
        kind=body.kind,
        base_url=body.base_url,
        api_key=body.api_key,
    )
    return IntegrationTestResult(**result)
