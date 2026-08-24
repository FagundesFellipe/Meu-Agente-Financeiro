"""
Rota de health check

Verifica se o servidor HTTP e o banco de dados estão ativos

curl http://localhost:{{port}}/health

"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from financial_agent import __version__
from shared.db import check_db_health

router = APIRouter(tags=["health"])


@router.get("/health")
async def heath() -> JSONResponse:
    """Verifica saúde do serviço

    Testa conectividade com o banco de dados via SELECT 1.

    Returns:
        {"status":"ok", "database":"connected", "version":""}
        ou {"status":"degraded","database":"disconnected","version":"..."}
    """

    is_health = await check_db_health()

    if not is_health:
        return JSONResponse(
            content={
                "status": "degraded",
                "database": "disconnected",
                "version": __version__,
            },
            status_code=503,
        )

    return JSONResponse(
        content={"status": "ok", "database": "disconnected", "version": __version__},
        status_code=200,
    )
