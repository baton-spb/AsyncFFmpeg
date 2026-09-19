"""Backward compatibility shim for aio_ffmpeg.integration."""

import aio_ffmpeg.integration as _integration
from aio_ffmpeg.integration import *  # noqa: F403

__all__ = [attr for attr in dir(_integration) if not attr.startswith("_")]
