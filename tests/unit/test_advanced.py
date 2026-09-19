"""Unit и интеграционные тесты для расширенных методов FFmpegClient (two_pass, contact sheet, silence)."""

from pathlib import Path

import pytest

from async_ffmpeg.client import FFmpegClient
from async_ffmpeg.models import SilenceInterval


@pytest.fixture
async def sample_video_file(tmp_path: Path) -> Path:
    """Создает тестовый видеофайл длительностью 1.0 секунды со звуком."""
    out_file = tmp_path / "sample_video.mp4"
    client = FFmpegClient()
    cmd = (
        client.create_command()
        .overwrite()
        .input("color=c=navy:s=320x240:d=1.0:r=20", f="lavfi")
        .input("sine=frequency=800:duration=1.0", f="lavfi")
        .video_codec("libx264")
        .preset("ultrafast")
        .audio_codec("aac")
        .output(out_file)
    )
    res = await cmd.execute()
    assert res.success
    return out_file


@pytest.fixture
async def sample_audio_with_silence(tmp_path: Path) -> Path:
    """Создает аудиофайл с явным периодом тишины (0.8с звук + 1.2с пауза + 0.5с звук)."""
    out_file = tmp_path / "audio_with_silence.wav"
    client = FFmpegClient()
    # Формируем цепочку через lavfi
    cmd = (
        client.create_command()
        .overwrite()
        .input("aevalsrc=sin(2*PI*440*t):d=0.8", f="lavfi")
        .input("aevalsrc=0:d=1.2", f="lavfi")
        .input("aevalsrc=sin(2*PI*880*t):d=0.5", f="lavfi")
        .complex_filter("[0:a][1:a][2:a]concat=n=3:v=0:a=1[outa]")
        .map("[outa]")
        .output(out_file)
    )
    res = await cmd.execute()
    assert res.success
    return out_file


def test_silence_interval_model() -> None:
    """Проверка создания и свойств объекта SilenceInterval."""
    interval = SilenceInterval(start=1.5, end=4.0, duration=2.5)
    assert interval.start == 1.5
    assert interval.end == 4.0
    assert interval.duration == 2.5


@pytest.mark.asyncio
async def test_two_pass_transcode(sample_video_file: Path, tmp_path: Path) -> None:
    """Проверка двухпроходного кодирования (2-pass transcode)."""
    client = FFmpegClient()
    out_file = tmp_path / "two_pass_result.mp4"

    res = await client.two_pass_transcode(
        input=sample_video_file,
        output=out_file,
        video_codec="libx264",
        bitrate="250k",
        preset="ultrafast",
        audio_codec="aac",
        audio_bitrate="64k",
    )

    assert res.success is True
    assert out_file.exists()
    assert out_file.stat().st_size > 0

    info = await client.probe(out_file)
    assert info.primary_video is not None
    assert info.primary_audio is not None


@pytest.mark.asyncio
async def test_create_contact_sheet(sample_video_file: Path, tmp_path: Path) -> None:
    """Проверка генерации обзорной раскадровки (contact sheet / storyboard)."""
    client = FFmpegClient()
    out_sheet = tmp_path / "storyboard.jpg"

    res = await client.create_contact_sheet(
        input=sample_video_file,
        output=out_sheet,
        rows=2,
        cols=2,
        width=160,
        frame_interval=0.2,
    )

    assert res.success is True
    assert out_sheet.exists()
    assert out_sheet.stat().st_size > 0

    info = await client.probe(out_sheet)
    assert info.primary_video is not None
    # 2 колонки по 160 = 320 ширина
    assert info.primary_video.width == 320


@pytest.mark.asyncio
async def test_detect_silence(sample_audio_with_silence: Path) -> None:
    """Проверка детекции участков тишины через фильтр silencedetect."""
    client = FFmpegClient()

    intervals = await client.detect_silence(
        input=sample_audio_with_silence,
        noise_tolerance_db=-30.0,
        min_duration=0.5,
    )

    assert len(intervals) >= 1
    # Тишина должна быть зафиксирована в районе от 0.8с до 2.0с (длительность ~1.2с)
    first_silence = intervals[0]
    assert 0.7 <= first_silence.start <= 0.9
    assert first_silence.duration >= 0.5


@pytest.mark.asyncio
async def test_detect_silence_empty_output(tmp_path: Path) -> None:
    """Проверка возврата пустого списка, если в аудиофайле нет периодов тишины."""
    client = FFmpegClient()
    sine_file = tmp_path / "constant_sine.wav"
    await (
        client.create_command()
        .overwrite()
        .input("sine=frequency=440:duration=1.0", f="lavfi")
        .output(sine_file)
        .execute()
    )

    intervals = await client.detect_silence(
        input=sine_file,
        noise_tolerance_db=-20.0,
        min_duration=0.5,
    )
    assert intervals == []
