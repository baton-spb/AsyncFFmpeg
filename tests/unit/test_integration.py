"""Тесты модуля интеграции с async-yt-dlp (Phase 15)."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from aio_ffmpeg import FFmpegClient
from aio_ffmpeg.integration import (
    DownloadPostProcessor,
    PostProcessResult,
    extract_download_audio,
    process_download_result,
    transcode_download,
)


@dataclass
class FakeDownloadResult:
    """Имитация результата скачивания из библиотеки async-yt-dlp."""

    filepath: Path
    title: str | None = "Test Video Title"
    duration: float | None = 1.0


@pytest.fixture
async def sample_download_file(tmp_path: Path) -> FakeDownloadResult:
    """Создает реальный валидный тестовый медиафайл для постобработки."""
    raw_path = tmp_path / "downloaded_raw.mp4"
    client = FFmpegClient()
    cmd = (
        client.create_command()
        .overwrite()
        .input("color=c=magenta:s=320x240:d=1.0", f="lavfi")
        .input("sine=frequency=1000:d=1.0", f="lavfi")
        .video_codec("libx264")
        .preset("ultrafast")
        .audio_codec("aac")
        .output(raw_path)
    )
    res = await cmd.execute()
    assert res.success
    return FakeDownloadResult(filepath=raw_path, title="My Awesome Stream", duration=1.0)


@pytest.mark.asyncio
async def test_process_download_result_transcode(sample_download_file: FakeDownloadResult) -> None:
    """Проверяет транскодирование объекта DownloadResultProtocol."""
    res = await process_download_result(
        sample_download_file,
        resolution=(160, 120),
        video_codec="libx264",
        crf=28,
    )
    assert isinstance(res, PostProcessResult)
    assert res.result.success
    assert res.output.exists()
    assert res.title == "My Awesome Stream"
    assert res.media_info is not None
    assert res.media_info.primary_video is not None
    assert res.media_info.primary_video.width == 160
    assert res.media_info.primary_video.height == 120


@pytest.mark.asyncio
async def test_process_download_result_extract_audio(
    sample_download_file: FakeDownloadResult,
) -> None:
    """Проверяет извлечение аудиодорожки из результата скачивания."""
    res = await extract_download_audio(
        sample_download_file,
        codec="aac",
        bitrate="64k",
    )
    assert res.result.success
    assert res.output.exists()
    assert res.media_info is not None
    assert res.media_info.has_audio
    assert not res.media_info.has_video


@pytest.mark.asyncio
async def test_process_download_result_convert(sample_download_file: FakeDownloadResult) -> None:
    """Проверяет быструю смену контейнера (convert)."""
    res = await process_download_result(
        sample_download_file,
        action="convert",
    )
    assert res.result.success
    assert res.output.exists()
    assert res.output.name.endswith("_converted.mp4")


@pytest.mark.asyncio
async def test_download_post_processor_callable(sample_download_file: FakeDownloadResult) -> None:
    """Проверяет использование DownloadPostProcessor как callable хука."""
    processor = DownloadPostProcessor(
        action="transcode",
        resolution=(128, 96),
    )
    res = await processor(sample_download_file)
    assert res.result.success
    assert res.output.exists()
    assert res.media_info is not None
    assert res.media_info.primary_video is not None
    assert res.media_info.primary_video.width == 128


@pytest.mark.asyncio
async def test_transcode_download_function(sample_download_file: FakeDownloadResult) -> None:
    """Проверяет вызов функции transcode_download."""
    res = await transcode_download(
        sample_download_file,
        resolution=(128, 96),
        video_codec="libx264",
    )
    assert res.result.success
    assert res.output.exists()
    assert res.media_info is not None
    assert res.media_info.primary_video is not None
    assert res.media_info.primary_video.width == 128
