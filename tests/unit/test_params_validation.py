"""Модульные тесты для перечислений (enums) и валидации параметров в AsyncFFmpeg."""

from __future__ import annotations

import pytest

from async_ffmpeg import (
    AudioCodec,
    AudioFormat,
    FFmpegClient,
    FFmpegCommand,
    MediaPipeline,
    Resolution,
    VideoCodec,
    VideoContainer,
)


def test_ffmpeg_enums_values() -> None:
    """Проверяет значения типизированных перечислений кодеков и пресетов разрешения."""
    assert VideoCodec.H264 == "libx264"
    assert VideoCodec.H265 == "libx265"
    assert VideoCodec.AV1 == "libsvtav1"
    assert VideoCodec.COPY == "copy"

    assert AudioCodec.AAC == "aac"
    assert AudioCodec.MP3 == "libmp3lame"
    assert AudioCodec.OPUS == "libopus"
    assert AudioCodec.COPY == "copy"

    assert VideoContainer.MP4 == "mp4"
    assert VideoContainer.MKV == "mkv"
    assert VideoContainer.WEBM == "webm"

    assert AudioFormat.MP3 == "mp3"
    assert AudioFormat.FLAC == "flac"

    assert Resolution.SD_360P == (640, 360)
    assert Resolution.HD_720P == (1280, 720)
    assert Resolution.FHD_1080P == (1920, 1080)
    assert Resolution.UHD_4K == (3840, 2160)


def test_ffmpeg_command_codec_and_crf_validation() -> None:
    """Проверяет установку кодеков и валидацию диапазона CRF в FFmpegCommand."""
    cmd = FFmpegCommand()
    cmd.video_codec(VideoCodec.H264)
    cmd.audio_codec(AudioCodec.AAC)
    cmd.crf(20)

    with pytest.raises(ValueError, match=r"crf должен быть в диапазоне от 0 до 51"):
        cmd.crf(-1)

    with pytest.raises(ValueError, match=r"crf должен быть в диапазоне от 0 до 51"):
        cmd.crf(52)


def test_ffmpeg_command_resolution_and_fps_validation() -> None:
    """Проверяет валидацию разрешения и частоты кадров в FFmpegCommand."""
    cmd = FFmpegCommand()
    cmd.resolution(Resolution.HD_720P)
    cmd.fps(60)
    cmd.frames(100)

    with pytest.raises(ValueError, match=r"Размеры кадра должны быть строго положительными"):
        cmd.resolution(0, 1080)

    with pytest.raises(ValueError, match=r"Размеры кадра должны быть строго положительными"):
        cmd.resolution((-100, 200))

    with pytest.raises(ValueError, match=r"Необходимо указать высоту"):
        cmd.resolution(1920)  # type: ignore[call-overload]

    with pytest.raises(ValueError, match=r"fps.*должна быть > 0"):
        cmd.fps(0)

    with pytest.raises(ValueError, match=r"fps.*должна быть > 0"):
        cmd.fps(-1)

    with pytest.raises(ValueError, match=r"Количество кадров должно быть > 0"):
        cmd.frames(0)

    with pytest.raises(ValueError, match=r"Количество кадров должно быть > 0"):
        cmd.frames(-5)


@pytest.mark.asyncio
async def test_client_transcode_validation() -> None:
    """Проверяет валидацию аргументов в FFmpegClient.transcode."""
    client = FFmpegClient()

    with pytest.raises(ValueError, match=r"crf должен быть в диапазоне от 0 до 51"):
        await client.transcode("in.mp4", "out.mp4", crf=55)

    with pytest.raises(ValueError, match=r"fps.*должен быть > 0"):
        await client.transcode("in.mp4", "out.mp4", fps=-10)

    with pytest.raises(ValueError, match=r"Размеры кадра должны быть строго положительными"):
        await client.transcode("in.mp4", "out.mp4", resolution=(0, 720))

    with pytest.raises(ValueError, match=r"start должен быть >= 0"):
        await client.transcode("in.mp4", "out.mp4", start=-1.0)

    with pytest.raises(ValueError, match=r"duration должен быть > 0"):
        await client.transcode("in.mp4", "out.mp4", duration=0)


@pytest.mark.asyncio
async def test_client_trim_validation() -> None:
    """Проверяет валидацию временных меток в FFmpegClient.trim."""
    client = FFmpegClient()

    with pytest.raises(ValueError, match=r"start должен быть >= 0"):
        await client.trim("in.mp4", "out.mp4", start=-5.0)

    with pytest.raises(ValueError, match=r"duration должен быть > 0"):
        await client.trim("in.mp4", "out.mp4", duration=-1.0)

    with pytest.raises(ValueError, match=r"end.*должна быть больше начальной start"):
        await client.trim("in.mp4", "out.mp4", start=10.0, end=5.0)


@pytest.mark.asyncio
async def test_client_scale_validation() -> None:
    """Проверяет валидацию размеров и CRF в FFmpegClient.scale."""
    client = FFmpegClient()

    with pytest.raises(ValueError, match=r"Размеры кадра должны быть строго положительными"):
        await client.scale("in.mp4", "out.mp4", width=0, height=720)

    with pytest.raises(ValueError, match=r"crf должен быть в диапазоне от 0 до 51"):
        await client.scale("in.mp4", "out.mp4", width=1280, height=720, crf=-2)

    with pytest.raises(ValueError, match=r"Необходимо указать высоту"):
        await client.scale("in.mp4", "out.mp4", width=1280)  # type: ignore[call-overload]


def test_media_pipeline_validation() -> None:
    """Проверяет валидацию аргументов в MediaPipeline."""
    pipe = MediaPipeline("input.mp4")

    # Scale
    pipe.scale(Resolution.FHD_1080P)
    assert len(pipe._video_filters) == 1

    with pytest.raises(ValueError, match=r"Размеры кадра должны быть строго положительными"):
        pipe.scale(0, 1080)

    with pytest.raises(ValueError, match=r"Необходимо указать высоту"):
        pipe.scale(1920)  # type: ignore[call-overload]

    # Codecs and CRF
    pipe.video_codec(VideoCodec.H264, crf=28)
    assert pipe._video_codec == "libx264"
    assert pipe._video_crf == 28

    with pytest.raises(ValueError, match=r"crf должен быть в диапазоне от 0 до 51"):
        pipe.video_codec(VideoCodec.H265, crf=60)

    with pytest.raises(ValueError, match=r"crf должен быть в диапазоне от 0 до 51"):
        pipe.crf(-1)

    pipe.audio_codec(AudioCodec.OPUS, bitrate="128k")
    assert pipe._audio_codec == "libopus"

    # Trim
    pipe.trim(start=1.0, duration=10.0)

    with pytest.raises(ValueError, match=r"start должен быть >= 0"):
        pipe.trim(start=-1.0)

    with pytest.raises(ValueError, match=r"duration должен быть > 0"):
        pipe.trim(duration=0)

    with pytest.raises(ValueError, match=r"end.*должна быть больше начальной start"):
        pipe.trim(start=10.0, end=8.0)
