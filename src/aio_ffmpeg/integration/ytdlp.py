"""Модуль интеграции async-ffmpeg с библиотеками загрузки медиа (async-yt-dlp).

Опирается исключительно на DownloadResultProtocol и не создает жестких зависимостей
от конкретных сторонних пакетов во время выполнения.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from aio_ffmpeg._constants import DEFAULT_AUDIO_BITRATE, DEFAULT_VIDEO_CRF
from aio_ffmpeg._types import DownloadResultProtocol, PathLike, ProgressCallback
from aio_ffmpeg.client import FFmpegClient
from aio_ffmpeg.models import MediaInfo
from aio_ffmpeg.process import ProcessResult

type PostProcessAction = Literal["transcode", "extract_audio", "convert"]


@dataclass(frozen=True, slots=True)
class PostProcessResult:
    """Результат постобработки загруженного медиафайла."""

    source: Path
    output: Path
    title: str | None
    duration_seconds: float
    result: ProcessResult
    media_info: MediaInfo | None = None


def _resolve_source_path_and_metadata(
    download: DownloadResultProtocol | PathLike,
) -> tuple[Path, str | None, float | None]:
    """Извлекает путь к файлу и метаданные из объекта результата загрузки или пути."""
    if isinstance(download, DownloadResultProtocol):
        return download.filepath, download.title, download.duration
    p = Path(download)
    return p, p.stem, None


async def process_download_result(
    download: DownloadResultProtocol | PathLike,
    output: PathLike | None = None,
    *,
    action: PostProcessAction = "transcode",
    video_codec: str = "libx264",
    audio_codec: str = "aac",
    audio_bitrate: str = DEFAULT_AUDIO_BITRATE,
    crf: int = DEFAULT_VIDEO_CRF,
    resolution: tuple[int, int] | None = None,
    client: FFmpegClient | None = None,
    probe_output: bool = True,
    on_progress: ProgressCallback | None = None,
) -> PostProcessResult:
    """Выполняет постобработку результата скачивания (транскодирование, извлечение аудио, смена контейнера).

    Args:
        download: Объект DownloadResultProtocol (из async-yt-dlp) или путь к файлу.
        output: Целевой выходной файл (если не указан, формируется автоматически рядом).
        action: Тип операции ('transcode', 'extract_audio', 'convert').
        video_codec: Видеокодек для transcode.
        audio_codec: Аудиокодек для transcode / extract_audio.
        audio_bitrate: Битрейт аудио.
        crf: Фактор качества для видео.
        resolution: Желаемое разрешение (ширина, высота).
        client: Экземпляр FFmpegClient (если None, создается временный).
        probe_output: Анализировать ли итоговый файл через FFprobe.
        on_progress: Функция обратного вызова для отслеживания прогресса.
    """
    source_path, title, _duration = _resolve_source_path_and_metadata(download)
    cli = client if client is not None else FFmpegClient()

    if output is None:
        parent = source_path.parent
        stem = source_path.stem
        if action == "extract_audio":
            ext = "mp3" if "mp3" in audio_codec else "m4a"
            target_out = parent / f"{stem}.{ext}"
        elif action == "convert":
            target_out = parent / f"{stem}_converted.mp4"
        else:
            suffix = f"_{resolution[1]}p" if resolution else "_processed"
            target_out = parent / f"{stem}{suffix}.mp4"
    else:
        target_out = Path(output)

    if action == "extract_audio":
        proc_res = await cli.extract_audio(
            input=source_path,
            output=target_out,
            codec=audio_codec,
            bitrate=audio_bitrate,
            on_progress=on_progress,
        )
    elif action == "convert":
        proc_res = await cli.convert(
            input=source_path,
            output=target_out,
            copy=True,
            on_progress=on_progress,
        )
    else:
        # transcode
        metadata = {"title": title} if title else None
        proc_res = await cli.transcode(
            input=source_path,
            output=target_out,
            video_codec=video_codec,
            crf=crf,
            resolution=resolution,
            audio_codec=audio_codec,
            audio_bitrate=audio_bitrate,
            metadata=metadata,
            on_progress=on_progress,
        )

    media_info: MediaInfo | None = None
    if probe_output and proc_res.success and target_out.exists():
        media_info = await cli.probe(target_out)

    return PostProcessResult(
        source=source_path,
        output=target_out,
        title=title,
        duration_seconds=proc_res.duration_seconds,
        result=proc_res,
        media_info=media_info,
    )


async def transcode_download(
    download: DownloadResultProtocol | PathLike,
    output: PathLike | None = None,
    *,
    resolution: tuple[int, int] | None = None,
    video_codec: str = "libx264",
    audio_codec: str = "aac",
    client: FFmpegClient | None = None,
    on_progress: ProgressCallback | None = None,
) -> PostProcessResult:
    """Удобная функция-хелпер для транскодирования скачанного видео."""
    return await process_download_result(
        download=download,
        output=output,
        action="transcode",
        resolution=resolution,
        video_codec=video_codec,
        audio_codec=audio_codec,
        client=client,
        on_progress=on_progress,
    )


async def extract_download_audio(
    download: DownloadResultProtocol | PathLike,
    output: PathLike | None = None,
    *,
    codec: str = "aac",
    bitrate: str = DEFAULT_AUDIO_BITRATE,
    client: FFmpegClient | None = None,
    on_progress: ProgressCallback | None = None,
) -> PostProcessResult:
    """Удобная функция-хелпер для извлечения звуковой дорожки из скачанного медиа."""
    return await process_download_result(
        download=download,
        output=output,
        action="extract_audio",
        audio_codec=codec,
        audio_bitrate=bitrate,
        client=client,
        on_progress=on_progress,
    )


class DownloadPostProcessor:
    """Класс-обработчик (callable hook), пригодный для передачи в пайплайны async-yt-dlp."""

    def __init__(
        self,
        action: PostProcessAction = "transcode",
        *,
        client: FFmpegClient | None = None,
        **options: object,
    ) -> None:
        """Инициализирует постобработчик результатов загрузки.

        Args:
            action: Действие обработки ('transcode', 'extract_audio', 'convert').
            client: Экземпляр FFmpegClient для исполнения команд.
            **options: Дополнительные параметры постобработки.
        """
        self._action = action
        self._client = client
        self._options: dict[str, object] = options

    async def __call__(self, download: DownloadResultProtocol | PathLike) -> PostProcessResult:
        """Выполняет постобработку при вызове экземпляра."""
        return await process_download_result(
            download=download,
            action=self._action,
            client=self._client,
            **self._options,  # type: ignore[arg-type]
        )
