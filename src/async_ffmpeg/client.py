"""Высокоуровневый фасадный клиент FFmpegClient для повседневных задач обработки медиа.

Предоставляет удобный асинхронный API для:
- Анализа медиаданных (probe)
- Транскодирования видео/аудио (transcode) с автоматическим процентом прогресса
- Извлечения звуковых дорожек (extract_audio)
- Быстрой и покадровой обрезки (trim)
- Объединения видеофайлов (concat) через demuxer или filter
- Создания скриншотов (screenshot) и серий превью (thumbnails)
- Быстрой смены контейнера без перекодирования (convert)
- Нормализации громкости звука по стандартам EBU R128 (normalize_audio)
- Изменения разрешения (scale)
- Контроля параллелизма через ProcessRunner и семафоры
- Асинхронного контекстного менеджера (async with FFmpegClient())
"""

import re
import tempfile
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from async_ffmpeg.pipeline import MediaPipeline

from async_ffmpeg._compat import get_null_device, normalize_path_for_ffmpeg
from async_ffmpeg._constants import (
    DEFAULT_AUDIO_BITRATE,
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_VIDEO_CRF,
    DEFAULT_VIDEO_PRESET,
)
from async_ffmpeg._discovery import find_ffmpeg
from async_ffmpeg._logging import get_logger
from async_ffmpeg._types import (
    AudioCodec,
    AudioFormat,
    CommandOptionValue,
    ConcatMethod,
    PathLike,
    ProgressCallback,
    StderrCallback,
    VideoCodec,
    VideoPreset,
)
from async_ffmpeg.command import FFmpegCommand
from async_ffmpeg.exceptions import InvalidInputError
from async_ffmpeg.filters import Filter, FilterChain, FilterGraph, loudnorm, scale
from async_ffmpeg.hardware import HardwareAccel
from async_ffmpeg.models import MediaInfo, SilenceInterval
from async_ffmpeg.probe import FFprobe
from async_ffmpeg.process import ProcessResult, ProcessRunner

_RE_SILENCE_START = re.compile(r"silence_start:\s*(-?[\d\.]+)")
_RE_SILENCE_END = re.compile(r"silence_end:\s*(-?[\d\.]+)\s*\|\s*silence_duration:\s*(-?[\d\.]+)")

logger = get_logger("client")


class FFmpegClient:
    """Высокоуровневый асинхронный клиент для работы с FFmpeg и FFprobe.

    Интегрирует поиск бинарников, ограничение конкурентных задач, парсинг прогресса,
    автоопределение длительности и аппаратное ускорение в единый дружелюбный интерфейс.
    """

    def __init__(
        self,
        ffmpeg_path: PathLike | None = None,
        ffprobe_path: PathLike | None = None,
        *,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        default_timeout: float | None = None,
        temp_dir: PathLike | None = None,
    ) -> None:
        """Инициализирует высокоуровневый клиент FFmpegClient.

        Args:
            ffmpeg_path: Пользовательский путь к бинарнику ffmpeg.
            ffprobe_path: Пользовательский путь к бинарнику ffprobe.
            max_concurrent: Максимальное число параллельных процессов.
            default_timeout: Таймаут по умолчанию для длительных операций в секундах.
            temp_dir: Пользовательская директория для временных файлов.
        """
        self._ffmpeg_path = ffmpeg_path
        self._ffprobe_path = ffprobe_path
        self._default_timeout = default_timeout
        self._temp_dir = Path(temp_dir) if temp_dir else Path(tempfile.gettempdir())

        self._runner = ProcessRunner(
            max_concurrent=max_concurrent,
            default_timeout=default_timeout,
        )
        self._ffprobe = FFprobe(
            ffprobe_path=ffprobe_path,
            process_runner=self._runner,
            default_timeout=default_timeout or 30.0,
        )
        self._hardware = HardwareAccel(
            ffmpeg_path=ffmpeg_path,
            runner=self._runner,
        )
        self._created_temp_files: list[Path] = []

    @property
    def runner(self) -> ProcessRunner:
        """Низкоуровневый исполнитель процессов."""
        return self._runner

    @property
    def ffprobe(self) -> FFprobe:
        """Инструмент для анализа медиафайлов FFprobe."""
        return self._ffprobe

    @property
    def hardware(self) -> HardwareAccel:
        """Менеджер аппаратного ускорения."""
        return self._hardware

    @property
    def active_processes(self) -> int:
        """Количество активных параллельных процессов в данный момент."""
        return self._runner.active_count

    @property
    def ffmpeg_path(self) -> PathLike | None:
        """Пользовательский путь к бинарнику ffmpeg или None (автопоиск)."""
        return self._ffmpeg_path

    @property
    def ffprobe_path(self) -> PathLike | None:
        """Пользовательский путь к бинарнику ffprobe или None (автопоиск)."""
        return self._ffprobe_path

    @property
    def default_timeout(self) -> float | None:
        """Таймаут по умолчанию для длительных операций."""
        return self._default_timeout

    def pipeline(self, input: PathLike | None = None) -> MediaPipeline:  # noqa: A002
        """Создает конвейер обработки (MediaPipeline), использующий настройки данного клиента."""
        from async_ffmpeg.pipeline import MediaPipeline

        return MediaPipeline(
            input=input,
            client=self,
            ffmpeg_path=self._ffmpeg_path,
            ffprobe_path=self._ffprobe_path,
        )

    async def __aenter__(self) -> Self:
        """Вход в асинхронный контекстный менеджер клиента."""
        await self._runner.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Выход из контекстного менеджера с очисткой временных файлов и отменой незавершенных задач."""
        try:
            # Очищаем временные файлы списка конкатенации
            for tmp in self._created_temp_files:
                if tmp.exists():
                    with suppress(OSError):
                        tmp.unlink()
            self._created_temp_files.clear()
        finally:
            await self._runner.__aexit__(exc_type, exc_val, exc_tb)

    def create_command(self) -> FFmpegCommand:
        """Создает новый экземпляр FFmpegCommand с привязкой путей и ProcessRunner клиента."""
        return FFmpegCommand()

    async def probe(self, path: PathLike, *, timeout: float | None = None) -> MediaInfo:
        """Анализирует медиафайл и возвращает детальную структурированную информацию MediaInfo."""
        return await self._ffprobe.probe(path, timeout=timeout)

    async def _resolve_duration_if_needed(
        self,
        input_target: PathLike,
        explicit_duration: float | None = None,
    ) -> float | None:
        """Определяет общую длительность медиафайла для расчета процентов прогресса."""
        if explicit_duration is not None and explicit_duration > 0:
            return explicit_duration
        try:
            info = await self.probe(input_target)
            return info.duration
        except Exception as exc:
            logger.debug(
                "Не удалось определить длительность для '%s' через probe: %s", input_target, exc
            )
            return None

    # =========================================================================
    # Основные операции
    # =========================================================================

    async def transcode(
        self,
        input: PathLike,  # noqa: A002
        output: PathLike,
        *,
        video_codec: VideoCodec | str | None = None,
        audio_codec: AudioCodec | str | None = None,
        video_bitrate: str | None = None,
        audio_bitrate: str | None = None,
        resolution: tuple[int, int] | None = None,
        fps: float | int | None = None,
        preset: VideoPreset | str | None = DEFAULT_VIDEO_PRESET,
        crf: int | None = DEFAULT_VIDEO_CRF,
        pixel_format: str | None = "yuv420p",
        video_filters: str | FilterGraph | FilterChain | Filter | None = None,
        audio_filters: str | FilterGraph | FilterChain | Filter | None = None,
        metadata: dict[str, str] | None = None,
        start: float | str | None = None,
        duration: float | str | None = None,
        hwaccel: str | None = None,
        copy_video: bool = False,
        copy_audio: bool = False,
        extra_args: Sequence[str] | None = None,
        total_duration: float | None = None,
        timeout: float | None = None,
        on_progress: ProgressCallback | None = None,
        on_stderr: StderrCallback | None = None,
    ) -> ProcessResult:
        """Универсальное транскодирование видео- и аудиопотоков.

        Если передан `on_progress`, клиент автоматически определяет общую длительность файла
        для отображения процентов выполнения (0.0% – 100.0%) и времени ETA.
        """
        if crf is not None and not (0 <= crf <= 51):
            raise ValueError(f"Параметр crf должен быть в диапазоне от 0 до 51, получено: {crf}")
        if fps is not None and fps <= 0:
            raise ValueError(f"Параметр fps должен быть > 0, получено: {fps}")
        if resolution is not None:
            w, h = resolution
            if w <= 0 or h <= 0:
                raise ValueError(
                    f"Размеры кадра должны быть строго положительными, получено: {w}x{h}"
                )
        if isinstance(start, (int, float)) and start < 0:
            raise ValueError(f"Параметр start должен быть >= 0 секунд, получено: {start}")
        if isinstance(duration, (int, float)) and duration <= 0:
            raise ValueError(f"Параметр duration должен быть > 0 секунд, получено: {duration}")
        calc_duration = total_duration
        if on_progress and calc_duration is None:
            if isinstance(duration, (int, float)):
                calc_duration = float(duration)
            else:
                calc_duration = await self._resolve_duration_if_needed(input)

        cmd = self.create_command().overwrite()

        # Входные опции
        input_opts: dict[str, CommandOptionValue] = {}
        if start is not None:
            input_opts["ss"] = start
        if duration is not None:
            input_opts["t"] = duration
        if hwaccel is not None:
            cmd.hwaccel(hwaccel)

        cmd.input(input, **input_opts)

        # Видео параметры
        if copy_video:
            cmd.copy_video()
        elif video_codec is not None:
            cmd.video_codec(video_codec)
        else:
            cmd.video_codec("libx264")

        if not copy_video:
            if preset is not None:
                cmd.preset(preset)
            if crf is not None:
                cmd.crf(crf)
            if video_bitrate is not None:
                cmd.video_bitrate(video_bitrate)
            if pixel_format is not None:
                cmd.pixel_format(pixel_format)

        # Аудио параметры
        if copy_audio:
            cmd.copy_audio()
        elif audio_codec is not None:
            cmd.audio_codec(audio_codec)
        else:
            cmd.audio_codec("aac")

        if not copy_audio and audio_bitrate is not None:
            cmd.audio_bitrate(audio_bitrate)

        # Фильтры
        if resolution is not None or fps is not None:
            vf_chain = FilterChain()
            if resolution is not None:
                vf_chain.add(scale(resolution[0], resolution[1]))
            if fps is not None:
                vf_chain.add(Filter("fps", fps))
            if video_filters is not None:
                if isinstance(video_filters, Filter):
                    vf_chain.add(video_filters)
                elif isinstance(video_filters, FilterChain):
                    for f in video_filters.filters:
                        vf_chain.add(f)
                elif isinstance(video_filters, FilterGraph):
                    for ch in video_filters.chains:
                        for f in ch.filters:
                            vf_chain.add(f)
                else:
                    vf_chain.add(str(video_filters))
            cmd.video_filter(vf_chain)
        elif video_filters is not None:
            cmd.video_filter(video_filters)

        if audio_filters is not None:
            cmd.audio_filter(audio_filters)

        # Метаданные
        if metadata:
            for k, v in metadata.items():
                cmd.metadata(k, v)

        if extra_args:
            cmd.extra_args(*extra_args)

        cmd.output(output)

        return await cmd.execute(
            ffmpeg_path=self._ffmpeg_path or find_ffmpeg(),
            process_runner=self._runner,
            total_duration=calc_duration,
            timeout=timeout or self._default_timeout,
            on_progress=on_progress,
            on_stderr=on_stderr,
        )

    async def extract_audio(
        self,
        input: PathLike,  # noqa: A002
        output: PathLike,
        *,
        codec: AudioCodec | AudioFormat | str = "aac",
        bitrate: str = DEFAULT_AUDIO_BITRATE,
        sample_rate: int | None = None,
        channels: int | None = None,
        timeout: float | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> ProcessResult:
        """Извлекает звуковую дорожку из видеофайла или перекодирует аудио."""
        total_duration = None
        if on_progress:
            total_duration = await self._resolve_duration_if_needed(input)

        cmd = (
            self.create_command()
            .overwrite()
            .input(input)
            .no_video()
            .audio_codec(codec)
            .audio_bitrate(bitrate)
        )

        if sample_rate is not None:
            cmd.output_option("ar", sample_rate)
        if channels is not None:
            cmd.output_option("ac", channels)

        cmd.output(output)

        return await cmd.execute(
            ffmpeg_path=self._ffmpeg_path or find_ffmpeg(),
            process_runner=self._runner,
            total_duration=total_duration,
            timeout=timeout or self._default_timeout,
            on_progress=on_progress,
        )

    async def trim(
        self,
        input: PathLike,  # noqa: A002
        output: PathLike,
        *,
        start: float | str | None = None,
        end: float | str | None = None,
        duration: float | str | None = None,
        copy: bool = True,
        timeout: float | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> ProcessResult:
        """Обрезает медиафайл по временным интервалам.

        Если `copy=True`, выполняется мгновенная обрезка через stream copy без перекодирования.
        """
        if isinstance(start, (int, float)) and start < 0:
            raise ValueError(f"Параметр start должен быть >= 0 секунд, получено: {start}")
        if isinstance(duration, (int, float)) and duration <= 0:
            raise ValueError(f"Параметр duration должен быть > 0 секунд, получено: {duration}")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end <= start:
            raise ValueError(
                f"Конечная метка end ({end}) должна быть больше начальной start ({start})"
            )
        input_opts: dict[str, CommandOptionValue] = {}
        if start is not None:
            input_opts["ss"] = start

        output_opts: dict[str, CommandOptionValue] = {}
        if end is not None:
            output_opts["to"] = end
        elif duration is not None:
            output_opts["t"] = duration

        cmd = self.create_command().overwrite().input(input, **input_opts)

        if copy:
            cmd.copy_all()
        else:
            cmd.video_codec("libx264").audio_codec("aac")

        cmd.output(output, **output_opts)

        # Вычисляем длительность фрагмента для прогресса
        calc_duration: float | None = None
        if isinstance(duration, (int, float)):
            calc_duration = float(duration)
        elif isinstance(end, (int, float)) and isinstance(start, (int, float)):
            calc_duration = float(end) - float(start)

        return await cmd.execute(
            ffmpeg_path=self._ffmpeg_path or find_ffmpeg(),
            process_runner=self._runner,
            total_duration=calc_duration,
            timeout=timeout or self._default_timeout,
            on_progress=on_progress,
        )

    async def concat(
        self,
        inputs: Sequence[PathLike],
        output: PathLike,
        *,
        method: ConcatMethod = "demuxer",
        has_video: bool = True,
        has_audio: bool = True,
        timeout: float | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> ProcessResult:
        """Объединяет несколько медиафайлов в один выходной файл.

        Поддерживает:
        - `demuxer`: сверхбыстрое слияние без перекодирования через временный файл списка (по умолчанию).
        - `filter`: объединение через комплексный фильтр concat (с перекодированием, поддерживает разнородные файлы).
        """
        if not inputs:
            raise InvalidInputError(
                "", "Список входных файлов для объединения не может быть пустым."
            )

        if method == "demuxer":
            # Создаем временный файл списка для concat demuxer
            tmp_file = Path(tempfile.mktemp(dir=self._temp_dir, suffix=".txt"))
            self._created_temp_files.append(tmp_file)

            lines: list[str] = []
            for inp in inputs:
                # В demuxer пути должны быть абсолютными, с прямыми слэшами и экранированными кавычками
                resolved_path = Path(inp).resolve()
                clean_path = normalize_path_for_ffmpeg(resolved_path).replace("'", "'\\''")
                lines.append(f"file '{clean_path}'")

            tmp_file.write_text("\n".join(lines), encoding="utf-8")
            logger.debug(
                "Создан временный файл списка для concat demuxer: %s (%d записей)",
                tmp_file,
                len(lines),
            )

            cmd = (
                self.create_command()
                .overwrite()
                .input(tmp_file, f="concat", safe="0")
                .copy_all()
                .output(output)
            )

            try:
                return await cmd.execute(
                    ffmpeg_path=self._ffmpeg_path or find_ffmpeg(),
                    process_runner=self._runner,
                    timeout=timeout or self._default_timeout,
                    on_progress=on_progress,
                )
            finally:
                if tmp_file.exists():
                    with suppress(OSError):
                        tmp_file.unlink()
                        logger.debug("Удалён временный файл списка concat demuxer: %s", tmp_file)
                        if tmp_file in self._created_temp_files:
                            self._created_temp_files.remove(tmp_file)

        elif method == "filter":
            # Комплексный фильтр concat
            cmd = self.create_command().overwrite()
            for inp in inputs:
                cmd.input(inp)

            num_inputs = len(inputs)
            v_val = 1 if has_video else 0
            a_val = 1 if has_audio else 0

            stream_labels = ""
            for i in range(num_inputs):
                if has_video:
                    stream_labels += f"[{i}:v]"
                if has_audio:
                    stream_labels += f"[{i}:a]"

            out_labels = ""
            if has_video:
                out_labels += "[outv]"
            if has_audio:
                out_labels += "[outa]"

            concat_filter = f"{stream_labels}concat=n={num_inputs}:v={v_val}:a={a_val}{out_labels}"

            cmd.complex_filter(concat_filter)
            if has_video:
                cmd.map_stream("[outv]")
                cmd.video_codec("libx264")
            if has_audio:
                cmd.map_stream("[outa]")
                cmd.audio_codec("aac")
            cmd.output(output)

            return await cmd.execute(
                ffmpeg_path=self._ffmpeg_path or find_ffmpeg(),
                process_runner=self._runner,
                timeout=timeout or self._default_timeout,
                on_progress=on_progress,
            )
        else:
            raise ValueError(f"Неподдерживаемый метод конкатенации: {method}")

    async def screenshot(
        self,
        input: PathLike,  # noqa: A002
        output: PathLike,
        *,
        timestamp: float | str = 0,
        resolution: tuple[int, int] | None = None,
        quality: int = 2,
        timeout: float | None = None,
    ) -> ProcessResult:
        """Создает одиночный скриншот из видеофайла в заданный момент времени."""
        cmd = (
            self.create_command()
            .overwrite()
            .input(input, ss=str(timestamp))
            .output_option("vframes", 1)
        )

        if resolution is not None:
            cmd.video_filter(f"scale={resolution[0]}:{resolution[1]}")

        cmd.output_option("q:v", quality)
        cmd.output(output)

        return await cmd.execute(
            ffmpeg_path=self._ffmpeg_path or find_ffmpeg(),
            process_runner=self._runner,
            timeout=timeout or self._default_timeout,
        )

    async def thumbnails(
        self,
        input: PathLike,  # noqa: A002
        output_pattern: PathLike,
        *,
        interval: float | None = None,
        count: int | None = None,
        fps: float | None = None,
        resolution: tuple[int, int] | None = None,
        quality: int = 2,
        timeout: float | None = None,
    ) -> ProcessResult:
        """Генерирует серию превью-кадров по заданному интервалу, частоте или количеству кадров.

        Args:
            input: Путь к исходному видеофайлу.
            output_pattern: Шаблон вывода (например, 'thumb_%03d.jpg').
            interval: Интервал между превью в секундах (например, каждые 10 сек).
            count: Фиксированное общее количество превью (рассчитывает интервал из длительности).
            fps: Частота захвата кадров в секунду (e.g. 0.5 = кадр каждые 2 сек).
            resolution: Разрешение сохраняемых превью.
            quality: Качество JPEG (2 = максимальное).
            timeout: Таймаут операции.
        """
        vf_parts: list[str] = []

        if fps is not None:
            vf_parts.append(f"fps={fps}")
        elif interval is not None and interval > 0:
            vf_parts.append(f"fps=1/{interval}")
        elif count is not None and count > 0:
            info = await self.probe(input)
            dur = info.duration or 60.0
            computed_interval = dur / count
            vf_parts.append(f"fps=1/{computed_interval}")
        else:
            # По умолчанию кадр каждую секунду
            vf_parts.append("fps=1")

        if resolution is not None:
            vf_parts.append(f"scale={resolution[0]}:{resolution[1]}")

        cmd = (
            self.create_command()
            .overwrite()
            .input(input)
            .video_filter(",".join(vf_parts))
            .output_option("q:v", quality)
            .output(output_pattern)
        )

        return await cmd.execute(
            ffmpeg_path=self._ffmpeg_path or find_ffmpeg(),
            process_runner=self._runner,
            timeout=timeout or self._default_timeout,
        )

    async def convert(
        self,
        input: PathLike,  # noqa: A002
        output: PathLike,
        *,
        copy: bool = True,
        timeout: float | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> ProcessResult:
        """Выполняет конвертацию контейнера (например, MKV -> MP4 или TS -> MP4).

        По умолчанию `copy=True` выполняет мгновенное перепаковывание без сжатия.
        """
        total_duration = None
        if on_progress:
            total_duration = await self._resolve_duration_if_needed(input)

        cmd = self.create_command().overwrite().input(input)

        if copy:
            cmd.copy_all()
        else:
            cmd.video_codec("libx264").audio_codec("aac")

        cmd.output(output)

        return await cmd.execute(
            ffmpeg_path=self._ffmpeg_path or find_ffmpeg(),
            process_runner=self._runner,
            total_duration=total_duration,
            timeout=timeout or self._default_timeout,
            on_progress=on_progress,
        )

    async def normalize_audio(
        self,
        input: PathLike,  # noqa: A002
        output: PathLike,
        *,
        target_lufs: float = -14.0,
        target_tp: float = -1.0,
        target_lra: float = 7.0,
        codec: str = "aac",
        bitrate: str = DEFAULT_AUDIO_BITRATE,
        timeout: float | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> ProcessResult:
        """Нормализует громкость звука по вещательным стандартам EBU R128 / ITU-R BS.1770."""
        total_duration = None
        if on_progress:
            total_duration = await self._resolve_duration_if_needed(input)

        norm_filter = loudnorm(i=target_lufs, lra=target_lra, tp=target_tp)

        cmd = (
            self.create_command()
            .overwrite()
            .input(input)
            .copy_video()
            .audio_filter(norm_filter)
            .audio_codec(codec)
            .audio_bitrate(bitrate)
            .output(output)
        )

        return await cmd.execute(
            ffmpeg_path=self._ffmpeg_path or find_ffmpeg(),
            process_runner=self._runner,
            total_duration=total_duration,
            timeout=timeout or self._default_timeout,
            on_progress=on_progress,
        )

    async def scale(
        self,
        input: PathLike,  # noqa: A002
        output: PathLike,
        *,
        width: int | tuple[int, int],
        height: int | None = None,
        video_codec: VideoCodec | str = "libx264",
        crf: int = DEFAULT_VIDEO_CRF,
        preset: VideoPreset | str = DEFAULT_VIDEO_PRESET,
        audio_codec: AudioCodec | str = "copy",
        timeout: float | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> ProcessResult:
        """Масштабирует видео в заданное разрешение."""
        if isinstance(width, tuple):
            w, h = width
        elif height is not None:
            w, h = width, height
        else:
            raise ValueError(
                "Необходимо указать высоту height или передать кортеж (ширина, высота)"
            )

        if w <= 0 or h <= 0:
            raise ValueError(f"Размеры кадра должны быть строго положительными, получено: {w}x{h}")
        if not (0 <= crf <= 51):
            raise ValueError(f"Параметр crf должен быть в диапазоне от 0 до 51, получено: {crf}")

        total_duration = None
        if on_progress:
            total_duration = await self._resolve_duration_if_needed(input)

        cmd = (
            self.create_command()
            .overwrite()
            .input(input)
            .video_filter(scale(w, h))
            .video_codec(video_codec)
            .crf(crf)
            .preset(preset)
        )

        if str(audio_codec) == "copy":
            cmd.copy_audio()
        else:
            cmd.audio_codec(audio_codec)

        cmd.output(output)

        return await cmd.execute(
            ffmpeg_path=self._ffmpeg_path or find_ffmpeg(),
            process_runner=self._runner,
            total_duration=total_duration,
            timeout=timeout or self._default_timeout,
            on_progress=on_progress,
        )

    async def two_pass_transcode(
        self,
        input: PathLike,  # noqa: A002
        output: PathLike,
        *,
        video_codec: VideoCodec | str = "libx264",
        bitrate: str = "2000k",
        audio_codec: AudioCodec | str = "aac",
        audio_bitrate: str = DEFAULT_AUDIO_BITRATE,
        preset: VideoPreset | str = DEFAULT_VIDEO_PRESET,
        passlogfile: PathLike | None = None,
        timeout: float | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> ProcessResult:
        """Выполняет двухпроходное кодирование (2-pass) для максимального качества при заданном битрейте.

        Первый проход анализирует сложность сцен и генерирует статистику в лог-файл без записи звука.
        Второй проход использует собранную статистику для оптимального распределения битрейта.

        Args:
            input: Путь к исходному медиафайлу.
            output: Путь к целевому файлу с результатом.
            video_codec: Кодек видео (по умолчанию 'libx264').
            bitrate: Целевой битрейт видео (например, '2000k' или '4M').
            audio_codec: Кодек аудио (по умолчанию 'aac').
            audio_bitrate: Битрейт аудиопотока (по умолчанию DEFAULT_AUDIO_BITRATE).
            preset: Пресет кодировщика.
            passlogfile: Пользовательский префикс пути к файлам журнала проходов.
            timeout: Таймаут на каждый проход в секундах.
            on_progress: Функция обратного вызова для отслеживания прогресса (вызывается на обоих проходах).

        Returns:
            ProcessResult результата второго прохода кодирования.
        """
        temp_log_prefix: Path | None = None
        if passlogfile is None:
            temp_log_prefix = Path(tempfile.mktemp(dir=self._temp_dir, prefix="ffmpeg2pass_"))
            log_prefix_str = normalize_path_for_ffmpeg(temp_log_prefix)
        else:
            log_prefix_str = normalize_path_for_ffmpeg(passlogfile)

        total_duration = None
        if on_progress:
            total_duration = await self._resolve_duration_if_needed(input)

        logger.info(
            "Запуск двухпроходного кодирования для '%s' -> '%s' (битрейт=%s, кодек=%s)",
            input,
            output,
            bitrate,
            video_codec,
        )

        try:
            # Первый проход: анализ видео и сбор статистики
            cmd_pass1 = (
                self.create_command()
                .overwrite()
                .input(input)
                .video_codec(video_codec)
                .video_bitrate(bitrate)
                .output_option("-pass", 1)
                .output_option("-passlogfile", log_prefix_str)
                .preset(preset)
                .no_audio()
                .format("null")
                .output(get_null_device())
            )

            res1 = await cmd_pass1.execute(
                ffmpeg_path=self._ffmpeg_path or find_ffmpeg(),
                process_runner=self._runner,
                total_duration=total_duration,
                timeout=timeout or self._default_timeout,
                on_progress=on_progress,
            )
            if not res1.is_success:
                logger.warning(
                    "Первый проход двухпроходного кодирования завершился ошибкой (код=%d)",
                    res1.exit_code,
                )
                return res1

            logger.info(
                "Первый проход двухпроходного кодирования успешно завершён за %.2f с",
                res1.duration_seconds,
            )

            # Второй проход: финальное кодирование с учетом статистики
            cmd_pass2 = (
                self.create_command()
                .overwrite()
                .input(input)
                .video_codec(video_codec)
                .video_bitrate(bitrate)
                .output_option("-pass", 2)
                .output_option("-passlogfile", log_prefix_str)
                .preset(preset)
                .audio_codec(audio_codec)
                .audio_bitrate(audio_bitrate)
                .output(output)
            )

            res2 = await cmd_pass2.execute(
                ffmpeg_path=self._ffmpeg_path or find_ffmpeg(),
                process_runner=self._runner,
                total_duration=total_duration,
                timeout=timeout or self._default_timeout,
                on_progress=on_progress,
            )
            if res2.is_success:
                logger.info(
                    "Второй проход двухпроходного кодирования успешно завершён за %.2f с",
                    res2.duration_seconds,
                )
            else:
                logger.warning(
                    "Второй проход двухпроходного кодирования завершился ошибкой (код=%d)",
                    res2.exit_code,
                )
            return res2
        finally:
            if temp_log_prefix is not None:
                parent_dir = temp_log_prefix.parent
                prefix_name = temp_log_prefix.name
                for log_file in parent_dir.glob(f"{prefix_name}*"):
                    with suppress(OSError):
                        log_file.unlink()
                logger.debug(
                    "Очищены временные файлы двухпроходного кодирования с префиксом '%s'",
                    prefix_name,
                )

    async def create_contact_sheet(
        self,
        input: PathLike,  # noqa: A002
        output: PathLike,
        *,
        rows: int = 3,
        cols: int = 4,
        frame_interval: float | None = None,
        width: int = 320,
        timeout: float | None = None,
    ) -> ProcessResult:
        """Создает обзорную сетку кадров (contact sheet / storyboard) из видеофайла.

        Масштабирует кадры до одинаковой ширины и компонует их в матрицу через фильтр `tile`.
        Если frame_interval не указан, интервал между кадрами рассчитывается автоматически
        на основе длительности видео и параметров сетки.

        Args:
            input: Исходный видеофайл.
            output: Целевой файл изображения (JPG, PNG).
            rows: Количество строк в сетке (по умолчанию 3).
            cols: Количество столбцов в сетке (по умолчанию 4).
            frame_interval: Интервал между кадрами в секундах. При None рассчитывается равномерно.
            width: Ширина каждого отдельного кадра мозаики в пикселях.
            timeout: Таймаут выполнения операции в секундах.

        Returns:
            ProcessResult с результатом выполнения команды FFmpeg.
        """
        step = frame_interval
        if step is None or step <= 0:
            total_tiles = max(1, rows * cols)
            duration = await self._resolve_duration_if_needed(input)
            step = duration / (total_tiles + 1) if duration and duration > 0 else 2.0

        # Формируем цепочку фильтров: fps -> scale -> tile
        fps_val = max(1.0 / step, 0.0001)
        tile_filter = f"fps={fps_val:.4f},scale={width}:-1,tile={cols}x{rows}"

        cmd = (
            self.create_command()
            .overwrite()
            .input(input)
            .video_filter(tile_filter)
            .frames(1, "v")
            .output(output)
        )

        return await cmd.execute(
            ffmpeg_path=self._ffmpeg_path or find_ffmpeg(),
            process_runner=self._runner,
            timeout=timeout or self._default_timeout,
        )

    async def detect_silence(
        self,
        input: PathLike,  # noqa: A002
        *,
        noise_tolerance_db: float = -30.0,
        min_duration: float = 0.5,
        timeout: float | None = None,
    ) -> list[SilenceInterval]:
        """Обнаруживает интервалы тишины в звуковой дорожке медиафайла.

        Применяет аудиофильтр `silencedetect` FFmpeg и анализирует stderr-лог для
        формирования списка меток начала, окончания и длительности пауз.

        Args:
            input: Исходный медиафайл.
            noise_tolerance_db: Порог шума в децибелах (например, -30.0 или -50.0). Сигналы тише порога считаются тишиной.
            min_duration: Минимальная длительность тишины в секундах для ее фиксации.
            timeout: Таймаут выполнения операции в секундах.

        Returns:
            Список интервалов SilenceInterval с временными метками обнаруженной тишины.
        """
        logger.info(
            "Анализ пауз и тишины в '%s' (порог=%.1f dB, мин. длительность=%.2f с)",
            input,
            noise_tolerance_db,
            min_duration,
        )
        filter_str = f"silencedetect=noise={noise_tolerance_db}dB:d={min_duration}"

        cmd = (
            self.create_command()
            .overwrite()
            .loglevel("info")
            .input(input)
            .audio_filter(filter_str)
            .no_video()
            .no_subtitles()
            .format("null")
            .output(get_null_device())
        )

        result = await cmd.execute(
            ffmpeg_path=self._ffmpeg_path or find_ffmpeg(),
            process_runner=self._runner,
            timeout=timeout or self._default_timeout,
        )

        intervals: list[SilenceInterval] = []
        current_start: float | None = None

        for line in result.stderr_text.splitlines():
            start_match = _RE_SILENCE_START.search(line)
            if start_match:
                with suppress(ValueError):
                    current_start = float(start_match.group(1))
                continue

            end_match = _RE_SILENCE_END.search(line)
            if end_match:
                with suppress(ValueError):
                    end_val = float(end_match.group(1))
                    dur_val = float(end_match.group(2))
                    start_val = (
                        current_start if current_start is not None else max(0.0, end_val - dur_val)
                    )
                    intervals.append(
                        SilenceInterval(start=start_val, end=end_val, duration=dur_val)
                    )
                    current_start = None

        if current_start is not None:
            # Тишина продолжалась до конца файла
            duration = await self._resolve_duration_if_needed(input)
            if duration is not None and duration > current_start:
                intervals.append(
                    SilenceInterval(
                        start=current_start,
                        end=duration,
                        duration=duration - current_start,
                    )
                )

        logger.info("Обнаружено интервалов тишины: %d в '%s'", len(intervals), input)
        return intervals
