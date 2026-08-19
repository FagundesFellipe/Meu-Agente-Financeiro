"""Cliente assíncrono para envio de mensagens pelo Telegram Bot API."""

from __future__ import annotations

import httpx
import structlog

logger = structlog.get_logger()

TELEGRAM_API_BASE_URL = "https://api.telegram.org"
TELEGRAM_MAX_MESSAGE_LENGTH = 4096


class TelegramSendError(Exception):
    """Erro retornado pelo Telegram ao enviar uma mensagem."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Telegram API error {status_code}: {detail}")


class TelegramClient:
    """Cliente assíncrono para enviar mensagens pelo Telegram.

    Args:
        bot_token: Token do bot fornecido pelo BotFather.
        delivery_mode: ``mock`` simula os envios para desenvolvimento local.
    """

    def __init__(self, bot_token: str, *, delivery_mode: str = "real"):
        if delivery_mode not in ("real", "mock"):
            raise ValueError(
                f"delivery_mode deve ser 'real' ou 'mock'; recebido: {delivery_mode}"
            )
        if delivery_mode == "real" and not bot_token:
            raise ValueError("bot_token não pode ser vazio")

        self.bot_token = bot_token
        self.delivery_mode = delivery_mode
        self.base_url = f"{TELEGRAM_API_BASE_URL}/bot{bot_token}"

    async def send_message(self, to: int | str, body: str) -> int:
        """Envia uma mensagem de texto e retorna seu ``message_id``.

        Não envia ``parse_mode``: a resposta do agente permanece texto literal,
        sem interpretar Markdown ou HTML presentes na entrada do usuário.
        """
        if not body:
            raise ValueError("body não pode ser vazio")
        if len(body) > TELEGRAM_MAX_MESSAGE_LENGTH:
            raise ValueError(
                "body excede o limite de "
                f"{TELEGRAM_MAX_MESSAGE_LENGTH} caracteres do Telegram"
            )

        if self.delivery_mode == "mock":
            logger.info("telegram_message_mocked", to=to, body_length=len(body))
            return 0

        data = await self._post("sendMessage", {"chat_id": to, "text": body})
        result = data.get("result")
        message_id = result.get("message_id") if isinstance(result, dict) else None
        if not isinstance(message_id, int):
            raise TelegramSendError(
                200, "sendMessage não retornou message_id na mensagem criada"
            )

        logger.info("telegram_message_sent", to=to, message_id=message_id)
        return message_id

    async def send_typing(self, to: int | str) -> bool:
        """Exibe o indicador de digitação por até cinco segundos."""
        if self.delivery_mode == "mock":
            logger.debug("telegram_typing_skipped", to=to, reason="mock_mode")
            return False

        try:
            data = await self._post(
                "sendChatAction", {"chat_id": to, "action": "typing"}
            )
            if data.get("result") is True:
                logger.info("telegram_typing_sent", to=to)
                return True
            logger.warning("telegram_typing_failed", to=to, detail="result_not_true")
        except TelegramSendError as exc:
            logger.warning("telegram_typing_failed", to=to, status_code=exc.status_code)
        except httpx.HTTPError as exc:
            logger.warning(
                "telegram_typing_error", to=to, error_type=type(exc).__name__
            )
        return False

    async def _post(self, method: str, payload: dict[str, int | str]) -> dict:
        try:
            async with httpx.AsyncClient() as http:
                response = await http.post(
                    f"{self.base_url}/{method}", json=payload, timeout=15.0
                )
        except httpx.HTTPError as exc:
            raise TelegramSendError(0, type(exc).__name__) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise TelegramSendError(
                response.status_code, "resposta inválida do Telegram"
            ) from exc
        if not isinstance(data, dict):
            raise TelegramSendError(
                response.status_code, "resposta inválida do Telegram"
            )

        if not response.is_success or not data.get("ok"):
            detail = str(data.get("description", "erro desconhecido"))[:500]
            detail = detail.replace(self.bot_token, "[REDACTED]")
            logger.error(
                "telegram_send_failed",
                status_code=response.status_code,
                detail=detail,
            )
            raise TelegramSendError(response.status_code, detail)

        return data
