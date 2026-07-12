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

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import (
    IntegrationTestResult,
    TestArrRequest,
    TestEmuwarezRequest,
    TestQbitRequest,
    TestTmdbRequest,
    TestUploadrrRequest,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])

_VALID_ARR_KINDS = {"radarr", "sonarr"}


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


@router.post("/test/qbit", response_model=IntegrationTestResult)
def test_qbit(
    body: TestQbitRequest,
    current_user: dict = Depends(require_auth),
) -> IntegrationTestResult:
    """Probe qBittorrent WebUI with the provided (or stored) credentials.
    Never stores credentials, never touches torrents."""
    from emuwarez_uploadrr.services.integration_tests import test_qbit_connection
    with _get_conn() as conn:
        result = test_qbit_connection(
            url=body.url or None,
            port=body.port or None,
            username=body.username if body.username is not None else None,
            password=body.password if body.password is not None else None,
            conn=conn,
        )
    return IntegrationTestResult(**result)


@router.post("/test/arr", response_model=IntegrationTestResult)
def test_arr(
    body: TestArrRequest,
    current_user: dict = Depends(require_auth),
) -> IntegrationTestResult:
    """Probe Radarr/Sonarr, either a saved instance (instance_id) or unsaved
    credentials (kind/base_url/api_key). Never stores credentials."""
    from emuwarez_uploadrr.services.integration_tests import test_arr_connection

    if body.instance_id is not None:
        with _get_conn() as conn:
            result = test_arr_connection(instance_id=body.instance_id, conn=conn)
        return IntegrationTestResult(**result)

    if not body.kind or body.kind not in _VALID_ARR_KINDS:
        raise HTTPException(status_code=422, detail="kind debe ser 'radarr' o 'sonarr'")
    if not body.base_url or not body.api_key:
        raise HTTPException(status_code=422, detail="base_url y api_key son obligatorios si no se especifica instance_id")

    result = test_arr_connection(
        kind=body.kind,
        base_url=body.base_url,
        api_key=body.api_key,
    )
    return IntegrationTestResult(**result)


@router.post("/test/uploadrr", response_model=IntegrationTestResult)
def test_uploadrr(
    body: TestUploadrrRequest,
    current_user: dict = Depends(require_auth),
) -> IntegrationTestResult:
    """Check Uploadrr-EMU runtime paths (filesystem only). Never executes Uploadrr."""
    from emuwarez_uploadrr.services.integration_tests import test_uploadrr_connection
    with _get_conn() as conn:
        result = test_uploadrr_connection(
            path=body.path or None,
            python_path=body.python_path or None,
            conn=conn,
        )
    return IntegrationTestResult(**result)
