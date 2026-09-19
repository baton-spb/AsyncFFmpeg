"""Высокоуровневый конвейер (MediaPipeline) для объединения операций FFmpeg в единый процесс.

Позволяет формировать цепочки преобразований:
```python
pipeline = (
    MediaPipeline("input.mp4")
    .trim(start=10, end=30)
    .scale(1280, 720)
    .fps(30)
    .watermark("logo.png", position="top-right", margin=15)
    .normalize_audio()
    .video_codec("libx264", preset="fast", crf=22)
    .audio_codec("aac", bitrate="192k")
    .output("output.mp4")
)
result = await pipeline.run(on_progress=my_callback)
```
"""

from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from async_ffmpeg._discovery import find_ffmpeg, find_ffprobe
from async_ffmpeg._logging import get_logger
from async_ffmpeg._types import (
    CommandOptionValue,
    MediaInputProtocol,
    PathLike,
    ProgressCallback,
    StderrCallback,
    VideoPreset,
    WatermarkPosition,
)
from async_ffmpeg.command import FFmpegCommand
from async_ffmpeg.exceptions import CommandBuildError
from async_ffmpeg.filters import (
    ComplexFilterGraph,
    Filter,
    FilterChain,
    afade,
    atempo,
    crop,
    drawtext,
    loudnorm,
    overlay,
    pad,
    volume,
)
from async_ffmpeg.filters import (
    fps as fps_filter,
)
from async_ffmpeg.filters import (
    hflip as hflip_filter,
)
from async_ffmpeg.filters import (
    rotate as rotate_filter,
)
from async_ffmpeg.filters import (
    scale as scale_filter,
)
from async_ffmpeg.filters import (
    transpose as transpose_filter,
)
from async_ffmpeg.filters import (
    vflip as vflip_filter,
)
from async_ffmpeg.probe import FFprobe
from async_ffmpeg.process import ProcessResult, ProcessRunner

if TYPE_CHECKING:
    from async_ffmpeg.client import FFmpegClient

logger = get_logger("pipeline")


@dataclass(frozen=True, slots=True)
class WatermarkConfig:
    """Конфигурация наложения водяного знака / логотипа поверх видео."""

    target: PathLike
    position: WatermarkPosition = "bottom-right"
    margin: int = 10
    opacity: float | None = None


def _calculate_watermark_xy(position: WatermarkPosition, margin: int) -> tuple[str, str]:
    """Вычисляет координаты x и y для фильтра overlay в FFmpeg."""
    if position == "top-left":
        return str(margin), str(margin)
    elif position == "top-right":
        return f"main_w-overlay_w-{margin}", str(margin)
    elif position == "bottom-left":
        return str(margin), f"main_h-overlay_h-{margin}"
    elif position == "bottom-right":
        return f"main_w-overlay_w-{margin}", f"main_h-overlay_h-{margin}"
    elif position == "center":
        return "(main_w-overlay_w)/2", "(main_h-overlay_h)/2"
    return f"main_w-overlay_w-{margin}", f"main_h-overlay_h-{margin}"


class MediaPipeline:
    """Высокоуровневый конвейер операций медиаобработки.

    Объединяет цепочки фильтров, обрезку, наложение слоев и транскодирование в один процесс FFmpeg.
    """

    def __init__(
        self,
        input: PathLike | MediaInputProtocol | None = None,  # noqa: A002
        *,
        client: FFmpegClient | None = None,
        ffmpeg_path: PathLike | None = None,
        ffprobe_path: PathLike | None = None,
    ) -> None:
        """Инициализирует конвейер обработки медиаданных.

        Args:
            input: Исходный входной медиафайл или URL (опционально).
            client: Экземпляр FFmpegClient для исполнения задач.
            ffmpeg_path: Пользовательский путь к бинарнику ffmpeg.
            ffprobe_path: Пользовательский путь к бинарнику ffprobe.
        """
        self._client = client
        self._ffmpeg_path = ffmpeg_path
        self._ffprobe_path = ffprobe_path

        # Входы
        self._inputs: list[tuple[PathLike | MediaInputProtocol, dict[str, CommandOptionValue]]] = []
        if input is not None:
            self.input(input)

        # Обрезка и тайминг
        self._start: float | str | None = None
        self._end: float | str | None = None
        self._duration: float | str | None = None
        self._fast_seek: bool = True

        # Видеофильтры
        self._video_filters: list[Filter | str] = []
        self._watermark: WatermarkConfig | None = None

        # Аудиофильтры
        self._audio_filters: list[Filter | str] = []

        # Настройки кодеков
        self._video_codec: str | None = None
        self._video_preset: VideoPreset | str | None = None
        self._video_crf: int | None = None
        self._video_bitrate: str | int | None = None
        self._copy_video: bool = False
        self._no_video: bool = False

        self._audio_codec: str | None = None
        self._audio_bitrate: str | int | None = None
        self._audio_sample_rate: int | None = None
        self._audio_channels: int | None = None
        self._copy_audio: bool = False
        self._no_audio: bool = False

        self._subtitle_codec: str | None = None
        self._no_subtitles: bool = False

        self._copy_all: bool = False

        # Аппаратное ускорение
        self._hwaccel_name: str | None = None
        self._hwaccel_device: str | None = None
        self._hwaccel_output_format: str | None = None

        # Маппинг и метаданные
        self._stream_maps: list[str] = []
        self._metadata: dict[str, str] = {}
        self._extra_args: list[str] = []

        # Выходы
        self._outputs: list[tuple[PathLike, dict[str, CommandOptionValue]]] = []

    # ========================================================================
    # Входные файлы и аппаратное ускорение
    # ========================================================================

    def input(self, target: PathLike | MediaInputProtocol, **opts: CommandOptionValue) -> Self:
        """Добавляет входной источник данных к конвейеру.

        Args:
            target: Путь к файлу, URL или объект, реализующий MediaInputProtocol.
            **opts: Опции, применяемые к данному входному файлу.

        Returns:
            Экземпляр MediaPipeline для цепочечных вызовов.
        """
        self._inputs.append((target, opts))
        return self

    def add_input(self, target: PathLike | MediaInputProtocol, **opts: CommandOptionValue) -> Self:
        """Добавляет дополнительный входной источник данных к конвейеру.

        Args:
            target: Путь к файлу, URL или объект, реализующий MediaInputProtocol.
            **opts: Опции входного файла.

        Returns:
            Экземпляр MediaPipeline для цепочечных вызовов.
        """
        return self.input(target, **opts)

    def hwaccel(
        self,
        name: str,
        device: str | None = None,
        output_format: str | None = None,
    ) -> Self:
        """Включает аппаратное ускорение для обработки входа (-hwaccel)."""
        self._hwaccel_name = name
        self._hwaccel_device = device
        self._hwaccel_output_format = output_format
        return self

    # ========================================================================
    # Обрезка и тайминг
    # ========================================================================

    def trim(
        self,
        start: float | str | None = None,
        end: float | str | None = None,
        duration: float | str | None = None,
        *,
        fast_seek: bool = True,
    ) -> Self:
        """Задает диапазон обрезки медиафайла.

        Args:
            start: Начало фрагмента в секундах или формате "HH:MM:SS".
            end: Конец фрагмента.
            duration: Длительность фрагмента.
            fast_seek: Использовать быстрый поиск перед -i (True) или точный после -i (False).
        """
        self._start = start
        self._end = end
        self._duration = duration
        self._fast_seek = fast_seek
        return self

    def seek(self, start: float | str, *, fast: bool = True) -> Self:
        """Устанавливает точку старта (-ss)."""
        self._start = start
        self._fast_seek = fast
        return self

    def duration(self, duration: float | str) -> Self:
        """Устанавливает длительность фрагмента (-t)."""
        self._duration = duration
        return self

    # ========================================================================
    # Преобразования видео
    # ========================================================================

    def scale(
        self,
        width: int,
        height: int,
        *,
        keep_aspect_ratio: bool = False,
        force_original_aspect_ratio: str | None = None,
    ) -> Self:
        """Изменяет разрешение видео."""
        force = force_original_aspect_ratio
        if keep_aspect_ratio and force is None:
            force = "decrease"
        self._video_filters.append(scale_filter(width, height, force_original_aspect_ratio=force))
        return self

    def crop(
        self,
        w: int | str,
        h: int | str,
        x: int | str = "(in_w-out_w)/2",
        y: int | str = "(in_h-out_h)/2",
    ) -> Self:
        """Обрезает видеокадр по координатам (crop)."""
        self._video_filters.append(crop(w, h, x, y))
        return self

    def pad(
        self,
        w: int | str,
        h: int | str,
        x: int | str = "(ow-iw)/2",
        y: int | str = "(oh-ih)/2",
        color: str = "black",
    ) -> Self:
        """Добавляет поля (паддинг) вокруг видео (pad)."""
        self._video_filters.append(pad(w, h, x, y, color=color))
        return self

    def fps(self, rate: float | int | str) -> Self:
        """Изменяет частоту кадров (fps)."""
        self._video_filters.append(fps_filter(rate))
        return self

    def rotate(self, angle: float | str, fillcolor: str = "black") -> Self:
        """Поворачивает видео на угол в радианах (rotate)."""
        self._video_filters.append(rotate_filter(angle, fillcolor=fillcolor))
        return self

    def vflip(self) -> Self:
        """Отражает видео вертикально (vflip)."""
        self._video_filters.append(vflip_filter())
        return self

    def hflip(self) -> Self:
        """Отражает видео горизонтально (hflip)."""
        self._video_filters.append(hflip_filter())
        return self

    def transpose(self, direction: int | str = 1) -> Self:
        """Поворачивает видео на 90 градусов (transpose)."""
        self._video_filters.append(transpose_filter(direction))
        return self

    def blur(self, radius: float | int = 5) -> Self:
        """Применяет размытие (boxblur)."""
        self._video_filters.append(Filter("boxblur", str(radius)))
        return self

    def sharpen(self, luma_amount: float = 1.0) -> Self:
        """Повышает четкость изображения (unsharp)."""
        self._video_filters.append(
            Filter("unsharp", "5:5:1.0" if luma_amount == 1.0 else f"5:5:{luma_amount}")
        )
        return self

    def drawtext(
        self,
        text: str,
        *,
        x: int | str = 10,
        y: int | str = 10,
        fontsize: int | None = None,
        fontcolor: str | None = None,
        fontfile: str | None = None,
        box: bool = False,
        boxcolor: str | None = None,
    ) -> Self:
        """Накладывает текстовую надпись на видео (drawtext)."""
        self._video_filters.append(
            drawtext(
                text=text,
                x=x,
                y=y,
                fontsize=fontsize,
                fontcolor=fontcolor,
                fontfile=fontfile,
                box=box,
                boxcolor=boxcolor,
            )
        )
        return self

    def watermark(
        self,
        overlay_input: PathLike,
        position: WatermarkPosition = "bottom-right",
        margin: int = 10,
        opacity: float | None = None,
    ) -> Self:
        """Добавляет водяной знак (логотип) поверх видеопотока.

        Args:
            overlay_input: Путь к файлу изображения логотипа (например PNG).
            position: Позиция ('top-left', 'top-right', 'bottom-left', 'bottom-right', 'center').
            margin: Отступ от границ видеокадра в пикселях.
            opacity: Прозрачность логотипа от 0.0 до 1.0 (None = исходная).
        """
        self._watermark = WatermarkConfig(
            target=overlay_input,
            position=position,
            margin=margin,
            opacity=opacity,
        )
        return self

    def video_filter(self, filter_: Filter | FilterChain | str) -> Self:
        """Добавляет пользовательский видеофильтр."""
        if isinstance(filter_, FilterChain):
            self._video_filters.extend(filter_.filters)
        else:
            self._video_filters.append(filter_)
        return self

    # ========================================================================
    # Преобразования аудио
    # ========================================================================

    def volume(self, level: float | str) -> Self:
        """Регулирует громкость звука (volume)."""
        self._audio_filters.append(volume(level))
        return self

    def normalize_audio(
        self,
        target_lufs: float = -14.0,
        target_tp: float = -1.0,
        target_lra: float = 7.0,
    ) -> Self:
        """Нормализует громкость по вещательным стандартам EBU R128 (loudnorm)."""
        self._audio_filters.append(loudnorm(i=target_lufs, tp=target_tp, lra=target_lra))
        return self

    def afade(
        self,
        type: str = "in",  # noqa: A002
        start_time: float = 0.0,
        duration: float = 1.0,
    ) -> Self:
        """Добавляет нарастание или затухание звука (afade)."""
        self._audio_filters.append(afade(type=type, start_time=start_time, duration=duration))
        return self

    def atempo(self, speed: float) -> Self:
        """Изменяет скорость воспроизведения аудио без изменения высоты тона (atempo)."""
        self._audio_filters.append(atempo(speed))
        return self

    def audio_filter(self, filter_: Filter | FilterChain | str) -> Self:
        """Добавляет пользовательский аудиофильтр."""
        if isinstance(filter_, FilterChain):
            self._audio_filters.extend(filter_.filters)
        else:
            self._audio_filters.append(filter_)
        return self

    # ========================================================================
    # Кодеки, битрейты и опции потоков
    # ========================================================================

    def video_codec(
        self,
        codec: str,
        *,
        preset: VideoPreset | str | None = None,
        crf: int | None = None,
        bitrate: str | int | None = None,
    ) -> Self:
        """Задает параметры кодирования видеопотока."""
        self._video_codec = codec
        if preset is not None:
            self._video_preset = preset
        if crf is not None:
            self._video_crf = crf
        if bitrate is not None:
            self._video_bitrate = bitrate
        return self

    def audio_codec(
        self,
        codec: str,
        *,
        bitrate: str | int | None = None,
        sample_rate: int | None = None,
        channels: int | None = None,
    ) -> Self:
        """Задает параметры кодирования аудиопотока."""
        self._audio_codec = codec
        if bitrate is not None:
            self._audio_bitrate = bitrate
        if sample_rate is not None:
            self._audio_sample_rate = sample_rate
        if channels is not None:
            self._audio_channels = channels
        return self

    def copy_video(self) -> Self:
        """Копирует видеопоток без перекодирования (-c:v copy)."""
        self._copy_video = True
        return self

    def copy_audio(self) -> Self:
        """Копирует аудиопоток без перекодирования (-c:a copy)."""
        self._copy_audio = True
        return self

    def copy_all(self) -> Self:
        """Копирует все потоки без перекодирования (-c copy)."""
        self._copy_all = True
        return self

    def preset(self, name: VideoPreset | str) -> Self:
        """Задает пресет кодировщика (-preset)."""
        self._video_preset = name
        return self

    def crf(self, value: int) -> Self:
        """Задает фактор качества (-crf)."""
        self._video_crf = value
        return self

    def bitrate(
        self,
        *,
        video: str | int | None = None,
        audio: str | int | None = None,
    ) -> Self:
        """Устанавливает битрейты видео и аудио."""
        if video is not None:
            self._video_bitrate = video
        if audio is not None:
            self._audio_bitrate = audio
        return self

    def no_video(self) -> Self:
        """Отключает запись видеопотока (-vn)."""
        self._no_video = True
        return self

    def no_audio(self) -> Self:
        """Отключает запись аудиопотока (-an)."""
        self._no_audio = True
        return self

    def no_subtitles(self) -> Self:
        """Отключает запись субтитров (-sn)."""
        self._no_subtitles = True
        return self

    def subtitle_codec(self, codec: str) -> Self:
        """Устанавливает кодек субтитров (-c:s)."""
        self._subtitle_codec = codec
        return self

    def map_stream(self, spec: str) -> Self:
        """Направляет поток в выходной файл (-map)."""
        self._stream_maps.append(spec)
        return self

    def metadata(self, key: str, value: str) -> Self:
        """Добавляет метаданные (-metadata key=value)."""
        self._metadata[key] = value
        return self

    def extra_args(self, *args: str) -> Self:
        """Добавляет сырые аргументы командной строки."""
        self._extra_args.extend(args)
        return self

    def output(
        self,
        target: PathLike,
        format: str | None = None,  # noqa: A002
        **opts: CommandOptionValue,
    ) -> Self:
        """Добавляет выходной файл в конвейер обработки.

        Args:
            target: Путь к целевому файлу для сохранения результата.
            format: Принудительный формат контейнера (флаг -f).
            **opts: Дополнительные опции выходного потока.

        Returns:
            Экземпляр MediaPipeline для цепочечных вызовов.
        """
        out_opts = dict(opts)
        if format is not None:
            out_opts["f"] = format
        self._outputs.append((target, out_opts))
        return self

    # ========================================================================
    # Валидация и компиляция команды
    # ========================================================================

    def validate(self) -> None:
        """Проверяет совместимость и полноту конфигурации конвейера перед запуском."""
        if not self._inputs:
            raise CommandBuildError(
                "MediaPipeline требует указания хотя бы одного входного файла через input()."
            )

        if not self._outputs:
            raise CommandBuildError(
                "MediaPipeline требует указания выходного файла через output()."
            )

        # Конфликты stream copy и фильтров
        if self._copy_all:
            if self._video_filters or self._watermark:
                raise CommandBuildError(
                    "Нельзя использовать copy_all (stream copy) одновременно с фильтрами видео."
                )
            if self._audio_filters:
                raise CommandBuildError(
                    "Нельзя использовать copy_all (stream copy) одновременно с фильтрами аудио."
                )

        if self._copy_video:
            if self._video_filters:
                raise CommandBuildError(
                    "Нельзя одновременно использовать copy_video и фильтры видео."
                )
            if self._watermark:
                raise CommandBuildError(
                    "Нельзя одновременно использовать copy_video и наложение водяного знака."
                )

        if self._copy_audio and self._audio_filters:
            raise CommandBuildError("Нельзя одновременно использовать copy_audio и фильтры аудио.")

        # Конфликты no_video / no_audio
        if self._no_video and (self._video_codec or self._video_filters or self._watermark):
            raise CommandBuildError(
                "Опции видео (кодек, фильтры, водяной знак) заданы вместе с no_video()."
            )

        if self._no_audio and (self._audio_codec or self._audio_filters):
            raise CommandBuildError("Опции аудио (кодек или фильтры) заданы вместе с no_audio().")

    def to_command(self) -> FFmpegCommand:
        """Компилирует цепочку операций конвейера в готовый объект FFmpegCommand."""
        self.validate()

        cmd = FFmpegCommand().overwrite().no_stdin()

        # Аппаратное ускорение
        if self._hwaccel_name is not None:
            cmd.hwaccel(
                self._hwaccel_name,
                device=self._hwaccel_device,
                output_format=self._hwaccel_output_format,
            )

        # 1. Первый вход (основной)
        primary_target, primary_opts = self._inputs[0]
        in_opts = dict(primary_opts)

        if self._fast_seek:
            if self._start is not None:
                in_opts["ss"] = str(self._start)
            if self._duration is not None:
                in_opts["t"] = str(self._duration)
            elif self._end is not None:
                in_opts["to"] = str(self._end)

        cmd.input(primary_target, **in_opts)

        # 2. Дополнительные входы
        for extra_target, extra_opts in self._inputs[1:]:
            cmd.input(extra_target, **extra_opts)

        # 3. Водяной знак как вход (если задан)
        if self._watermark is not None:
            cmd.input(self._watermark.target)

        # Точный поиск (после -i, если не fast_seek)
        if not self._fast_seek:
            if self._start is not None:
                cmd.extra_args("-ss", str(self._start))
            if self._duration is not None:
                cmd.extra_args("-t", str(self._duration))
            elif self._end is not None:
                cmd.extra_args("-to", str(self._end))

        # Построение видеофильтров
        if self._watermark is not None:
            wm = self._watermark
            wm_idx = len(self._inputs)  # Индекс входа логотипа
            chains: list[FilterChain] = []

            base_label = "0:v"
            if self._video_filters:
                base_chain = FilterChain(inputs=["0:v"], outputs=["v_base"])
                for vf in self._video_filters:
                    base_chain.add(vf)
                chains.append(base_chain)
                base_label = "v_base"

            wm_label = f"{wm_idx}:v"
            if wm.opacity is not None:
                chains.append(
                    FilterChain(
                        Filter("format", "rgba"),
                        Filter("colorchannelmixer", aa=str(wm.opacity)),
                        inputs=[f"{wm_idx}:v"],
                        outputs=["wm_ready"],
                    )
                )
                wm_label = "wm_ready"

            ox, oy = _calculate_watermark_xy(wm.position, wm.margin)
            chains.append(
                FilterChain(
                    overlay(x=ox, y=oy),
                    inputs=[base_label, wm_label],
                    outputs=["outv"],
                )
            )

            filter_graph = ComplexFilterGraph(*chains)
            cmd.complex_filter(filter_graph)

            if not self._stream_maps:
                cmd.map_stream("[outv]")
                if not self._no_audio:
                    cmd.map_stream("0:a?")
        else:
            if self._video_filters:
                vf_chain = FilterChain()
                for vf in self._video_filters:
                    vf_chain.add(vf)
                cmd.video_filter(vf_chain)

        # Построение аудиофильтров
        if self._audio_filters and not self._no_audio:
            af_chain = FilterChain()
            for af in self._audio_filters:
                af_chain.add(af)
            cmd.audio_filter(af_chain)

        # Маппинг потоков
        for m in self._stream_maps:
            cmd.map_stream(m)

        # Кодеки видео
        if self._no_video:
            cmd.no_video()
        elif self._copy_all:
            cmd.copy_all()
        elif self._copy_video:
            cmd.copy_video()
        else:
            if self._video_codec is not None:
                cmd.video_codec(self._video_codec)
            if self._video_preset is not None:
                cmd.preset(self._video_preset)
            if self._video_crf is not None:
                cmd.crf(self._video_crf)
            if self._video_bitrate is not None:
                cmd.video_bitrate(self._video_bitrate)

        # Кодеки аудио
        if self._no_audio:
            cmd.no_audio()
        elif not self._copy_all:
            if self._copy_audio:
                cmd.copy_audio()
            else:
                if self._audio_codec is not None:
                    cmd.audio_codec(self._audio_codec)
                if self._audio_bitrate is not None:
                    cmd.audio_bitrate(self._audio_bitrate)
                if self._audio_sample_rate is not None:
                    cmd.output_option("ar", self._audio_sample_rate)
                if self._audio_channels is not None:
                    cmd.output_option("ac", self._audio_channels)

        # Субтитры
        if self._no_subtitles:
            cmd.no_subtitles()
        elif self._subtitle_codec is not None:
            cmd.subtitle_codec(self._subtitle_codec)

        # Метаданные
        for k, v in self._metadata.items():
            cmd.metadata(k, v)

        # Дополнительные аргументы
        if self._extra_args:
            cmd.extra_args(*self._extra_args)

        # Выходы
        for out_path, out_opts in self._outputs:
            cmd.output(out_path, **out_opts)

        return cmd

    def build(self) -> list[str]:
        """Возвращает список аргументов командной строки FFmpeg."""
        return self.to_command().build()

    def build_pretty(self) -> str:
        """Возвращает форматированную строку команды для отладки."""
        return self.to_command().build_pretty()

    def preview(self) -> str:
        """Алиас для build_pretty()."""
        return self.build_pretty()

    # ========================================================================
    # Выполнение
    # ========================================================================

    async def run(
        self,
        *,
        timeout: float | None = None,
        on_progress: ProgressCallback | None = None,
        on_stderr: StderrCallback | None = None,
    ) -> ProcessResult:
        """Выполняет конвейер асинхронно в едином процессе FFmpeg."""
        calc_duration: float | None = None
        if self._duration is not None:
            try:
                calc_duration = float(self._duration)
            except ValueError, TypeError:
                calc_duration = None
        elif self._start is not None and self._end is not None:
            try:
                calc_duration = max(0.0, float(self._end) - float(self._start))
            except ValueError, TypeError:
                calc_duration = None
        elif on_progress is not None and self._inputs:
            # Оцениваем длительность через probe
            first_raw = self._inputs[0][0]
            first_target: PathLike = (
                first_raw.to_ffmpeg_input()
                if isinstance(first_raw, MediaInputProtocol)
                else first_raw
            )
            try:
                if self._client is not None:
                    info = await self._client.probe(first_target)
                else:
                    ffprobe_p = self._ffprobe_path or find_ffprobe()
                    info = await FFprobe(ffprobe_p).probe(first_target)

                if info.duration is not None:
                    dur = info.duration
                    if self._start is not None:
                        with suppress(ValueError, TypeError):
                            dur = max(0.0, dur - float(self._start))
                    calc_duration = dur
            except Exception as exc:
                logger.debug(
                    "Не удалось определить длительность для прогресса через probe: %s", exc
                )
                calc_duration = None

        runner = self._client.runner if self._client is not None else ProcessRunner()
        cmd = self.to_command()

        ffmpeg_bin = (
            self._ffmpeg_path
            or (self._client.ffmpeg_path if self._client is not None else None)
            or find_ffmpeg()
        )

        eff_timeout = timeout
        if eff_timeout is None and self._client is not None:
            eff_timeout = self._client.default_timeout

        logger.debug(
            "MediaPipeline сформировал команду FFmpeg: %s",
            cmd.build(ffmpeg_path=ffmpeg_bin),
        )

        return await cmd.execute(
            ffmpeg_path=ffmpeg_bin,
            process_runner=runner,
            total_duration=calc_duration,
            timeout=eff_timeout,
            on_progress=on_progress,
            on_stderr=on_stderr,
        )

    async def execute(
        self,
        *,
        timeout: float | None = None,
        on_progress: ProgressCallback | None = None,
        on_stderr: StderrCallback | None = None,
    ) -> ProcessResult:
        """Алиас для run()."""
        return await self.run(
            timeout=timeout,
            on_progress=on_progress,
            on_stderr=on_stderr,
        )
