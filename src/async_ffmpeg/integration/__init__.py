"""Модули интеграции async-ffmpeg со сторонними экосистемами (async-yt-dlp)."""

from async_ffmpeg.integration.ytdlp import (
    DownloadPostProcessor,
    PostProcessAction,
    PostProcessResult,
    extract_download_audio,
    process_download_result,
    transcode_download,
)

__all__ = [
    "DownloadPostProcessor",
    "PostProcessAction",
    "PostProcessResult",
    "extract_download_audio",
    "process_download_result",
    "transcode_download",
]
