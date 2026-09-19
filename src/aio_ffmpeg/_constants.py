"""Константы и конфигурация по умолчанию для библиотеки async-ffmpeg."""

from typing import Final

__version__: Final[str] = "0.1.2"

# Имена исполняемых файлов по умолчанию
DEFAULT_FFMPEG_EXECUTABLE: Final[str] = "ffmpeg"
DEFAULT_FFPROBE_EXECUTABLE: Final[str] = "ffprobe"

# Переменные окружения для переопределения путей
ENV_FFMPEG_PATH: Final[str] = "FFMPEG_PATH"
ENV_FFPROBE_PATH: Final[str] = "FFPROBE_PATH"
ENV_MAX_CONCURRENT: Final[str] = "ASYNC_FFMPEG_MAX_CONCURRENT"
ENV_TIMEOUT: Final[str] = "ASYNC_FFMPEG_TIMEOUT"

# Ограничения конкурентности и буферизации
DEFAULT_MAX_CONCURRENT: Final[int] = 4
DEFAULT_READ_BUFFER_SIZE: Final[int] = 64 * 1024  # 64 КБ

# Таймауты завершения процессов (в секундах)
GRACEFUL_SHUTDOWN_TIMEOUT: Final[float] = 5.0
FORCE_KILL_TIMEOUT: Final[float] = 2.0
DEFAULT_PROBE_TIMEOUT: Final[float] = 30.0

# Параметры FFmpeg по умолчанию
DEFAULT_STATS_PERIOD: Final[float] = 0.5
DEFAULT_LOGLEVEL: Final[str] = "error"
DEFAULT_AUDIO_BITRATE: Final[str] = "128k"
DEFAULT_VIDEO_CRF: Final[int] = 23
DEFAULT_VIDEO_PRESET: Final[str] = "medium"
