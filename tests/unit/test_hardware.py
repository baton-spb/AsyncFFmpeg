"""Unit-тесты для модуля аппаратного ускорения (hardware.py)."""

import pytest

from aio_ffmpeg.command import FFmpegCommand
from aio_ffmpeg.hardware import (
    DecoderInfo,
    EncoderInfo,
    HardwareAccel,
    HardwareCapability,
    HWAccelConfig,
    get_hwaccel_args,
    parse_decoders_output,
    parse_encoders_output,
    parse_hwaccels_output,
)

SAMPLE_HWACCELS_OUTPUT = """
ffmpeg version 9.0.1 Copyright (c) 2000-2026 the FFmpeg developers
Hardware acceleration methods:
cuda
dxva2
qsv
d3d11va
opencl
vulkan
amf
"""

SAMPLE_ENCODERS_OUTPUT = """
Encoders:
 V..... = Video
 A..... = Audio
 S..... = Subtitle
 .F.... = Frame-level multithreading
 ..S... = Slice-level multithreading
 ...X.. = Experimental
 ....B. = Supports draw_horiz_band
 .....D = Direct rendering method
 ------
 V....D h264_nvenc           NVIDIA NVENC H.264 encoder (codec h264)
 V..... h264_qsv             H.264 / AVC (Intel Quick Sync Video acceleration) (codec h264)
 V....D h264_amf             AMD AMF H.264 Encoder (codec h264)
 V....D h264_mf              H.264 / AVC via MediaFoundation (codec h264)
 V.S..D libx264              libx264 H.264 / AVC / MPEG-4 AVC (codec h264)
 V....D libx265              libx265 H.265 / HEVC (codec hevc)
 A....D aac                  AAC (Advanced Audio Coding)
 S..... srt                  SubRip subtitle
"""

SAMPLE_DECODERS_OUTPUT = """
Decoders:
 V..... = Video
 A..... = Audio
 S..... = Subtitle
 ------
 V..... h264_cuvid           Nvidia CUVID H264 decoder (codec h264)
 V....D h264_qsv             H264 video (Intel Quick Sync Video acceleration) (codec h264)
 V.S..D h264                 H.264 / AVC / MPEG-4 AVC
 A....D mp3                  MP3 (MPEG audio layer 3)
"""


def test_parse_hwaccels_output() -> None:
    """Проверка извлечения списка аппаратных ускорителей из вывода FFmpeg."""
    accels = parse_hwaccels_output(SAMPLE_HWACCELS_OUTPUT)
    assert "cuda" in accels
    assert "d3d11va" in accels
    assert "amf" in accels
    assert "qsv" in accels
    assert len(accels) == 7


def test_parse_encoders_output() -> None:
    """Проверка парсинга списка энкодеров и выявления аппаратных возможностей."""
    encoders = parse_encoders_output(SAMPLE_ENCODERS_OUTPUT)
    enc_by_name = {e.name: e for e in encoders}

    assert "h264_nvenc" in enc_by_name
    nvenc = enc_by_name["h264_nvenc"]
    assert nvenc.codec == "h264"
    assert nvenc.is_hardware is True
    assert nvenc.vendor == "nvidia"
    assert nvenc.media_type == "video"

    assert "libx264" in enc_by_name
    x264 = enc_by_name["libx264"]
    assert x264.is_hardware is False
    assert x264.slice_threading is True

    assert "h264_mf" in enc_by_name
    mf = enc_by_name["h264_mf"]
    assert mf.is_hardware is True
    assert mf.vendor == "microsoft"

    assert "aac" in enc_by_name
    aac = enc_by_name["aac"]
    assert aac.media_type == "audio"


def test_parse_decoders_output() -> None:
    """Проверка парсинга списка декодеров."""
    decoders = parse_decoders_output(SAMPLE_DECODERS_OUTPUT)
    dec_by_name = {d.name: d for d in decoders}

    assert "h264_cuvid" in dec_by_name
    cuvid = dec_by_name["h264_cuvid"]
    assert cuvid.is_hardware is True
    assert cuvid.vendor == "nvidia"

    assert "h264" in dec_by_name
    sw_h264 = dec_by_name["h264"]
    assert sw_h264.is_hardware is False


def test_hwaccel_config_and_args() -> None:
    """Проверка генерации аргументов командной строки аппаратного ускорения."""
    cfg = HWAccelConfig("cuda", device="0", output_format="cuda")
    args = cfg.to_ffmpeg_args()
    assert args == [
        "-hwaccel",
        "cuda",
        "-hwaccel_device",
        "0",
        "-hwaccel_output_format",
        "cuda",
    ]

    helper_args = get_hwaccel_args("d3d11va", output_format="d3d11")
    assert helper_args == ["-hwaccel", "d3d11va", "-hwaccel_output_format", "d3d11"]


def test_hardware_capability_properties() -> None:
    """Проверка вычисляемых свойств модели возможностей оборудования."""
    encoders = (
        EncoderInfo("h264_nvenc", "h264", "NVENC", "video", True, "nvidia"),
        EncoderInfo("h264_mf", "h264", "MF", "video", True, "microsoft"),
        EncoderInfo("libx264", "h264", "x264", "video", False, "generic"),
    )
    decoders = (DecoderInfo("h264_cuvid", "h264", "CUVID", "video", True, "nvidia"),)

    cap = HardwareCapability(
        available_accels=("cuda", "d3d11va", "dxva2"),
        encoders=encoders,
        decoders=decoders,
    )

    assert cap.has_cuda is True
    assert cap.has_nvenc is True
    assert cap.has_d3d11va is True
    assert cap.has_dxva2 is True
    assert cap.has_mediafoundation is True
    assert cap.has_qsv is False
    assert cap.has_amf is False


def test_command_hwaccel_integration() -> None:
    """Проверка добавления флагов -hwaccel в FFmpegCommand."""
    cmd = (
        FFmpegCommand()
        .hwaccel("cuda", device="0", output_format="cuda")
        .input("input.mp4")
        .output("output.mp4")
    )
    built = cmd.build()

    # Опции hwaccel должны предшествовать -i input.mp4
    hwaccel_idx = built.index("-hwaccel")
    input_idx = built.index("-i")
    assert hwaccel_idx < input_idx
    assert built[hwaccel_idx + 1] == "cuda"
    assert built[built.index("-hwaccel_device") + 1] == "0"
    assert built[built.index("-hwaccel_output_format") + 1] == "cuda"


@pytest.mark.asyncio
async def test_hardware_accel_real_discovery() -> None:
    """Интеграционный тест: опрос реальных возможностей текущей системы через FFmpeg."""
    hw = HardwareAccel()

    accels = await hw.get_available_accels()
    assert isinstance(accels, tuple)
    assert len(accels) > 0

    encoders = await hw.get_available_encoders()
    assert isinstance(encoders, tuple)
    assert len(encoders) > 0
    enc_names = {e.name for e in encoders}
    assert "libx264" in enc_names

    cap = await hw.detect_hardware()
    assert isinstance(cap, HardwareCapability)

    # Программный энкодер всегда должен работать
    assert await hw.test_encoder("libx264") is True

    # Несуществующий энкодер должен возвращать False
    assert await hw.test_encoder("nonexistent_encoder_xyz") is False

    # Проверка выбора программного энкодера при prefer_hw=False
    best_sw = await hw.best_encoder("h264", prefer_hw=False)
    assert best_sw == "libx264"

    # Проверка интеллектуального выбора при prefer_hw=True
    best_hw = await hw.best_encoder("h264", prefer_hw=True, verify_working=True)
    assert isinstance(best_hw, str)
    assert len(best_hw) > 0
