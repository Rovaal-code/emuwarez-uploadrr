"""Contract documentation endpoints."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..schemas import ContractSummaryResponse
from ..errors import AppError

router = APIRouter(tags=["contract"])

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONTRACT_MD = _REPO_ROOT / "docs" / "ui_backend_contract.md"
_CONTRACT_JSON = _REPO_ROOT / "docs" / "ui_backend_contract.json"


@router.get("/contract", response_model=ContractSummaryResponse)
def contract_summary() -> ContractSummaryResponse:
    return ContractSummaryResponse(
        message="Contrato funcional UI/Backend v1.0. Ver archivos docs/ para especificación completa.",
        md_path=str(_CONTRACT_MD),
        json_path=str(_CONTRACT_JSON),
        sections=[
            "Dashboard", "Biblioteca", "Faltantes", "Peticiones",
            "Subidas", "Tareas", "Instancias", "Logs", "Configuración",
        ],
        docs_url="/api/docs",
    )


@router.get("/contract/json")
def contract_json() -> JSONResponse:
    if not _CONTRACT_JSON.exists():
        raise AppError(
            "Archivo de contrato no encontrado",
            status_code=404,
            detail=f"Ruta esperada: {_CONTRACT_JSON}",
        )
    try:
        data = json.loads(_CONTRACT_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AppError("Contrato JSON inválido", status_code=500, detail=str(exc))
    return JSONResponse(content=data)
