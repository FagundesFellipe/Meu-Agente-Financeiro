"""Aplicação FASTAPI com lifespan

Ponto de entrada do servidor HTTP

Uso:
    uvicorn financial_agent.server.main:app

"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db.migrate import run_migrations
from financial_agent.server.routes.health import router as health_router
from financial_agent.server.routes.webhook_telegram import (
    router as webhook_telegram_router,
)
from financial_agent.server.routes.webhook_whatsapp import (
    router as webhook_whatsapp_router,
)
from shared.config import _configure_structlog, settings
from shared.db import (
    bootstrap_langgraph_schema,
    close_checkpointer,
    close_pool,
)
from shared.db_sync_categories import sync_categories

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Gerencia o ciclo de vida da aplicação."""

    _configure_structlog()

    logger.info("server_starting", port=settings.port)

    await run_migrations()
    await sync_categories()
    await bootstrap_langgraph_schema()
    logger.info("server_ready")

    yield

    await close_checkpointer()
    await close_pool()
    logger.info("server_stopped")


app = FastAPI(
    title="Financial Agent",
    description="API para agente financeiro whatsapp e telegram",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.resolved_cors_allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(health_router)
app.include_router(webhook_whatsapp_router)
app.include_router(webhook_telegram_router)

if settings.enable_sync_webhook and settings.environment != "production":
    from financial_agent.server.routes.webhook_sync import router as webhook_sync_router

    app.include_router(webhook_sync_router)
