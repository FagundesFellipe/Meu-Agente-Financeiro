"""Entry point do Worker — loop de processamento de mensagens.

Inicia o Worker que consome mensagens da fila PostgreSQL em loop.
Cada mensagem é processada pelo agente configurado, seja ela vinda do
Telegram ou do WhatsApp (Twilio) — o canal é resolvido por mensagem em
``processor.process_message``.

Uso:
    python -m financial_agent.worker.main
"""

import asyncio

import structlog

from db.migrate import run_migrations
from financial_agent.worker.consumer import claim_next_message
from financial_agent.worker.processor import process_message
from shared.config import _configure_structlog, settings
from shared.db import close_checkpointer, close_pool, get_checkpointer, get_pool
from shared.db_sync_categories import sync_categories

logger = structlog.get_logger()


def _check_twilio_credentials() -> None:
    """Falha rápido se o WhatsApp (Twilio) estiver em modo real sem credenciais."""
    if settings.resolved_twilio_outbound_mode != "real":
        return

    missing = []
    if not settings.twilio_account_sid:
        missing.append("TWILIO_ACCOUNT_SID")
    if not settings.twilio_api_key_sid:
        missing.append("TWILIO_API_KEY_SID")
    if not settings.twilio_api_key_secret:
        missing.append("TWILIO_API_KEY_SECRET")
    if not settings.twilio_from_number:
        missing.append("TWILIO_FROM_NUMBER")

    if missing:
        logger.error(
            "twilio_credentials_missing",
            missing=missing,
            outbound_mode=settings.resolved_twilio_outbound_mode,
        )
        msg = (
            "Twilio outbound em modo 'real' exige as seguintes variáveis: "
            f"{', '.join(missing)}"
        )
        raise RuntimeError(msg)


def _check_telegram_credentials() -> None:
    """Avisa (sem interromper o Worker) se o Telegram estiver sem bot token."""
    if not settings.telegram_bot_token:
        logger.warning("telegram_bot_token_missing")


async def main() -> None:
    """Loop principal do Worker.

    1. Configura logging e banco de dados
    2. Aplica migrações pendentes
    3. Entra em loop infinito buscando mensagens na fila
    4. Processa cada mensagem com o agente apropriado (Telegram ou WhatsApp)
    """
    _configure_structlog()
    logger.info("worker_starting")

    await get_pool()
    await run_migrations()
    await sync_categories()

    checkpointer = await get_checkpointer()
    await checkpointer.setup()

    _check_twilio_credentials()
    _check_telegram_credentials()

    logger.info(
        "worker_ready",
        poll_interval=settings.poll_interval_seconds,
        lease_seconds=settings.lease_seconds,
    )

    try:
        while True:
            message = await claim_next_message(settings.lease_seconds)

            if message is None:
                await asyncio.sleep(settings.poll_interval_seconds)
                continue

            await process_message(message)

    except KeyboardInterrupt:
        logger.info("worker_interrupted")
    finally:
        await close_checkpointer()
        await close_pool()
        logger.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
