"""aio-ffmpeg — асинхронная, строго типизированная библиотека-обёртка над FFmpeg и FFprobe.

Предоставляет полный доступ к API async_ffmpeg под псевдонимом aio_ffmpeg.
"""

from async_ffmpeg import *  # noqa: F403
from async_ffmpeg import __all__ as _async_ffmpeg_all
from async_ffmpeg import __version__

__all__ = [*_async_ffmpeg_all, "__version__"]
