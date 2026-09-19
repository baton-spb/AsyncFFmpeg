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

import tempfile
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from async_ffmpeg.pipeline import MediaPipeline

from async_ffmpeg._compat import normalize_path_for_ffmpeg
from async_ffmpeg._constants import (
    DEFAULT_AUDIO_BITRATE,
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_VIDEO_CRF,
    DEFAULT_VIDEO_PRESET,
)
from async_ffmpeg._discovery import find_ffmpeg
from async_ffmpeg._types import (
    ConcatMethod,
    PathLike,
    ProgressCallback,
    StderrCallback,
    VideoPreset,
)
from async_ffmpeg.command import FFmpegCommand
from async_ffmpeg.exceptions import InvalidInputError
from async_ffmpeg.filters import Filter, FilterChain, FilterGraph, loudnorm, scale
from async_ffmpeg.hardware import HardwareAccel
from async_ffmpeg.models import MediaInfo
from async_ffmpeg.probe import FFprobe
from async_ffmpeg.process import ProcessResult, ProcessRunner


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
        await self._runner.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
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
        except Exception:
            return None

    # =========================================================================
    # Основные операции
    # =========================================================================

    async def transcode(
        self,
        input: PathLike,  # noqa: A002
        output: PathLike,
        *,
        video_codec: str | None = None,
        audio_codec: str | None = None,
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
        calc_duration = total_duration
        if on_progress and calc_duration is None:
            if isinstance(duration, (int, float)):
                calc_duration = float(duration)
            else:
                calc_duration = await self._resolve_duration_if_needed(input)

        cmd = self.create_command().overwrite()

        # Входные опции
        input_opts: dict[str, Any] = {}
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
        codec: str = "aac",
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
        input_opts: dict[str, Any] = {}
        if start is not None:
            input_opts["ss"] = start

        output_opts: dict[str, Any] = {}
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
                # В demuxer пути должны быть с прямыми слэшами и экранированными одинарными кавычками
                clean_path = normalize_path_for_ffmpeg(inp).replace("'", "'\\''")
                lines.append(f"file '{clean_path}'")

            tmp_file.write_text("\n".join(lines), encoding="utf-8")

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
        width: int,
        height: int,
        video_codec: str = "libx264",
        crf: int = DEFAULT_VIDEO_CRF,
        preset: VideoPreset | str = DEFAULT_VIDEO_PRESET,
        audio_codec: str = "copy",
        timeout: float | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> ProcessResult:
        """Масштабирует видео в заданное разрешение."""
        total_duration = None
        if on_progress:
            total_duration = await self._resolve_duration_if_needed(input)

        cmd = (
            self.create_command()
            .overwrite()
            .input(input)
            .video_filter(scale(width, height))
            .video_codec(video_codec)
            .crf(crf)
            .preset(preset)
        )

        if audio_codec == "copy":
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
