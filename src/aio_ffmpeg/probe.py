"""Асинхронный клиент FFprobe для зондирования и анализа медиафайлов."""

import asyncio
import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from aio_ffmpeg._compat import get_subprocess_creation_kwargs
from aio_ffmpeg._constants import DEFAULT_PROBE_TIMEOUT
from aio_ffmpeg._discovery import find_ffprobe
from aio_ffmpeg._logging import get_logger
from aio_ffmpeg._types import PathLike
from aio_ffmpeg.exceptions import FFprobeError, InvalidInputError
from aio_ffmpeg.models import (
    AudioStream,
    Chapter,
    MediaFormat,
    MediaInfo,
    StreamDisposition,
    SubtitleStream,
    VideoStream,
    _parse_fraction,
)
from aio_ffmpeg.process import ProcessRunner

logger = get_logger("probe")


def _parse_disposition(disp_dict: Mapping[str, object] | None) -> StreamDisposition:
    """Парсит секцию disposition из ffprobe JSON.

    Args:
        disp_dict: Словарь disposition из JSON ffprobe.

    Returns:
        Сконструированный объект StreamDisposition.
    """
    if not disp_dict:
        return StreamDisposition()
    return StreamDisposition(
        default=bool(disp_dict.get("default", 0)),
        dub=bool(disp_dict.get("dub", 0)),
        original=bool(disp_dict.get("original", 0)),
        comment=bool(disp_dict.get("comment", 0)),
        lyrics=bool(disp_dict.get("lyrics", 0)),
        karaoke=bool(disp_dict.get("karaoke", 0)),
        forced=bool(disp_dict.get("forced", 0)),
        hearing_impaired=bool(disp_dict.get("hearing_impaired", 0)),
        visual_impaired=bool(disp_dict.get("visual_impaired", 0)),
        clean_effects=bool(disp_dict.get("clean_effects", 0)),
        attached_pic=bool(disp_dict.get("attached_pic", 0)),
        timed_thumbnails=bool(disp_dict.get("timed_thumbnails", 0)),
        captions=bool(disp_dict.get("captions", 0)),
        descriptions=bool(disp_dict.get("descriptions", 0)),
        metadata=bool(disp_dict.get("metadata", 0)),
        dependent=bool(disp_dict.get("dependent", 0)),
        still_image=bool(disp_dict.get("still_image", 0)),
    )


def _safe_float(val: object) -> float | None:
    """Безопасно преобразует значение в вещественное число float.

    Args:
        val: Исходное значение из JSON FFprobe.

    Returns:
        Число float или None при невозможности преобразования.
    """
    if val is None or val == "" or str(val).upper() == "N/A":
        return None
    try:
        return float(str(val))
    except ValueError, TypeError:
        return None


def _safe_int(val: object) -> int | None:
    """Безопасно преобразует значение в целое число int.

    Args:
        val: Исходное значение из JSON FFprobe.

    Returns:
        Число int или None при невозможности преобразования.
    """
    if val is None or val == "" or str(val).upper() == "N/A":
        return None
    try:
        return int(float(str(val)))
    except ValueError, TypeError:
        return None


def parse_probe_json(data: str | bytes | Mapping[str, object]) -> MediaInfo:
    """Парсит сырой JSON-вывод FFprobe в строгую типизированную модель `MediaInfo`.

    Args:
        data: Строка, байты JSON или словарь метаданных FFprobe.

    Returns:
        Типизированная структура метаданных MediaInfo.

    Raises:
        FFprobeError: Если передан невалидный JSON.
    """
    raw: dict[str, object]
    if isinstance(data, (str, bytes)):
        try:
            parsed = json.loads(data)
            if not isinstance(parsed, dict):
                raise FFprobeError(f"Ожидался JSON-объект, получено: {type(parsed).__name__}")
            raw = parsed
        except json.JSONDecodeError as exc:
            snippet = str(data)[:200]
            raise FFprobeError(f"Невалидный JSON от FFprobe: {exc}. Данные: {snippet}") from exc
    else:
        raw = dict(data)

    fmt_dict = raw.get("format")
    fmt_raw: Mapping[str, object] = fmt_dict if isinstance(fmt_dict, Mapping) else {}
    fmt_tags_dict = fmt_raw.get("tags")
    fmt_tags: dict[str, str] = (
        {str(k): str(v) for k, v in fmt_tags_dict.items()}
        if isinstance(fmt_tags_dict, Mapping)
        else {}
    )

    media_format = MediaFormat(
        filename=str(fmt_raw.get("filename", "")),
        nb_streams=_safe_int(fmt_raw.get("nb_streams")) or 0,
        format_name=str(fmt_raw.get("format_name", "")),
        format_long_name=str(fmt_raw.get("format_long_name", "")),
        start_time=_safe_float(fmt_raw.get("start_time")),
        duration=_safe_float(fmt_raw.get("duration")),
        size=_safe_int(fmt_raw.get("size")),
        bit_rate=_safe_int(fmt_raw.get("bit_rate")),
        probe_score=_safe_int(fmt_raw.get("probe_score")),
        tags=fmt_tags,
    )

    streams_val = raw.get("streams")
    streams_raw: list[Mapping[str, object]] = (
        [s for s in streams_val if isinstance(s, Mapping)] if isinstance(streams_val, list) else []
    )
    video_streams: list[VideoStream] = []
    audio_streams: list[AudioStream] = []
    subtitle_streams: list[SubtitleStream] = []
    all_streams: list[VideoStream | AudioStream | SubtitleStream] = []

    for s in streams_raw:
        codec_type = str(s.get("codec_type", "")).lower()
        idx = _safe_int(s.get("index")) or 0
        c_name = str(s.get("codec_name", ""))
        c_long_name = str(s.get("codec_long_name", ""))
        profile = str(s["profile"]) if "profile" in s and s["profile"] is not None else None
        tag_str = (
            str(s["codec_tag_string"])
            if "codec_tag_string" in s and s["codec_tag_string"] is not None
            else None
        )
        s_tags_raw = s.get("tags")
        tags: dict[str, str] = (
            {str(k): str(v) for k, v in s_tags_raw.items()}
            if isinstance(s_tags_raw, Mapping)
            else {}
        )
        disp_raw = s.get("disposition")
        disposition = _parse_disposition(disp_raw if isinstance(disp_raw, Mapping) else None)

        if codec_type == "video":
            r_fr = str(s.get("r_frame_rate", "0/0"))
            avg_fr = str(s.get("avg_frame_rate", "0/0"))
            fr = _parse_fraction(avg_fr) or _parse_fraction(r_fr)

            v_stream = VideoStream(
                index=idx,
                codec_name=c_name,
                codec_long_name=c_long_name,
                codec_type="video",
                profile=profile,
                codec_tag_string=tag_str,
                tags=tags,
                disposition=disposition,
                width=_safe_int(s.get("width")) or 0,
                height=_safe_int(s.get("height")) or 0,
                pix_fmt=str(s.get("pix_fmt", "")),
                frame_rate=fr,
                r_frame_rate=r_fr,
                avg_frame_rate=avg_fr,
                duration=_safe_float(s.get("duration")),
                bit_rate=_safe_int(s.get("bit_rate")),
                nb_frames=_safe_int(s.get("nb_frames")),
                coded_width=_safe_int(s.get("coded_width")),
                coded_height=_safe_int(s.get("coded_height")),
                sample_aspect_ratio=(
                    str(s["sample_aspect_ratio"])
                    if "sample_aspect_ratio" in s and s["sample_aspect_ratio"] is not None
                    else None
                ),
                display_aspect_ratio=(
                    str(s["display_aspect_ratio"])
                    if "display_aspect_ratio" in s and s["display_aspect_ratio"] is not None
                    else None
                ),
                color_space=(
                    str(s["color_space"])
                    if "color_space" in s and s["color_space"] is not None
                    else None
                ),
                color_range=(
                    str(s["color_range"])
                    if "color_range" in s and s["color_range"] is not None
                    else None
                ),
                color_primaries=(
                    str(s["color_primaries"])
                    if "color_primaries" in s and s["color_primaries"] is not None
                    else None
                ),
                color_transfer=(
                    str(s["color_transfer"])
                    if "color_transfer" in s and s["color_transfer"] is not None
                    else None
                ),
                field_order=(
                    str(s["field_order"])
                    if "field_order" in s and s["field_order"] is not None
                    else None
                ),
                is_avc=str(s.get("is_avc", "")).lower() == "true",
            )
            video_streams.append(v_stream)
            all_streams.append(v_stream)

        elif codec_type == "audio":
            a_stream = AudioStream(
                index=idx,
                codec_name=c_name,
                codec_long_name=c_long_name,
                codec_type="audio",
                profile=profile,
                codec_tag_string=tag_str,
                tags=tags,
                disposition=disposition,
                sample_rate=_safe_int(s.get("sample_rate")) or 0,
                channels=_safe_int(s.get("channels")) or 0,
                channel_layout=(
                    str(s["channel_layout"])
                    if "channel_layout" in s and s["channel_layout"] is not None
                    else None
                ),
                sample_fmt=(
                    str(s["sample_fmt"])
                    if "sample_fmt" in s and s["sample_fmt"] is not None
                    else None
                ),
                duration=_safe_float(s.get("duration")),
                bit_rate=_safe_int(s.get("bit_rate")),
                nb_frames=_safe_int(s.get("nb_frames")),
                bits_per_sample=_safe_int(s.get("bits_per_sample")),
            )
            audio_streams.append(a_stream)
            all_streams.append(a_stream)

        elif codec_type == "subtitle":
            sub_stream = SubtitleStream(
                index=idx,
                codec_name=c_name,
                codec_long_name=c_long_name,
                codec_type="subtitle",
                profile=profile,
                codec_tag_string=tag_str,
                tags=tags,
                disposition=disposition,
                language=tags.get("language"),
                duration=_safe_float(s.get("duration")),
                nb_frames=_safe_int(s.get("nb_frames")),
            )
            subtitle_streams.append(sub_stream)
            all_streams.append(sub_stream)

    chapters_val = raw.get("chapters")
    chapters_raw: list[Mapping[str, object]] = (
        [c for c in chapters_val if isinstance(c, Mapping)]
        if isinstance(chapters_val, list)
        else []
    )
    chapters: list[Chapter] = []
    for c in chapters_raw:
        c_tags_raw = c.get("tags")
        c_tags: dict[str, str] = (
            {str(k): str(v) for k, v in c_tags_raw.items()}
            if isinstance(c_tags_raw, Mapping)
            else {}
        )
        chapter = Chapter(
            id=_safe_int(c.get("id")) or 0,
            time_base=str(c.get("time_base", "")),
            start=_safe_int(c.get("start")) or 0,
            start_time=_safe_float(c.get("start_time")) or 0.0,
            end=_safe_int(c.get("end")) or 0,
            end_time=_safe_float(c.get("end_time")) or 0.0,
            tags=c_tags,
        )
        chapters.append(chapter)

    return MediaInfo(
        format=media_format,
        streams=tuple(all_streams),
        video_streams=tuple(video_streams),
        audio_streams=tuple(audio_streams),
        subtitle_streams=tuple(subtitle_streams),
        chapters=tuple(chapters),
        raw_data=raw,
    )


class FFprobe:
    """Асинхронный клиент для зондирования медиафайлов с помощью `ffprobe`."""

    def __init__(
        self,
        ffprobe_path: PathLike | None = None,
        *,
        default_timeout: float = DEFAULT_PROBE_TIMEOUT,
        process_runner: ProcessRunner | None = None,
    ) -> None:
        """Инициализирует анализатор медиафайлов FFprobe.

        Args:
            ffprobe_path: Пользовательский путь к бинарнику ffprobe.
            default_timeout: Таймаут анализа по умолчанию в секундах.
            process_runner: Опциональный ProcessRunner для переиспользования пула процессов.
        """
        self._custom_path = ffprobe_path
        self._default_timeout = default_timeout
        self._process_runner = process_runner

    @property
    def binary_path(self) -> Path:
        """Абсолютный путь к найденному исполняемому файлу ffprobe."""
        return find_ffprobe(custom_path=self._custom_path)

    def _build_command(
        self,
        target: str,
        *,
        show_chapters: bool = True,
        extra_args: Sequence[str] | None = None,
    ) -> list[str]:
        """Формирует список аргументов командной строки ffprobe для JSON-анализа.

        Args:
            target: Путь к медиафайлу или сетевой URL.
            show_chapters: Включать ли информацию о главах (-show_chapters).
            extra_args: Дополнительные аргументы командной строки.

        Returns:
            Список строковых аргументов для запуска процесса ffprobe.
        """
        cmd = [
            str(self.binary_path),
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
        ]
        if show_chapters:
            cmd.append("-show_chapters")
        if extra_args:
            cmd.extend(extra_args)
        cmd.append(target)
        return cmd

    async def probe(
        self,
        path: PathLike,
        *,
        timeout: float | None = None,
        show_chapters: bool = True,
        extra_args: Sequence[str] | None = None,
    ) -> MediaInfo:
        """Асинхронно анализирует медиафайл или сетевой URL и возвращает `MediaInfo`.

        Raises:
            InvalidInputError: если локальный файл не существует.
            FFprobeError: при ошибках выполнения ffprobe или повреждённом JSON.
        """
        str_target = str(path)
        # Если это локальный путь (не URL типа http://, rtsp:// и т.д.), проверяем существование
        if "://" not in str_target and not Path(str_target).exists():
            raise InvalidInputError(str_target, "Файл не существует на диске")

        logger.debug("Зондирование медиафайла FFprobe: %s", str_target)
        cmd = self._build_command(str_target, show_chapters=show_chapters, extra_args=extra_args)
        effective_timeout = timeout if timeout is not None else self._default_timeout

        if self._process_runner is not None:
            res = await self._process_runner.run(
                cmd,
                timeout=effective_timeout,
                check=False,
            )
            if not res.success or not res.stdout:
                raise FFprobeError(
                    message=f"ffprobe завершился с кодом {res.exit_code}",
                    command=cmd,
                    stderr=res.stderr_text,
                )
            info = parse_probe_json(res.stdout)
            logger.info(
                "Успешно получены метаданные FFprobe для '%s' (формат: %s, длительность: %s с)",
                str_target,
                info.format.format_name,
                f"{info.duration:.2f}" if info.duration is not None else "N/A",
            )
            return info

        creation_kwargs = get_subprocess_creation_kwargs()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **creation_kwargs,  # type: ignore[arg-type]
            )
            stdout_data, stderr_data = await asyncio.wait_for(
                proc.communicate(), timeout=effective_timeout
            )
            if proc.returncode != 0 or not stdout_data:
                err_text = stderr_data.decode(errors="replace") if stderr_data else ""
                raise FFprobeError(
                    message=f"ffprobe завершился с ошибкой (exit code {proc.returncode})",
                    command=cmd,
                    stderr=err_text,
                )
            info = parse_probe_json(stdout_data)
            logger.info(
                "Успешно получены метаданные FFprobe для '%s' (формат: %s, длительность: %s с)",
                str_target,
                info.format.format_name,
                f"{info.duration:.2f}" if info.duration is not None else "N/A",
            )
            return info
        except (TimeoutError, OSError) as exc:
            raise FFprobeError(
                message=f"Ошибка вызова ffprobe: {exc}",
                command=cmd,
            ) from exc

    def probe_sync(
        self,
        path: PathLike,
        *,
        timeout: float | None = None,
        show_chapters: bool = True,
        extra_args: Sequence[str] | None = None,
    ) -> MediaInfo:
        """Синхронная версия `probe()`."""
        str_target = str(path)
        if "://" not in str_target and not Path(str_target).exists():
            raise InvalidInputError(str_target, "Файл не существует на диске")

        logger.debug("Синхронное зондирование медиафайла FFprobe: %s", str_target)
        cmd = self._build_command(str_target, show_chapters=show_chapters, extra_args=extra_args)
        effective_timeout = timeout if timeout is not None else self._default_timeout

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                check=False,
                timeout=effective_timeout,
            )
            if proc.returncode != 0 or not proc.stdout:
                raise FFprobeError(
                    message=f"ffprobe завершился с ошибкой {proc.returncode}",
                    command=cmd,
                    stderr=proc.stderr.decode(errors="replace"),
                )
            info = parse_probe_json(proc.stdout)
            logger.info(
                "Успешно получены метаданные FFprobe (sync) для '%s' (формат: %s, длительность: %s с)",
                str_target,
                info.format.format_name,
                f"{info.duration:.2f}" if info.duration is not None else "N/A",
            )
            return info
        except (subprocess.SubprocessError, OSError) as exc:
            raise FFprobeError(
                message=f"Ошибка синхронного вызова ffprobe: {exc}",
                command=cmd,
            ) from exc

    async def get_duration(self, path: PathLike, *, timeout: float | None = None) -> float | None:
        """Возвращает общую длительность медиафайла в секундах."""
        info = await self.probe(path, timeout=timeout, show_chapters=False)
        return info.duration

    async def get_resolution(
        self, path: PathLike, *, timeout: float | None = None
    ) -> tuple[int, int] | None:
        """Возвращает разрешение (ширина, высота) основного видеопотока."""
        info = await self.probe(path, timeout=timeout, show_chapters=False)
        return info.resolution

    async def get_codecs(self, path: PathLike, *, timeout: float | None = None) -> dict[str, str]:
        """Возвращает словарь названий кодеков для видео и аудио потоков."""
        info = await self.probe(path, timeout=timeout, show_chapters=False)
        codecs: dict[str, str] = {}
        if info.primary_video:
            codecs["video"] = info.primary_video.codec_name
        if info.primary_audio:
            codecs["audio"] = info.primary_audio.codec_name
        return codecs

    async def has_video(self, path: PathLike, *, timeout: float | None = None) -> bool:
        """Проверяет наличие видеопотока."""
        info = await self.probe(path, timeout=timeout, show_chapters=False)
        return info.has_video

    async def has_audio(self, path: PathLike, *, timeout: float | None = None) -> bool:
        """Проверяет наличие аудиопотока."""
        info = await self.probe(path, timeout=timeout, show_chapters=False)
        return info.has_audio
