"""Определения общих типов, псевдонимов и протоколов для библиотеки async-ffmpeg."""

import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from aio_ffmpeg.enums import (
    AudioCodec,
    AudioFormat,
    Resolution,
    VideoCodec,
    VideoContainer,
)

if TYPE_CHECKING:
    from aio_ffmpeg.progress import ProgressInfo

# Псевдонимы путей файловой системы (PEP 695 type syntax)
type PathLike = str | os.PathLike[str] | Path

# Уровни логирования FFmpeg
type LogLevel = Literal[
    "quiet",
    "panic",
    "fatal",
    "error",
    "warning",
    "info",
    "verbose",
    "debug",
    "trace",
]

# Пресеты кодирования x264/x265
type VideoPreset = Literal[
    "ultrafast",
    "superfast",
    "veryfast",
    "faster",
    "fast",
    "medium",
    "slow",
    "slower",
    "veryslow",
    "placebo",
]

# Способы объединения файлов (конкатенации)
type ConcatMethod = Literal[
    "demuxer",
    "filter",
    "protocol",
]

# Позиционирование водяного знака / оверлея
type WatermarkPosition = Literal[
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
    "center",
]

# Типы элементарных медиапотоков
type StreamType = Literal[
    "video",
    "audio",
    "subtitle",
    "data",
    "attachment",
]

# Коллбэки для отслеживания прогресса и потоков вывода
type ProgressCallback = (
    Callable[["ProgressInfo"], None] | Callable[["ProgressInfo"], Awaitable[None]]
)
type StderrCallback = Callable[[str], None] | Callable[[str], Awaitable[None]]
type StdoutLineCallback = Callable[[str], None] | Callable[[str], Awaitable[None]]

# Допустимые типы значений параметров командной строки и фильтров
type CommandOptionValue = str | int | float | bool | Path | None
type FilterParamValue = str | int | float | bool
type ProbeRawDict = dict[str, object]


@runtime_checkable
class DownloadResultProtocol(Protocol):
    """Протокол совместимости с результатом скачивания (например, из async-yt-dlp).

    Позволяет принимать результаты загрузки без прямой зависимости от внешних пакетов.
    """

    @property
    def filepath(self) -> Path:
        """Абсолютный путь к загруженному файлу."""
        ...

    @property
    def title(self) -> str | None:
        """Название медиа (если доступно)."""
        ...

    @property
    def duration(self) -> float | None:
        """Длительность в секундах (если доступно)."""
        ...


@runtime_checkable
class MediaInputProtocol(Protocol):
    """Протокол для объектов, которые могут выступать источником медиаданных."""

    def to_ffmpeg_input(self) -> str:
        """Преобразование в строковый аргумент пути или URL для FFmpeg."""
        ...


__all__ = [
    "AudioCodec",
    "AudioFormat",
    "CommandOptionValue",
    "ConcatMethod",
    "DownloadResultProtocol",
    "FilterParamValue",
    "LogLevel",
    "MediaInputProtocol",
    "PathLike",
    "ProbeRawDict",
    "ProgressCallback",
    "Resolution",
    "StderrCallback",
    "StdoutLineCallback",
    "StreamType",
    "VideoCodec",
    "VideoContainer",
    "VideoPreset",
    "WatermarkPosition",
]
