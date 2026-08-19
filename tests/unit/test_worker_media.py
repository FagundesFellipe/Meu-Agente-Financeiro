import httpx

from financial_agent.worker.media import shared, telegram


async def test_telegram_download_resolves_file_id_then_downloads_file(
    monkeypatch,
) -> None:
    requests: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.path.endswith("/getFile"):
            assert request.url.params["file_id"] == "telegram-file-id"
            return httpx.Response(
                200, json={"ok": True, "result": {"file_path": "voice/a.ogg"}}
            )
        return httpx.Response(200, content=b"audio")

    original_async_client = httpx.AsyncClient
    monkeypatch.setattr(telegram, "_bot_token", lambda: "test-token")
    monkeypatch.setattr(
        telegram.httpx,
        "AsyncClient",
        lambda **kwargs: original_async_client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )

    assert await telegram.download_media("telegram-file-id") == b"audio"
    assert requests == [
        "https://api.telegram.org/bottest-token/getFile?file_id=telegram-file-id",
        "https://api.telegram.org/file/bottest-token/voice/a.ogg",
    ]


async def test_preprocess_delegates_audio_download_and_transcription(
    monkeypatch,
) -> None:
    async def download_media(file_id: str) -> bytes:
        assert file_id == "file-id"
        return b"audio"

    async def transcribe_audio(media: bytes, media_type: str) -> str:
        assert media == b"audio"
        assert media_type == "audio/ogg"
        return "gastei dez reais"

    monkeypatch.setattr(shared, "transcribe_audio", transcribe_audio)

    result = await shared.preprocess_incoming_message(
        "", "file-id", "audio/ogg", download_media
    )

    assert result.should_invoke_agent is True
    assert result.normalized_text == "[Transcrição de áudio]: gastei dez reais"
    assert result.media_processing_status == "processed"


async def test_preprocess_does_not_expose_exception_details() -> None:
    async def download_media(_: str) -> bytes:
        raise RuntimeError("https://api.telegram.org/botsecret-token/getFile")

    result = await shared.preprocess_incoming_message(
        "", "file-id", "audio/ogg", download_media
    )

    assert result.should_invoke_agent is False
    assert result.media_processing_error == "media_preprocessing_failed"
    assert "secret-token" not in result.media_processing_error
