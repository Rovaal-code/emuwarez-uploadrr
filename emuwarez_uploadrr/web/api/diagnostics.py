"""Runtime diagnostics endpoint — GET /api/runtime/diagnostics."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import require_auth
from ..schemas import RuntimeDiagnosticsResponse

router = APIRouter(tags=["diagnostics"])


@router.get("/runtime/diagnostics", response_model=RuntimeDiagnosticsResponse)
def runtime_diagnostics(current_user: dict = Depends(require_auth)) -> RuntimeDiagnosticsResponse:
    """Diagnóstico del runtime de la aplicación. Requiere autenticación."""
    from emuwarez_uploadrr.services.runtime_diagnostics import get_runtime_diagnostics
    result = get_runtime_diagnostics()
    return RuntimeDiagnosticsResponse(**result)
