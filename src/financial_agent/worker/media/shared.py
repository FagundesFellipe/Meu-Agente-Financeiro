"""Lógica comum para transformar mídia recebida em texto para o agente."""

from __future__ import annotations

import base64
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
import structlog

from shared.config import settings

logger = structlog.get_logger()

AUTO_RESPONSE_MEDIA_FAILURE = (
    "Estamos com dificuldades em processar imagens/audio. "
    "Por favor, mande mensagem de texto."
)
AUTO_RESPONSE_UNSUPPORTED_MEDIA = (
    "Este tipo de mídia não é suportado no momento. Por favor, mande mensagem de texto."
)

DownloadMedia = Callable[[str], Awaitable[bytes]]


@dataclass
class MediaPreprocessResult:
    """Resultado do pré-processamento de entrada antes do agente."""

    should_invoke_agent: bool
    normalized_text: str | None
    media_processing_status: str
    media_processing_error: str | None = None
    auto_response: str | None = None


def media_kind(media_type: str | None) -> str:
    """Classifica os MIME types de mídia atualmente suportados."""
    if not media_type:
        return "none"
    if media_type.lower().startswith("audio/"):
        return "audio"
    return "unsupported"


def audio_format_from_media_type(media_type: str) -> str:
    """Mapeia MIME type para um formato aceito em ``input_audio``."""
    normalized = media_type.lower()
    if "wav" in normalized or "wave" in normalized:
        return "wav"
    if "mpeg" in normalized or "mp3" in normalized:
        return "mp3"
    if "ogg" in normalized:
        return "ogg"
    if "webm" in normalized:
        return "webm"
    return "ogg"


def _extract_text(content: str | list | None) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        return "\n".join(text for text in texts if text)
    return str(content)


async def _chat_completion_media(messages: list[dict]) -> str:
    api_key = settings.openrouter_api_key
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY não configurada")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key.get_secret_value()}",
                "Content-Type": "application/json",
                "X-Title": "transcription",
            },
            json={
                "model": settings.openrouter_midia_model,
                "messages": messages,
                # user_id ainda não está disponível aqui — a transcrição roda
                # antes de ensure_user_node, dentro do grafo, resolver o usuário.
                "user": "transcription",
            },
            timeout=45.0,
        )
        response.raise_for_status()
        result = response.json()
        return _extract_text(result["choices"][0]["message"].get("content")).strip()


async def transcribe_audio(media_bytes: bytes, media_type: str) -> str:
    """Transcreve áudio e retorna exclusivamente o texto reconhecido."""
    audio_b64 = base64.b64encode(media_bytes).decode("utf-8")
    return await _chat_completion_media(
        [
            {
                "role": "system",
                "content": (
                    "Você é um transcritor técnico. Retorne somente a transcrição "
                    "literal do áudio, sem saudações, confirmação, comentários, "
                    "emojis ou prefixos."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Transcreva este áudio fielmente em português brasileiro. "
                            "A saída deve conter apenas a transcrição crua do conteúdo."
                        ),
                    },
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_b64,
                            "format": audio_format_from_media_type(media_type),
                        },
                    },
                ],
            },
        ]
    )


async def preprocess_incoming_message(
    body: str,
    media_url: str | None,
    media_type: str | None,
    download_media: DownloadMedia,
) -> MediaPreprocessResult:
    """Normaliza a entrada de um canal para texto antes da chamada ao agente."""
    if not media_url and not media_type:
        return MediaPreprocessResult(True, body, "none")
    if not media_url or not media_type or media_kind(media_type) != "audio":
        return MediaPreprocessResult(
            False, None, "unsupported", auto_response=AUTO_RESPONSE_UNSUPPORTED_MEDIA
        )

    try:
        media_bytes = await download_media(media_url)
        transcription = await transcribe_audio(media_bytes, media_type)
        normalized = "\n".join(
            part
            for part in [body.strip(), f"[Transcrição de áudio]: {transcription}"]
            if part
        )
        return MediaPreprocessResult(True, normalized, "processed")
    except Exception as exc:
        logger.error(
            "media_preprocessing_failed",
            media_type=media_type,
            error_type=type(exc).__name__,
        )
        return MediaPreprocessResult(
            False,
            None,
            "failed",
            media_processing_error="media_preprocessing_failed",
            auto_response=AUTO_RESPONSE_MEDIA_FAILURE,
        )
