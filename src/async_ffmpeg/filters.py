"""Объектно-ориентированный построитель фильтров (FilterGraph Builder) для FFmpeg.

Поддерживает:
- Одиночные фильтры (Filter) с позиционными и именованными опциями.
- Линейные цепочки фильтров (FilterChain) через запятую `,` с входными/выходными метками.
- Простые графы фильтров (FilterGraph.simple) для параметров `-vf` и `-af`.
- Сложные графы фильтров (ComplexFilterGraph / FilterGraph.complex) для `-filter_complex`.
- Строго типизированные фабричные функции для популярных фильтров аудио и видео.
"""

from collections.abc import Iterable, Sequence
from typing import Any, Self

from async_ffmpeg.exceptions import FilterError


def _normalize_label(label: str) -> str:
    """Удаляет квадратные скобки из метки потока, если они были переданы."""
    clean = label.strip()
    if clean.startswith("[") and clean.endswith("]") and len(clean) >= 2:
        clean = clean[1:-1].strip()
    return clean


def _format_label(label: str) -> str:
    """Оборачивает метку потока в квадратные скобки [label]."""
    clean = _normalize_label(label)
    return f"[{clean}]"


def escape_filter_param(value: Any) -> str:
    """Экранирует значение параметра для использования в синтаксисе фильтра FFmpeg.

    Экранирует символы двоеточия ':', обратного слэша '\\', запятой ',' и одинарных кавычек.
    """
    if isinstance(value, bool):
        return "1" if value else "0"

    str_val = str(value)
    # Если значение уже в одинарных кавычках, сохраняем внутреннее экранирование
    if str_val.startswith("'") and str_val.endswith("'") and len(str_val) >= 2:
        return str_val

    # Символы, требующие экранирования в значениях параметров фильтра
    if any(c in str_val for c in (":", ",", "\\", "'", ";", "[", "]")):
        # Двойной слэш экранирования
        escaped = (
            str_val.replace("\\", "\\\\")
            .replace(":", "\\:")
            .replace(",", "\\,")
            .replace(";", "\\;")
            .replace("'", "\\'")
            .replace("[", "\\[")
            .replace("]", "\\]")
        )
        return f"'{escaped}'"
    return str_val


class Filter:
    """Представляет одиночный фильтр FFmpeg с опциями.

    Примеры:
    ```python
    f = Filter("scale", 1280, 720)  # scale=1280:720
    f = Filter("scale", w=1280, h=720)  # scale=w=1280:h=720
    f = Filter("loudnorm", I=-14.0, LRA=7.0, tp=-1.0)  # loudnorm=I=-14.0:LRA=7.0:tp=-1.0
    f = Filter("vflip")  # vflip
    ```
    """

    def __init__(self, name: str, *args: Any, **kwargs: Any) -> None:
        clean_name = name.strip()
        if not clean_name:
            raise FilterError(name, "Имя фильтра не может быть пустым.")
        self._name = clean_name
        self._args: tuple[str, ...] = tuple(str(a) for a in args)
        self._kwargs: dict[str, str] = {str(k): str(v) for k, v in kwargs.items() if v is not None}

    @property
    def name(self) -> str:
        """Название фильтра FFmpeg."""
        return self._name

    @property
    def args(self) -> tuple[str, ...]:
        """Позиционные аргументы фильтра."""
        return self._args

    @property
    def kwargs(self) -> dict[str, str]:
        """Именованные параметры фильтра."""
        return self._kwargs

    def with_options(self, *args: Any, **kwargs: Any) -> Self:
        """Возвращает новый фильтр с дополненными опциями."""
        new_args = self._args + tuple(str(a) for a in args)
        new_kwargs = dict(self._kwargs)
        for k, v in kwargs.items():
            if v is not None:
                new_kwargs[str(k)] = str(v)
        return self.__class__(self._name, *new_args, **new_kwargs)

    def __str__(self) -> str:
        """Сериализует фильтр в канонический синтаксис FFmpeg."""
        parts: list[str] = list(self._args)
        for k, v in self._kwargs.items():
            parts.append(f"{k}={v}")

        if not parts:
            return self._name
        return f"{self._name}={':'.join(parts)}"

    def __repr__(self) -> str:
        return f"Filter({self._name!r}, str={str(self)!r})"


class FilterChain:
    """Линейная цепочка фильтров, выполняемых последовательно через запятую `,`.

    Может иметь входные метки потоков (например, `[0:v]`) и выходные метки (например, `[scaled]`).
    Пример: `[0:v]scale=1280:720,fps=30[out]`
    """

    def __init__(
        self,
        *filters: Filter | str,
        inputs: Sequence[str] | str | None = None,
        outputs: Sequence[str] | str | None = None,
    ) -> None:
        self._filters: list[Filter] = []
        for f in filters:
            if isinstance(f, Filter):
                self._filters.append(f)
            elif isinstance(f, str):
                clean = f.strip()
                if clean:
                    self._filters.append(Filter(clean))

        self._inputs: list[str] = []
        if isinstance(inputs, str):
            self._inputs.append(_normalize_label(inputs))
        elif isinstance(inputs, Iterable):
            for inp in inputs:
                self._inputs.append(_normalize_label(inp))

        self._outputs: list[str] = []
        if isinstance(outputs, str):
            self._outputs.append(_normalize_label(outputs))
        elif isinstance(outputs, Iterable):
            for out in outputs:
                self._outputs.append(_normalize_label(out))

    @property
    def filters(self) -> list[Filter]:
        """Список фильтров в цепочке."""
        return self._filters

    @property
    def inputs(self) -> list[str]:
        """Входные метки потоков (без скобок)."""
        return self._inputs

    @property
    def outputs(self) -> list[str]:
        """Выходные метки потоков (без скобок)."""
        return self._outputs

    def add(self, filter_: Filter | str) -> Self:
        """Добавляет фильтр в конец цепочки."""
        if isinstance(filter_, Filter):
            self._filters.append(filter_)
        elif isinstance(filter_, str):
            clean = filter_.strip()
            if clean:
                self._filters.append(Filter(clean))
        return self

    def chain(self, *filters: Filter | str) -> Self:
        """Добавляет несколько фильтров в цепочку."""
        for f in filters:
            self.add(f)
        return self

    def with_inputs(self, *inputs: str) -> Self:
        """Устанавливает входные метки потоков."""
        self._inputs = [_normalize_label(i) for i in inputs]
        return self

    def with_outputs(self, *outputs: str) -> Self:
        """Устанавливает выходные метки потоков."""
        self._outputs = [_normalize_label(o) for o in outputs]
        return self

    def __str__(self) -> str:
        """Сериализует цепочку фильтров в формат FFmpeg."""
        if not self._filters:
            raise FilterError(
                "",
                "Цепочка фильтров FilterChain не может быть пустой при сериализации.",
            )

        in_str = "".join(_format_label(i) for i in self._inputs)
        filters_str = ",".join(str(f) for f in self._filters)
        out_str = "".join(_format_label(o) for o in self._outputs)
        return f"{in_str}{filters_str}{out_str}"

    def __repr__(self) -> str:
        return f"FilterChain({str(self)!r})"


class FilterGraph:
    """Базовый граф фильтров, состоящий из одной или нескольких цепочек FilterChain."""

    def __init__(self, *chains: FilterChain) -> None:
        self._chains: list[FilterChain] = list(chains)

    @property
    def chains(self) -> list[FilterChain]:
        """Список цепочек фильтров в графе."""
        return self._chains

    @classmethod
    def simple(cls, *filters: Filter | str | FilterChain) -> FilterGraph:
        """Создает простой линейный граф фильтров для `-vf` или `-af`.

        Принимает фильтры или готовую цепочку. Соединяет их через запятую.
        """
        chain = FilterChain()
        for item in filters:
            if isinstance(item, FilterChain):
                for f in item.filters:
                    chain.add(f)
            else:
                chain.add(item)
        return cls(chain)

    @classmethod
    def complex(cls) -> ComplexFilterGraph:
        """Создает сложный граф фильтров для параметра `-filter_complex`."""
        return ComplexFilterGraph()

    def add_chain(self, chain: FilterChain) -> Self:
        """Добавляет цепочку фильтров в граф."""
        self._chains.append(chain)
        return self

    def __str__(self) -> str:
        """Сериализует граф в строку FFmpeg, объединяя цепочки через точку с запятой `;`."""
        if not self._chains:
            return ""
        return ";".join(str(chain) for chain in self._chains)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({str(self)!r})"


class ComplexFilterGraph(FilterGraph):
    """Сложный граф фильтров для флага `-filter_complex`.

    Обеспечивает удобное fluent-построение разветвленных графов фильтрации.
    """

    def chain(
        self,
        inputs: Sequence[str] | str = (),
        filters: Sequence[Filter | str] | Filter | str = (),
        outputs: Sequence[str] | str = (),
    ) -> Self:
        """Добавляет новую связанную цепочку фильтров в сложный граф.

        Args:
            inputs: Одна метка или последовательность входных меток потоков (например, "0:v" или ["0:v", "1:v"]).
            filters: Один фильтр или последовательность фильтров (Filter или str).
            outputs: Одна метка или последовательность выходных меток (например, "scaled" или ["v1", "v2"]).
        """
        filter_list: list[Filter | str] = []
        if isinstance(filters, Filter | str):
            filter_list.append(filters)
        elif isinstance(filters, Iterable):
            filter_list.extend(filters)

        input_seq: Sequence[str] = (
            ([inputs] if inputs.strip() else []) if isinstance(inputs, str) else inputs
        )

        output_seq: Sequence[str] = (
            ([outputs] if outputs.strip() else []) if isinstance(outputs, str) else outputs
        )

        chain_obj = FilterChain(*filter_list, inputs=input_seq, outputs=output_seq)
        self.add_chain(chain_obj)
        return self


# ============================================================================
# Фабричные функции для частых видео-фильтров
# ============================================================================


def scale(
    width: int | str = -1,
    height: int | str = -1,
    *,
    force_original_aspect_ratio: str | None = None,
    flags: str | None = None,
    eval_mode: str | None = None,
) -> Filter:
    """Фильтр изменения масштаба видео (scale).

    Args:
        width: Ширина (число или выражение, e.g. 1280, -1, "iw*2").
        height: Высота (число или выражение, e.g. 720, -2).
        force_original_aspect_ratio: 'decrease' или 'increase' для сохранения пропорций.
        flags: Алгоритм масштабирования (e.g. 'bicubic', 'lanczos').
        eval_mode: Время вычисления выражений ('init' или 'frame').
    """
    kwargs: dict[str, Any] = {}
    if force_original_aspect_ratio is not None:
        kwargs["force_original_aspect_ratio"] = force_original_aspect_ratio
    if flags is not None:
        kwargs["flags"] = flags
    if eval_mode is not None:
        kwargs["eval"] = eval_mode

    return Filter("scale", str(width), str(height), **kwargs)


def fps(rate: int | float | str) -> Filter:
    """Фильтр изменения частоты кадров (fps)."""
    return Filter("fps", rate)


def crop(
    w: int | str,
    h: int | str,
    x: int | str = 0,
    y: int | str = 0,
) -> Filter:
    """Фильтр кадрирования видео (crop).

    crop=w:h:x:y
    """
    return Filter("crop", str(w), str(h), str(x), str(y))


def pad(
    w: int | str,
    h: int | str,
    x: int | str = 0,
    y: int | str = 0,
    color: str = "black",
) -> Filter:
    """Фильтр добавления полей/паддинга к видео (pad).

    pad=w:h:x:y:color
    """
    return Filter("pad", str(w), str(h), str(x), str(y), color)


def rotate(angle: float | str, fillcolor: str = "black") -> Filter:
    """Фильтр поворота видео на произвольный угол в радианах (rotate)."""
    return Filter("rotate", str(angle), fillcolor=fillcolor)


def vflip() -> Filter:
    """Фильтр вертикального зеркального отражения видео (vflip)."""
    return Filter("vflip")


def hflip() -> Filter:
    """Фильтр горизонтального зеркального отражения видео (hflip)."""
    return Filter("hflip")


def transpose(direction: int | str = 1) -> Filter:
    """Фильтр транспонирования/поворота видео на 90 градусов (transpose).

    0 = 90 против часовой стрелки и вертикальный flip
    1 = 90 по часовой стрелке
    2 = 90 против часовой стрелки
    3 = 90 по часовой стрелке и вертикальный flip
    """
    return Filter("transpose", str(direction))


def video_format(pix_fmts: str = "yuv420p") -> Filter:
    """Фильтр выбора пиксельного формата (format)."""
    return Filter("format", pix_fmts)


# Алиас для format
format = video_format  # noqa: A001


def setpts(expr: str = "PTS-STARTPTS") -> Filter:
    """Фильтр модификации временных меток видеокадров (setpts)."""
    return Filter("setpts", expr)


def vtrim(
    start: float | None = None,
    end: float | None = None,
    duration: float | None = None,
) -> Filter:
    """Фильтр обрезки видеопотока (trim)."""
    kwargs: dict[str, Any] = {}
    if start is not None:
        kwargs["start"] = start
    if end is not None:
        kwargs["end"] = end
    if duration is not None:
        kwargs["duration"] = duration
    return Filter("trim", **kwargs)


def overlay(
    x: int | str = 0,
    y: int | str = 0,
    *,
    eof_action: str = "repeat",
    shortest: bool = False,
    format: str | None = None,  # noqa: A002
) -> Filter:
    """Фильтр наложения видеопотоков друг на друга (overlay).

    Args:
        x: Координата X верхнего левого угла накладываемого слоя.
        y: Координата Y верхнего левого угла накладываемого слоя.
        eof_action: Действие при завершении второго потока ('repeat', 'endall', 'pass').
        shortest: Завершать вывод при окончании кратчайшего входного потока.
        format: Цветовое пространство оверлея (e.g. 'yuv420', 'rgb').
    """
    kwargs: dict[str, Any] = {
        "eof_action": eof_action,
    }
    if shortest:
        kwargs["shortest"] = 1
    if format is not None:
        kwargs["format"] = format
    return Filter("overlay", str(x), str(y), **kwargs)


def drawtext(
    text: str,
    *,
    x: int | str = 10,
    y: int | str = 10,
    fontsize: int | None = None,
    fontcolor: str | None = None,
    fontfile: str | None = None,
    box: bool = False,
    boxcolor: str | None = None,
) -> Filter:
    """Фильтр наложения текста на видео (drawtext)."""
    clean_text = text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
    kwargs: dict[str, Any] = {
        "text": f"'{clean_text}'",
        "x": str(x),
        "y": str(y),
    }
    if fontsize is not None:
        kwargs["fontsize"] = fontsize
    if fontcolor is not None:
        kwargs["fontcolor"] = fontcolor
    if fontfile is not None:
        kwargs["fontfile"] = fontfile
    if box:
        kwargs["box"] = 1
        if boxcolor:
            kwargs["boxcolor"] = boxcolor

    return Filter("drawtext", **kwargs)


# ============================================================================
# Фабричные функции для частых аудио-фильтров
# ============================================================================


def volume(volume: float | str, *, precision: str | None = None) -> Filter:
    """Фильтр изменения громкости аудио (volume).

    Примеры:
    - `volume(1.5)` — увеличение громкости в 1.5 раза
    - `volume("6dB")` — усиление на +6 дБ
    - `volume(0.5)` — уменьшение громкости в 2 раза
    """
    kwargs: dict[str, Any] = {}
    if precision is not None:
        kwargs["precision"] = precision
    return Filter("volume", str(volume), **kwargs)


def atempo(speed: float) -> Filter:
    """Фильтр изменения скорости воспроизведения аудио без изменения высоты тона (atempo).

    FFmpeg поддерживает значения от 0.5 до 2.0 на один фильтр atempo.
    """
    return Filter("atempo", str(speed))


def afade(
    type: str = "in",  # noqa: A002
    *,
    start_time: float | None = None,
    duration: float | None = None,
    curve: str | None = None,
) -> Filter:
    """Фильтр плавного нарастания (fade-in) или затухания (fade-out) аудио (afade).

    Args:
        type: 'in' для нарастания, 'out' для затухания.
        start_time: Время старта эффекта в секундах.
        duration: Длительность эффекта в секундах.
        curve: Тип кривой затухания (e.g. 'tri', 'qsin', 'esin', 'log').
    """
    kwargs: dict[str, Any] = {"t": type}
    if start_time is not None:
        kwargs["st"] = start_time
    if duration is not None:
        kwargs["d"] = duration
    if curve is not None:
        kwargs["curve"] = curve
    return Filter("afade", **kwargs)


def loudnorm(
    i: float = -14.0,
    lra: float = 7.0,
    tp: float = -1.0,
    dual_mono: bool = False,
) -> Filter:
    """Фильтр нормализации громкости по стандартам EBU R128 / ITU-R BS.1770 (loudnorm).

    Args:
        i: Интегрированная громкость (Integrated Loudness Target, LUFS). По умолчанию -14 LUFS.
        lra: Диапазон громкости (Loudness Range Target, LU). По умолчанию 7 LU.
        tp: Максимальный истинный пик (Maximum True Peak, dBFS). По умолчанию -1.0 dBFS.
        dual_mono: Обрабатывать стерео как два моно-канала.
    """
    kwargs: dict[str, Any] = {
        "I": str(i),
        "LRA": str(lra),
        "tp": str(tp),
        "dual_mono": "true" if dual_mono else "false",
    }
    return Filter("loudnorm", **kwargs)


def anull() -> Filter:
    """Аудио-фильтр null (сквозной пропуск аудио без изменений)."""
    return Filter("anull")


def amix(
    inputs: int = 2,
    *,
    duration: str = "longest",
    dropout_transition: float = 2.0,
) -> Filter:
    """Фильтр микширования нескольких аудиопотоков (amix).

    Args:
        inputs: Количество входных аудиопотоков.
        duration: Стратегия завершения ('longest', 'shortest', 'first').
        dropout_transition: Время плавного затухания канала при завершении.
    """
    return Filter(
        "amix",
        inputs=inputs,
        duration=duration,
        dropout_transition=dropout_transition,
    )


def atrim(
    start: float | None = None,
    end: float | None = None,
    duration: float | None = None,
) -> Filter:
    """Фильтр обрезки аудиопотока (atrim)."""
    kwargs: dict[str, Any] = {}
    if start is not None:
        kwargs["start"] = start
    if end is not None:
        kwargs["end"] = end
    if duration is not None:
        kwargs["duration"] = duration
    return Filter("atrim", **kwargs)


def asetpts(expr: str = "PTS-STARTPTS") -> Filter:
    """Фильтр сброса временных меток аудио (asetpts)."""
    return Filter("asetpts", expr)


def aresample(sample_rate: int) -> Filter:
    """Фильтр изменения частоты дискретизации аудио (aresample)."""
    return Filter("aresample", str(sample_rate))


def pan(layout: str, *matrix: str) -> Filter:
    """Фильтр маршрутизации аудиоканалов (pan).

    Пример: `pan("stereo", "c0=c0", "c1=c1")`
    """
    return Filter("pan", layout, *matrix)


# ============================================================================
# Утилитные фильтры
# ============================================================================


def concat(n: int = 2, v: int = 1, a: int = 1) -> Filter:
    """Фильтр конкатенации медиапотоков (concat).

    Args:
        n: Количество соединяемых сегментов.
        v: Количество видеопотоков в каждом сегменте.
        a: Количество аудиопотоков в каждом сегменте.
    """
    return Filter("concat", n=n, v=v, a=a)


def split(outputs: int = 2) -> Filter:
    """Фильтр размножения видеопотока на несколько выходов (split)."""
    return Filter("split", str(outputs))


def asplit(outputs: int = 2) -> Filter:
    """Фильтр размножения аудиопотока на несколько выходов (asplit)."""
    return Filter("asplit", str(outputs))
