"""Строгий, типизированный Fluent Command Builder для FFmpeg CLI.

Соблюдает строгий порядок аргументов FFmpeg:
[ffmpeg] [global_options] {[input_options] -i input} ... {[filters]} {[output_options] output} ...
"""

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, Self

from async_ffmpeg._compat import normalize_path_for_ffmpeg
from async_ffmpeg._constants import DEFAULT_LOGLEVEL, DEFAULT_STATS_PERIOD
from async_ffmpeg._discovery import find_ffmpeg
from async_ffmpeg._types import (
    LogLevel,
    MediaInputProtocol,
    PathLike,
    ProgressCallback,
    StderrCallback,
    VideoPreset,
)
from async_ffmpeg.exceptions import CommandBuildError
from async_ffmpeg.filters import Filter, FilterChain, FilterGraph
from async_ffmpeg.process import ProcessResult, ProcessRunner
from async_ffmpeg.progress import ProgressParser

type FilterLike = str | Filter | FilterChain | FilterGraph


def _format_option_key(key: str) -> str:
    """Нормализует имя опции: заменяет подчеркивания на дефисы или двоеточия."""
    clean = key.strip()
    if not clean.startswith("-"):
        clean = f"-{clean}"
    # Заменяем _ на : для спецификаторов потоков (например -c_v -> -c:v, -b_a -> -b:a)
    for prefix in ("-c_", "-b_", "-q_", "-s_"):
        if clean.startswith(prefix):
            clean = clean.replace(prefix, prefix[:-1] + ":", 1)
    # Заменяем остальные _ на - (например preset_name -> preset-name)
    if not clean.startswith(("-c:", "-b:", "-q:", "-s:")):
        clean = clean.replace("_", "-")
    return clean


@dataclass(frozen=True, slots=True)
class InputEntry:
    """Входной источник с индивидуальными опциями, предшествующими -i."""

    target: str
    options: tuple[tuple[str, str | None], ...] = ()


@dataclass(frozen=True, slots=True)
class OutputEntry:
    """Выходной файл с индивидуальными опциями кодирования."""

    target: str
    options: tuple[tuple[str, str | None], ...] = ()


class FFmpegCommand:
    """Построитель командной строки FFmpeg с контролем синтаксиса и порядка аргументов."""

    def __init__(self) -> None:
        self._global_options: list[tuple[str, str | None]] = []
        self._inputs: list[InputEntry] = []
        self._outputs: list[OutputEntry] = []
        self._video_filter: str | None = None
        self._audio_filter: str | None = None
        self._complex_filter: str | None = None
        self._pending_output_options: list[tuple[str, str | None]] = []
        self._overwrite: bool | None = None
        self._no_stdin: bool = True
        self._hide_banner: bool = True
        self._loglevel: str = DEFAULT_LOGLEVEL
        self._progress_url: str | None = None
        self._stats_period: float | None = None
        self._extra_args: list[str] = []

    # === Глобальные опции ===

    def overwrite(self, yes: bool = True) -> Self:
        """Включает (-y) или отключает перезапись существующих файлов."""
        self._overwrite = yes
        return self

    def no_overwrite(self) -> Self:
        """Запрещает перезапись существующих файлов (-n)."""
        self._overwrite = False
        return self

    def no_stdin(self, yes: bool = True) -> Self:
        """Отключает интерактивный ввод через stdin (-nostdin)."""
        self._no_stdin = yes
        return self

    def hide_banner(self, yes: bool = True) -> Self:
        """Подавляет вывод начального баннера сборки FFmpeg (-hide_banner)."""
        self._hide_banner = yes
        return self

    def loglevel(self, level: LogLevel | str) -> Self:
        """Устанавливает уровень логирования FFmpeg (-loglevel)."""
        self._loglevel = str(level)
        return self

    def progress(self, url: str = "pipe:1", stats_period: float | None = None) -> Self:
        """Направляет машиночитаемый прогресс (-progress)."""
        self._progress_url = url
        if stats_period is not None:
            self._stats_period = stats_period
        return self

    def stats_period(self, seconds: float) -> Self:
        """Задает интервал отправки статистики прогресса (-stats_period)."""
        self._stats_period = seconds
        return self

    def global_option(self, key: str, value: str | int | float | None = None) -> Self:
        """Добавляет произвольную глобальную опцию."""
        opt_key = _format_option_key(key)
        self._global_options.append((opt_key, str(value) if value is not None else None))
        return self

    # === Входы ===

    def input(self, target: PathLike | MediaInputProtocol, **opts: Any) -> Self:
        """Добавляет входной источник данных (-i) с предшествующими опциями."""
        if isinstance(target, MediaInputProtocol):
            str_target = target.to_ffmpeg_input()
        else:
            str_target = normalize_path_for_ffmpeg(target)

        input_opts: list[tuple[str, str | None]] = []
        for k, v in opts.items():
            opt_key = _format_option_key(k)
            if v is True:
                input_opts.append((opt_key, None))
            elif v is not False and v is not None:
                input_opts.append((opt_key, str(v)))

        self._inputs.append(InputEntry(target=str_target, options=tuple(input_opts)))
        return self

    # === Фильтры ===

    def video_filter(self, filtergraph: FilterLike) -> Self:
        """Устанавливает простой видео-фильтр (-vf)."""
        self._video_filter = str(filtergraph)
        return self

    def audio_filter(self, filtergraph: FilterLike) -> Self:
        """Устанавливает простой аудио-фильтр (-af)."""
        self._audio_filter = str(filtergraph)
        return self

    def complex_filter(self, filtergraph: FilterLike) -> Self:
        """Устанавливает комплексный граф фильтров (-filter_complex)."""
        self._complex_filter = str(filtergraph)
        return self

    # === Опции выходных потоков (применяются к следующему output()) ===

    def video_codec(self, codec: str, stream_spec: str | None = None) -> Self:
        """Устанавливает видеокодек (-c:v или -c:v:X)."""
        opt = f"-c:v:{stream_spec}" if stream_spec else "-c:v"
        self._pending_output_options.append((opt, codec))
        return self

    def audio_codec(self, codec: str, stream_spec: str | None = None) -> Self:
        """Устанавливает аудиокодек (-c:a или -c:a:X)."""
        opt = f"-c:a:{stream_spec}" if stream_spec else "-c:a"
        self._pending_output_options.append((opt, codec))
        return self

    def subtitle_codec(self, codec: str, stream_spec: str | None = None) -> Self:
        """Устанавливает кодек субтитров (-c:s или -c:s:X)."""
        opt = f"-c:s:{stream_spec}" if stream_spec else "-c:s"
        self._pending_output_options.append((opt, codec))
        return self

    def codec(self, codec: str) -> Self:
        """Устанавливает единый кодек для всех потоков (например -c copy)."""
        self._pending_output_options.append(("-c", codec))
        return self

    def video_bitrate(self, bitrate: str | int, stream_spec: str | None = None) -> Self:
        """Устанавливает битрейт видео (-b:v)."""
        opt = f"-b:v:{stream_spec}" if stream_spec else "-b:v"
        self._pending_output_options.append((opt, str(bitrate)))
        return self

    def audio_bitrate(self, bitrate: str | int, stream_spec: str | None = None) -> Self:
        """Устанавливает битрейт аудио (-b:a)."""
        opt = f"-b:a:{stream_spec}" if stream_spec else "-b:a"
        self._pending_output_options.append((opt, str(bitrate)))
        return self

    def preset(self, name: VideoPreset | str) -> Self:
        """Устанавливает пресет кодировщика (-preset)."""
        self._pending_output_options.append(("-preset", str(name)))
        return self

    def crf(self, value: int) -> Self:
        """Устанавливает фактор постоянного качества (-crf)."""
        self._pending_output_options.append(("-crf", str(value)))
        return self

    def resolution(self, width: int, height: int) -> Self:
        """Устанавливает выходное разрешение (-s WxH)."""
        self._pending_output_options.append(("-s", f"{width}x{height}"))
        return self

    def fps(self, rate: float | int) -> Self:
        """Устанавливает частоту кадров вывода (-r)."""
        self._pending_output_options.append(("-r", str(rate)))
        return self

    def pixel_format(self, fmt: str) -> Self:
        """Устанавливает пиксельный формат (-pix_fmt)."""
        self._pending_output_options.append(("-pix_fmt", fmt))
        return self

    def map(self, stream_spec: str) -> Self:
        """Добавляет сопоставление потока (-map)."""
        self._pending_output_options.append(("-map", stream_spec))
        return self

    def map_stream(self, stream_spec: str) -> Self:
        """Алиас для map(): добавляет сопоставление потока (-map)."""
        return self.map(stream_spec)

    def no_video(self) -> Self:
        """Отключает запись видеопотока (-vn)."""
        self._pending_output_options.append(("-vn", None))
        return self

    def no_audio(self) -> Self:
        """Отключает запись аудиопотока (-an)."""
        self._pending_output_options.append(("-an", None))
        return self

    def no_subtitles(self) -> Self:
        """Отключает запись субтитров (-sn)."""
        self._pending_output_options.append(("-sn", None))
        return self

    def metadata(self, key: str, value: str) -> Self:
        """Устанавливает тег метаданных (-metadata key=value)."""
        self._pending_output_options.append(("-metadata", f"{key}={value}"))
        return self

    def format(self, fmt: str) -> Self:
        """Задает формат выходного контейнера (-f)."""
        self._pending_output_options.append(("-f", fmt))
        return self

    def output_option(self, key: str, value: str | int | float | None = None) -> Self:
        """Добавляет произвольную опцию к текущему выходному файлу."""
        opt_key = _format_option_key(key)
        self._pending_output_options.append((opt_key, str(value) if value is not None else None))
        return self

    # === Выходы ===

    def output(self, target: PathLike, **opts: Any) -> Self:
        """Добавляет выходной файл, объединяя накопленные опции и переданные в kwargs."""
        str_target = normalize_path_for_ffmpeg(target)

        combined_opts = list(self._pending_output_options)
        self._pending_output_options = []

        for k, v in opts.items():
            opt_key = _format_option_key(k)
            if v is True:
                combined_opts.append((opt_key, None))
            elif v is not False and v is not None:
                combined_opts.append((opt_key, str(v)))

        self._outputs.append(OutputEntry(target=str_target, options=tuple(combined_opts)))
        return self

    def extra_args(self, *args: str) -> Self:
        """Добавляет сырые аргументы в конец команды перед выходами."""
        self._extra_args.extend(args)
        return self

    # === Сборка команды ===

    def build(self, ffmpeg_path: PathLike | None = None) -> list[str]:
        """Собирает и возвращает строгий список аргументов командной строки FFmpeg.

        Raises:
            CommandBuildError: если команда не содержит входов или выходов.
        """
        if not self._inputs:
            raise CommandBuildError("Команда должна содержать хотя бы один входной файл (-i).")
        if not self._outputs and not self._pending_output_options:
            raise CommandBuildError("Команда должна содержать хотя бы один выходной файл.")

        bin_path = str(find_ffmpeg(custom_path=ffmpeg_path))
        cmd: list[str] = [bin_path]

        # 1. Глобальные опции
        if self._overwrite is True:
            cmd.append("-y")
        elif self._overwrite is False:
            cmd.append("-n")

        if self._no_stdin:
            cmd.append("-nostdin")

        if self._hide_banner:
            cmd.append("-hide_banner")

        if self._loglevel:
            cmd.extend(["-loglevel", self._loglevel])

        if self._progress_url:
            cmd.extend(["-progress", self._progress_url])

        if self._stats_period is not None:
            cmd.extend(["-stats_period", str(self._stats_period)])

        for opt_key, opt_val in self._global_options:
            cmd.append(opt_key)
            if opt_val is not None:
                cmd.append(opt_val)

        # 2. Входные файлы и их опции
        for inp in self._inputs:
            for opt_key, opt_val in inp.options:
                cmd.append(opt_key)
                if opt_val is not None:
                    cmd.append(opt_val)
            cmd.extend(["-i", inp.target])

        # 3. Фильтры
        if self._complex_filter:
            cmd.extend(["-filter_complex", self._complex_filter])
        if self._video_filter:
            cmd.extend(["-vf", self._video_filter])
        if self._audio_filter:
            cmd.extend(["-af", self._audio_filter])

        # 4. Дополнительные опции
        if self._extra_args:
            cmd.extend(self._extra_args)

        # 5. Выходные файлы и их опции
        for out in self._outputs:
            for opt_key, opt_val in out.options:
                cmd.append(opt_key)
                if opt_val is not None:
                    cmd.append(opt_val)
            cmd.append(out.target)

        return cmd

    def build_pretty(self, ffmpeg_path: PathLike | None = None) -> str:
        """Возвращает форматированную многострочную строку команды для удобного чтения."""
        args = self.build(ffmpeg_path=ffmpeg_path)
        lines: list[str] = [args[0]]
        i = 1
        while i < len(args):
            arg = args[i]
            if arg.startswith("-") and i + 1 < len(args) and not args[i + 1].startswith("-"):
                lines.append(f"  {arg} {args[i + 1]}")
                i += 2
            else:
                lines.append(f"  {arg}")
                i += 1
        return " \\\n".join(lines)

    async def execute(
        self,
        *,
        ffmpeg_path: PathLike | None = None,
        process_runner: ProcessRunner | None = None,
        timeout: float | None = None,
        total_duration: float | None = None,
        on_progress: ProgressCallback | None = None,
        on_stderr: StderrCallback | None = None,
        check: bool = True,
    ) -> ProcessResult:
        """Собирает и асинхронно исполняет команду с обработкой прогресса.

        Если передан `on_progress`, автоматически настраивает `-progress pipe:1`
        и парсинг через `ProgressParser`.
        """
        # Автоподключение флага прогресса, если передан callback
        if on_progress and not self._progress_url:
            self.progress(url="pipe:1", stats_period=self._stats_period or DEFAULT_STATS_PERIOD)

        cmd = self.build(ffmpeg_path=ffmpeg_path)
        runner = process_runner or ProcessRunner()

        progress_parser: ProgressParser | None = None
        if on_progress:
            progress_parser = ProgressParser(
                total_duration=total_duration,
                on_progress=on_progress,
            )

        async def _stdout_handler(line: str) -> None:
            if progress_parser:
                info = progress_parser.feed_line(line)
                if info is not None and on_progress:
                    res = on_progress(info)
                    if isinstance(res, Awaitable):
                        await res

        return await runner.run(
            cmd,
            timeout=timeout,
            on_stdout_line=_stdout_handler if on_progress else None,
            on_stderr_line=on_stderr,
            check=check,
        )
