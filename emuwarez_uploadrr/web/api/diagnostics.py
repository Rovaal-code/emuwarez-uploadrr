"""Runtime diagnostics endpoint — GET /api/runtime/diagnostics."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import require_auth
from ..schemas import RuntimeDiagnosticsResponse, VersionResponse

router = APIRouter(tags=["diagnostics"])


@router.get("/runtime/diagnostics", response_model=RuntimeDiagnosticsResponse)
def runtime_diagnostics(current_user: dict = Depends(require_auth)) -> RuntimeDiagnosticsResponse:
    """Diagnóstico del runtime de la aplicación. Requiere autenticación."""
    from emuwarez_uploadrr.services.runtime_diagnostics import get_runtime_diagnostics
    result = get_runtime_diagnostics()
    return RuntimeDiagnosticsResponse(**result)


@router.get("/runtime/version", response_model=VersionResponse)
def runtime_version(
    refrescar: bool = False,
    current_user: dict = Depends(require_auth),
) -> VersionResponse:
    """Versión en ejecución y si hay uno más nuevo publicado.

    `refrescar=true` salta la caché de una hora: es lo que hace el botón
    "Comprobar ahora" de la tarjeta."""
    from emuwarez_uploadrr.services.version_info import estado_de_version
    return VersionResponse(**estado_de_version(forzar=refrescar))
