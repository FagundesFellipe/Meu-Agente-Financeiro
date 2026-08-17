"""FastAPI dependencies para validação e rate limiting.

Dependencies são injetadas automaticamente nas rotas via Depends().
Centralizar aqui mantém as rotas limpas e focadas na lógica de negócio.

Uso:
    from financial_agent.server.dependencies import (
        check_rate_limit,
        validate_telegram_secret_token,
        validate_twilio_signature,
    )

    @router.post("/webhook/twilio")
    async def webhook(
        _twilio: None = Depends(validate_twilio_signature),
        _rate: None = Depends(check_rate_limit),
    ):
        ...

    @router.post("/webhook/telegram")
    async def webhook(
        _tg: None = Depends(validate_telegram_secret_token),
        _rate: None = Depends(check_rate_limit),
    ):
        ...
"""

import hmac
import time
from collections import defaultdict

import structlog
from fastapi import HTTPException, Request
from twilio.request_validator import RequestValidator

from src.shared.config import settings

logger = structlog.get_logger()

# Sliding window de requisições por telefone: {phone: [timestamps]}
request_history: dict[str, list[float]] = defaultdict(list)


def build_validation_url(request: Request) -> str:
    """Reconstrói a URL pública que o Twilio usou para chamar o webhook.

    Atrás de proxy/túnel (cloudflared), request.url mostra localhost.
    TWILIO_WEBHOOK_URL resolve isso definindo a URL pública base.
    Se não configurada, usa a URL do request diretamente.

    Args:
        request: Request HTTP do FastAPI.

    Returns:
        URL completa para validação de assinatura.
    """

    if settings.twilio_webhook_url:
        base = settings.twilio_webhook_url.rstrip("/")
        url = f"{base}{request.url.path}"
        if request.url.path:
            url = f"{url}?{request.url.query}"

        return url

    return str(request.url)


async def validate_twilio_signature(request: Request) -> None:
    """Valida a assinatura X-Twilio-Signature com HMAC-SHA1 (SDK oficial).

    Usa o RequestValidator do SDK do Twilio para validação criptográfica.
    Quando habilitada (VALIDATE_TWILIO_SIGNATURE=true), rejeita com 403
    qualquer request sem assinatura válida.

    A URL usada na validação é reconstruída via TWILIO_WEBHOOK_URL
    (necessário atrás de proxy/túnel como cloudflared) ou do request.

    Raises:
        HTTPException 403: Se a assinatura é inválida ou ausente.
        HTTPException 500: Se TWILIO_AUTH_TOKEN não está configurado.
    """
    if not settings.validate_twilio_signature:
        return

    signature = request.headers.get("X-Twilio-Signature")
    if not signature:
        logger.warning("twilio_signature_missing")
        raise HTTPException(status_code=403, detail="Missing Twilio signature")

    if not settings.twilio_auth_token:
        logger.error("twilio_auth_token_not_configured")
        raise HTTPException(
            status_code=500,
            detail="Twilio auth token not configured",
        )

    url = build_validation_url(request)

    # Parâmetros POST para validação (Twilio assina URL + params ordenados)
    form_data = await request.form()
    params = {key: str(value) for key, value in form_data.items()}

    validator = RequestValidator(settings.twilio_auth_token)
    if not validator.validate(url, params, signature):
        logger.warning(
            "twilio_signature_invalid",
            url=url,
            params_keys=sorted(params.keys()),
        )
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    logger.debug("twilio_signature_valid")


async def validate_telegram_secret_token(request: Request) -> None:
    """Valida o token secreto do Telegram no header X-Telegram-Bot-Api-Secret-Token.

    Diferente do Twilio (HMAC-SHA1), o Telegram usa um simples header com
    o secret_token definido no setWebhook. Basta comparar strings.

    Raises:
        HTTPException 403: Se o token é inválido ou ausente.
    """
    if not settings.telegram_webhook_secret_token:
        return

    token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not token:
        logger.warning("telegram_secret_token_missing")
        raise HTTPException(status_code=403, detail="Missing Telegram secret token")

    if not hmac.compare_digest(token, settings.telegram_webhook_secret_token):
        logger.warning("telegram_secret_token_invalid")
        raise HTTPException(status_code=403, detail="Invalid Telegram secret token")

    logger.debug("telegram_secret_token_valid")


async def check_rate_limit(user_id: str) -> None:
    """Verifica rate limit por usuário (WhatsApp: phone, Telegram: chat_id).

    Usa sliding window de 1 hora. Remove timestamps antigos e compara
    a quantidade de requisições com o limite configurado.

    Args:
        user_id: Identificador do usuário (phone E.164 ou chat_id).

    Raises:
        HTTPException 429: Se o limite foi atingido.
    """
    now = time.time()
    one_hour_ago = now - 3600

    timestamps = request_history[user_id]
    request_history[user_id] = [t for t in timestamps if t > one_hour_ago]

    if len(request_history[user_id]) >= settings.rate_limit_per_hour:
        logger.warning(
            "rate_limit_exceeded",
            user_id=user_id,
            count=len(request_history[user_id]),
            limit=settings.rate_limit_per_hour,
        )
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again later.",
        )

    request_history[user_id].append(now)
