"""Асинхронный клиент FFprobe для зондирования и анализа медиафайлов."""

import asyncio
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from async_ffmpeg._compat import get_subprocess_creation_kwargs
from async_ffmpeg._constants import DEFAULT_PROBE_TIMEOUT
from async_ffmpeg._discovery import find_ffprobe
from async_ffmpeg._types import PathLike
from async_ffmpeg.exceptions import FFprobeError, InvalidInputError
from async_ffmpeg.models import (
    AudioStream,
    Chapter,
    MediaFormat,
    MediaInfo,
    StreamDisposition,
    SubtitleStream,
    VideoStream,
    _parse_fraction,
)
from async_ffmpeg.process import ProcessRunner


def _parse_disposition(disp_dict: dict[str, Any] | None) -> StreamDisposition:
    """Парсит секцию disposition из ffprobe JSON."""
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


def _safe_float(val: Any) -> float | None:
    if val is None or val == "" or str(val).upper() == "N/A":
        return None
    try:
        return float(val)
    except ValueError, TypeError:
        return None


def _safe_int(val: Any) -> int | None:
    if val is None or val == "" or str(val).upper() == "N/A":
        return None
    try:
        return int(val)
    except ValueError, TypeError:
        return None


def parse_probe_json(data: str | bytes | dict[str, Any]) -> MediaInfo:
    """Парсит сырой JSON-вывод FFprobe в строгую типизированную модель `MediaInfo`."""
    raw: dict[str, Any]
    if isinstance(data, (str, bytes)):
        try:
            raw = json.loads(data)
        except json.JSONDecodeError as exc:
            snippet = str(data)[:200]
            raise FFprobeError(f"Невалидный JSON от FFprobe: {exc}. Данные: {snippet}") from exc
    else:
        raw = data

    fmt_raw = raw.get("format", {})
    media_format = MediaFormat(
        filename=fmt_raw.get("filename", ""),
        nb_streams=_safe_int(fmt_raw.get("nb_streams")) or 0,
        format_name=fmt_raw.get("format_name", ""),
        format_long_name=fmt_raw.get("format_long_name", ""),
        start_time=_safe_float(fmt_raw.get("start_time")),
        duration=_safe_float(fmt_raw.get("duration")),
        size=_safe_int(fmt_raw.get("size")),
        bit_rate=_safe_int(fmt_raw.get("bit_rate")),
        probe_score=_safe_int(fmt_raw.get("probe_score")),
        tags=fmt_raw.get("tags", {}) if isinstance(fmt_raw.get("tags"), dict) else {},
    )

    streams_raw = raw.get("streams", [])
    video_streams: list[VideoStream] = []
    audio_streams: list[AudioStream] = []
    subtitle_streams: list[SubtitleStream] = []
    all_streams: list[VideoStream | AudioStream | SubtitleStream] = []

    for s in streams_raw:
        codec_type = s.get("codec_type", "").lower()
        idx = _safe_int(s.get("index")) or 0
        c_name = s.get("codec_name", "")
        c_long_name = s.get("codec_long_name", "")
        profile = s.get("profile")
        tag_str = s.get("codec_tag_string")
        tags = s.get("tags", {}) if isinstance(s.get("tags"), dict) else {}
        disposition = _parse_disposition(s.get("disposition"))

        if codec_type == "video":
            r_fr = s.get("r_frame_rate", "0/0")
            avg_fr = s.get("avg_frame_rate", "0/0")
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
                pix_fmt=s.get("pix_fmt", ""),
                frame_rate=fr,
                r_frame_rate=r_fr,
                avg_frame_rate=avg_fr,
                duration=_safe_float(s.get("duration")),
                bit_rate=_safe_int(s.get("bit_rate")),
                nb_frames=_safe_int(s.get("nb_frames")),
                coded_width=_safe_int(s.get("coded_width")),
                coded_height=_safe_int(s.get("coded_height")),
                sample_aspect_ratio=s.get("sample_aspect_ratio"),
                display_aspect_ratio=s.get("display_aspect_ratio"),
                color_space=s.get("color_space"),
                color_range=s.get("color_range"),
                color_primaries=s.get("color_primaries"),
                color_transfer=s.get("color_transfer"),
                field_order=s.get("field_order"),
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
                channel_layout=s.get("channel_layout"),
                sample_fmt=s.get("sample_fmt"),
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

    chapters_raw = raw.get("chapters", [])
    chapters: list[Chapter] = []
    for c in chapters_raw:
        c_tags = c.get("tags", {}) if isinstance(c.get("tags"), dict) else {}
        chapter = Chapter(
            id=_safe_int(c.get("id")) or 0,
            time_base=c.get("time_base", ""),
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
            return parse_probe_json(res.stdout)

        creation_kwargs = get_subprocess_creation_kwargs()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **creation_kwargs,
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
            return parse_probe_json(stdout_data)
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
            return parse_probe_json(proc.stdout)
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
