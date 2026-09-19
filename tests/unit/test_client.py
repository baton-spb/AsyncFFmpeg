"""Unit и интеграционные тесты для высокоуровневого клиента FFmpegClient (client.py)."""

from pathlib import Path

import pytest

from async_ffmpeg.client import FFmpegClient
from async_ffmpeg.exceptions import InvalidInputError
from async_ffmpeg.progress import ProgressInfo


@pytest.fixture
async def sample_video(tmp_path: Path) -> Path:
    """Создает реальный тестовый медиафайл (1 сек, видео + аудио) через FFmpegClient."""
    out_file = tmp_path / "source.mp4"
    client = FFmpegClient()
    cmd = (
        client.create_command()
        .overwrite()
        .input("color=c=blue:s=320x240:d=1.0:r=25", f="lavfi")
        .input("sine=frequency=1000:duration=1.0", f="lavfi")
        .video_codec("libx264")
        .preset("ultrafast")
        .audio_codec("aac")
        .output(out_file)
    )
    res = await cmd.execute()
    assert res.success
    assert out_file.exists()
    return out_file


def test_client_init_and_properties() -> None:
    """Проверка инициализации свойств и вложенных компонентов клиента."""
    client = FFmpegClient(max_concurrent=3, default_timeout=45.0)
    assert client.active_processes == 0
    assert client.runner is not None
    assert client.ffprobe is not None
    assert client.hardware is not None


@pytest.mark.asyncio
async def test_client_context_manager() -> None:
    """Проверка работы асинхронного контекстного менеджера FFmpegClient."""
    async with FFmpegClient(max_concurrent=2) as client:
        assert client.active_processes == 0
        cmd = (
            client.create_command()
            .overwrite()
            .input("color=c=black:s=64x64:d=0.1", f="lavfi")
            .video_codec("libx264")
            .preset("ultrafast")
            .output_option("f", "null")
            .output("NUL")
        )
        res = await cmd.execute()
        assert res.success


@pytest.mark.asyncio
async def test_client_probe(sample_video: Path) -> None:
    """Проверка анализа медиафайла через client.probe()."""
    client = FFmpegClient()
    info = await client.probe(sample_video)

    assert info.has_video is True
    assert info.has_audio is True
    assert info.duration is not None
    assert info.duration > 0.8
    assert info.resolution == (320, 240)
    assert info.primary_video is not None
    assert info.primary_video.codec_name == "h264"


@pytest.mark.asyncio
async def test_client_transcode_with_progress(sample_video: Path, tmp_path: Path) -> None:
    """Проверка транскодирования с расчетом процентов прогресса."""
    out_file = tmp_path / "transcoded.mp4"
    client = FFmpegClient()

    progress_events: list[ProgressInfo] = []

    def on_prog(info: ProgressInfo) -> None:
        progress_events.append(info)

    result = await client.transcode(
        sample_video,
        out_file,
        resolution=(160, 120),
        fps=15,
        preset="ultrafast",
        crf=28,
        on_progress=on_prog,
    )

    assert result.success is True
    assert out_file.exists()
    assert out_file.stat().st_size > 0
    assert len(progress_events) > 0

    # Проверяем, что выходной файл имеет новый размер
    info = await client.probe(out_file)
    assert info.resolution == (160, 120)


@pytest.mark.asyncio
async def test_client_extract_audio(sample_video: Path, tmp_path: Path) -> None:
    """Проверка извлечения звуковой дорожки."""
    out_audio = tmp_path / "extracted.m4a"
    client = FFmpegClient()

    result = await client.extract_audio(
        sample_video,
        out_audio,
        codec="aac",
        bitrate="96k",
    )

    assert result.success is True
    assert out_audio.exists()
    info = await client.probe(out_audio)
    assert info.has_video is False
    assert info.has_audio is True
    assert info.primary_audio is not None
    assert info.primary_audio.codec_name == "aac"


@pytest.mark.asyncio
async def test_client_trim(sample_video: Path, tmp_path: Path) -> None:
    """Проверка обрезки видео."""
    out_trimmed = tmp_path / "trimmed.mp4"
    client = FFmpegClient()

    result = await client.trim(
        sample_video,
        out_trimmed,
        start=0.2,
        duration=0.5,
        copy=False,
    )

    assert result.success is True
    assert out_trimmed.exists()
    info = await client.probe(out_trimmed)
    assert info.duration is not None
    assert 0.3 <= info.duration <= 0.7


@pytest.mark.asyncio
async def test_client_screenshot(sample_video: Path, tmp_path: Path) -> None:
    """Проверка создания одиночного скриншота."""
    out_img = tmp_path / "shot.jpg"
    client = FFmpegClient()

    result = await client.screenshot(
        sample_video,
        out_img,
        timestamp=0.2,
        resolution=(160, 120),
    )

    assert result.success is True
    assert out_img.exists()
    assert out_img.stat().st_size > 0


@pytest.mark.asyncio
async def test_client_thumbnails(sample_video: Path, tmp_path: Path) -> None:
    """Проверка создания серии превью."""
    pattern = tmp_path / "thumb_%02d.jpg"
    client = FFmpegClient()

    result = await client.thumbnails(
        sample_video,
        pattern,
        fps=2,
        resolution=(100, 75),
    )

    assert result.success is True
    generated = list(tmp_path.glob("thumb_*.jpg"))
    assert len(generated) >= 1


@pytest.mark.asyncio
async def test_client_convert(sample_video: Path, tmp_path: Path) -> None:
    """Проверка быстрой конвертации контейнера без перекодирования."""
    out_mkv = tmp_path / "converted.mkv"
    client = FFmpegClient()

    result = await client.convert(
        sample_video,
        out_mkv,
        copy=True,
    )

    assert result.success is True
    assert out_mkv.exists()
    info = await client.probe(out_mkv)
    assert info.format_name is not None
    assert "matroska" in info.format_name


@pytest.mark.asyncio
async def test_client_normalize_audio(sample_video: Path, tmp_path: Path) -> None:
    """Проверка нормализации звука loudnorm."""
    out_norm = tmp_path / "normalized.mp4"
    client = FFmpegClient()

    result = await client.normalize_audio(
        sample_video,
        out_norm,
        target_lufs=-16.0,
    )

    assert result.success is True
    assert out_norm.exists()


@pytest.mark.asyncio
async def test_client_scale(sample_video: Path, tmp_path: Path) -> None:
    """Проверка масштабирования видео."""
    out_scaled = tmp_path / "scaled.mp4"
    client = FFmpegClient()

    result = await client.scale(
        sample_video,
        out_scaled,
        width=200,
        height=150,
        preset="ultrafast",
    )

    assert result.success is True
    assert out_scaled.exists()
    info = await client.probe(out_scaled)
    assert info.resolution == (200, 150)


@pytest.mark.asyncio
async def test_client_concat_filter(sample_video: Path, tmp_path: Path) -> None:
    """Проверка объединения файлов через комплексный фильтр concat."""
    out_concat = tmp_path / "concatenated.mp4"
    client = FFmpegClient()

    result = await client.concat(
        [sample_video, sample_video],
        out_concat,
        method="filter",
    )

    assert result.success is True
    assert out_concat.exists()
    info = await client.probe(out_concat)
    assert info.duration is not None
    assert info.duration > 1.5


@pytest.mark.asyncio
async def test_client_concat_demuxer(sample_video: Path, tmp_path: Path) -> None:
    """Проверка объединения файлов через concat demuxer без перекодирования."""
    out_demuxed = tmp_path / "concat_demux.mp4"
    client = FFmpegClient()

    result = await client.concat(
        [sample_video, sample_video],
        out_demuxed,
        method="demuxer",
    )

    assert result.success is True
    assert out_demuxed.exists()
    info = await client.probe(out_demuxed)
    assert info.duration is not None
    assert info.duration > 1.5


@pytest.mark.asyncio
async def test_client_concat_empty_raises() -> None:
    """Проверка выброса исключения при пустом списке файлов для конкатенации."""
    client = FFmpegClient()
    with pytest.raises(InvalidInputError, match="не может быть пустым"):
        await client.concat([], "out.mp4")
