"""Backward compatibility layer for aio_ffmpeg.

DEPRECATION WARNING:
`async_ffmpeg` is deprecated. Use `aio_ffmpeg` instead:
    import aio_ffmpeg
    from aio_ffmpeg import FFmpegClient
"""

import warnings

import aio_ffmpeg as _aio_ffmpeg
from aio_ffmpeg import *  # noqa: F403

warnings.warn(
    "The 'async_ffmpeg' package name is deprecated, use 'aio_ffmpeg' instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = list(_aio_ffmpeg.__all__)
__version__ = _aio_ffmpeg.__version__  # type: ignore[misc]
