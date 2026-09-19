"""Определения общих типов, псевдонимов и протоколов для библиотеки async-ffmpeg."""

import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from async_ffmpeg.progress import ProgressInfo

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

# Типы элементарных медиапотоков
type StreamType = Literal[
    "video",
    "audio",
    "subtitle",
    "data",
    "attachment",
]

# Коллбэки для отслеживания прогресса и потока stderr
type ProgressCallback = (
    Callable[["ProgressInfo"], None] | Callable[["ProgressInfo"], Awaitable[None]]
)
type StderrCallback = Callable[[str], None] | Callable[[str], Awaitable[None]]


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
