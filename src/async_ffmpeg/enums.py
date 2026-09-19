"""Строго типизированные перечисления и пресеты для медиаформатов, кодеков и контейнеров.

Предоставляет:
- `AudioFormat`: форматы аудиодорожек (mp3, m4a, flac, opus, wav, aac и др.).
- `VideoContainer`: популярные контейнеры медиа (mp4, mkv, webm, mov и др.).
- `VideoCodec`: стандартные видеокодеки (libx264, libx265, libsvtav1, copy и др.).
- `AudioCodec`: стандартные аудиокодеки (aac, libmp3lame, libopus, copy и др.).
- `Resolution`: пресеты стандартных разрешений (SD, HD, Full HD, 2K, 4K).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class AudioFormat(StrEnum):
    """Поддерживаемые аудиоформаты для извлечения и конвертации звуковых дорожек."""

    MP3 = "mp3"
    M4A = "m4a"
    FLAC = "flac"
    OPUS = "opus"
    WAV = "wav"
    AAC = "aac"
    ALAC = "alac"
    VORBIS = "vorbis"
    BEST = "best"


class VideoContainer(StrEnum):
    """Популярные медиа-контейнеры для сохранения, ремуксинга и кодирования."""

    MP4 = "mp4"
    MKV = "mkv"
    WEBM = "webm"
    MOV = "mov"
    AVI = "avi"
    FLV = "flv"
    TS = "ts"


class VideoCodec(StrEnum):
    """Основные видеокодеки FFmpeg для транскодирования."""

    H264 = "libx264"
    H265 = "libx265"
    AV1 = "libsvtav1"
    VP9 = "libvpx-vp9"
    COPY = "copy"


class AudioCodec(StrEnum):
    """Основные аудиокодеки FFmpeg для сжатия и транскодирования."""

    AAC = "aac"
    MP3 = "libmp3lame"
    OPUS = "libopus"
    FLAC = "flac"
    COPY = "copy"


class Resolution:
    """Пресеты стандартных медиа-разрешений в формате `(ширина, высота)`."""

    SD_360P: Final[tuple[int, int]] = (640, 360)
    SD_480P: Final[tuple[int, int]] = (854, 480)
    HD_720P: Final[tuple[int, int]] = (1280, 720)
    FHD_1080P: Final[tuple[int, int]] = (1920, 1080)
    QHD_1440P: Final[tuple[int, int]] = (2560, 1440)
    UHD_4K: Final[tuple[int, int]] = (3840, 2160)
