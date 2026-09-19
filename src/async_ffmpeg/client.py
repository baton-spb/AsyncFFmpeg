"""Backward compatibility shim for aio_ffmpeg.client."""

import aio_ffmpeg.client as _client
from aio_ffmpeg.client import *  # noqa: F403

__all__ = [attr for attr in dir(_client) if not attr.startswith("_")]
