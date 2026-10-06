"""Fallo deliberado de la candidata E2E; no apta para producción normal."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health", status_code=503)
def health() -> dict[str, str]:
    return {
        "status": "error",
        "message": "Fallo E2E deliberado posterior a migración: candidata temporal no apta para producción.",
    }
