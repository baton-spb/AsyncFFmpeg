"""Backward compatibility shim for aio_ffmpeg.integration.ytdlp."""

import aio_ffmpeg.integration.ytdlp as _ytdlp
from aio_ffmpeg.integration.ytdlp import *  # noqa: F403

__all__ = [attr for attr in dir(_ytdlp) if not attr.startswith("_")]
