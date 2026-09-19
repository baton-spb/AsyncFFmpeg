# Архитектура async-ffmpeg

> **Дата:** 2026-09-19
> **Python:** >= 3.14
> **Зависимости:** только stdlib (asyncio, dataclasses, json, pathlib, shutil, enum, typing)

---

## 1. Обзор модулей

```
async_ffmpeg/
├── __init__.py              # Публичный API, re-exports
├── py.typed                 # PEP 561 маркер
├── _constants.py            # Константы (таймауты, пути)
├── _types.py                # TypeAliases, Literal types, protocols
│
├── exceptions.py            # Иерархия исключений
├── models.py                # Pydantic-free dataclass модели
│
├── process.py               # ProcessRunner — управление subprocess
├── progress.py              # Парсинг прогресса из -progress pipe:1
│
├── command.py               # FFmpegCommand builder (low-level)
├── probe.py                 # FFprobe клиент
│
├── filters.py               # FilterGraph builder
├── pipeline.py              # MediaPipeline — цепочка операций
│
├── client.py                # FFmpegClient — high-level API
├── hardware.py              # HW-ускорение: discovery + конфигурация
│
├── _discovery.py            # Поиск ffmpeg/ffprobe бинарников
└── _compat.py               # OS-specific код (Windows/Unix)
```

---

## 2. Слои архитектуры

```
┌────────────────────────────────────────────────┐
│              FFmpegClient (high-level)          │  client.py
│  transcode(), extract_audio(), concat(), ...    │
├────────────────────────────────────────────────┤
│              MediaPipeline                      │  pipeline.py
│  chain().scale().normalize().encode()            │
├────────────────────────────────────────────────┤
│         FFmpegCommand (builder)                 │  command.py
│  .global_opt().input().filter().output()        │
├────────────────────────────────────────────────┤
│         FilterGraph                             │  filters.py
│  Simple & Complex filtergraph builders          │
├────────────────────────────────────────────────┤
│         ProcessRunner                           │  process.py
│  asyncio.create_subprocess_exec() wrapper       │
│  + ProgressParser (progress.py)                 │
├────────────────────────────────────────────────┤
│         FFprobe                                 │  probe.py
│  Typed JSON models for media info               │
├────────────────────────────────────────────────┤
│         Hardware                                │  hardware.py
│  HW accel discovery + codec selection           │
└────────────────────────────────────────────────┘
```

---

## 3. Ключевые компоненты

### 3.1 ProcessRunner (process.py)

**Ответственность:** Управление жизненным циклом subprocess FFmpeg/FFprobe.

**Ключевые решения:**
- `asyncio.create_subprocess_exec()` — всегда, без shell=True
- `stdin=PIPE` — для graceful shutdown через 'q'
- `stdout=PIPE` — для прогресса (-progress pipe:1) или ffprobe JSON
- `stderr=PIPE` — для логирования ошибок
- Параллельное чтение stdout/stderr через asyncio.Task
- Graceful shutdown: `stdin.write(b'q')` → wait → kill (таймаут)
- OS-specific: на Unix `start_new_session=True`, на Windows — `creationflags`

```python
@dataclass(frozen=True, slots=True)
class ProcessResult:
    """Результат выполнения FFmpeg/FFprobe процесса."""

    exit_code: int
    stdout: bytes
    stderr: bytes
    duration_seconds: float


class ProcessRunner:
    """Асинхронный runner для FFmpeg/FFprobe процессов."""

    async def run(
        self,
        args: Sequence[str],
        *,
        timeout: float | None = None,
        on_progress: ProgressCallback | None = None,
        on_stderr: StderrCallback | None = None,
    ) -> ProcessResult: ...

    async def cancel(self) -> None:
        """Грациозное завершение: 'q' → wait → kill."""
        ...
```

### 3.2 ProgressParser (progress.py)

**Ответственность:** Парсинг key=value блоков из stdout FFmpeg.

```python
@dataclass(frozen=True, slots=True)
class ProgressInfo:
    """Один блок прогресса от FFmpeg."""

    frame: int | None  # None для audio-only
    fps: float
    bitrate: str  # Может быть "N/A"
    total_size: int | None  # None если "N/A"
    out_time_us: int  # Микросекунды
    out_time: str  # "HH:MM:SS.ffffff"
    speed: str  # e.g. "2.32x"
    dup_frames: int
    drop_frames: int
    is_finished: bool  # True если progress=end

    @property
    def percent(self) -> float | None:
        """Процент завершения (требуется total_duration_us)."""
        ...


# Type alias для callback
ProgressCallback = Callable[[ProgressInfo], None] | Callable[[ProgressInfo], Awaitable[None]]
```

### 3.3 FFmpegCommand (command.py)

**Ответственность:** Type-safe конструктор командной строки FFmpeg.

**КРИТИЧНО:** Соблюдение порядка аргументов FFmpeg.

```python
class FFmpegCommand:
    """Immutable builder для FFmpeg CLI-команд."""

    def global_option(self, key: str, value: str | None = None) -> Self: ...
    def input(self, path: str | Path, **opts: str) -> Self: ...
    def output(self, path: str | Path, **opts: str) -> Self: ...
    def video_codec(self, codec: str, stream: str | None = None) -> Self: ...
    def audio_codec(self, codec: str, stream: str | None = None) -> Self: ...
    def video_filter(self, filtergraph: str | FilterGraph) -> Self: ...
    def audio_filter(self, filtergraph: str | FilterGraph) -> Self: ...
    def complex_filter(self, filtergraph: str | FilterGraph) -> Self: ...
    def map_stream(self, spec: str) -> Self: ...
    def metadata(self, key: str, value: str) -> Self: ...
    def overwrite(self, yes: bool = True) -> Self: ...
    def no_stdin(self) -> Self: ...

    def build(self) -> list[str]:
        """Собрать финальную командную строку."""
        ...

    async def execute(
        self,
        *,
        timeout: float | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> ProcessResult: ...
```

### 3.4 FFprobe (probe.py)

**Ответственность:** Типизированный клиент для ffprobe.

```python
@dataclass(frozen=True, slots=True)
class VideoStream:
    index: int
    codec_name: str
    codec_long_name: str
    profile: str | None
    width: int
    height: int
    pix_fmt: str
    frame_rate: float  # Вычисляется из r_frame_rate "30/1"
    duration: float | None  # В секундах
    bit_rate: int | None
    nb_frames: int | None
    # ...


@dataclass(frozen=True, slots=True)
class AudioStream:
    index: int
    codec_name: str
    codec_long_name: str
    profile: str | None
    sample_rate: int
    channels: int
    channel_layout: str | None
    duration: float | None
    bit_rate: int | None
    # ...


@dataclass(frozen=True, slots=True)
class SubtitleStream:
    index: int
    codec_name: str
    codec_long_name: str
    # ...


@dataclass(frozen=True, slots=True)
class MediaFormat:
    filename: str
    nb_streams: int
    format_name: str
    format_long_name: str
    duration: float | None
    size: int | None
    bit_rate: int | None
    tags: dict[str, str]


@dataclass(frozen=True, slots=True)
class MediaInfo:
    format: MediaFormat
    video_streams: tuple[VideoStream, ...]
    audio_streams: tuple[AudioStream, ...]
    subtitle_streams: tuple[SubtitleStream, ...]
    chapters: tuple[Chapter, ...]

    @property
    def has_video(self) -> bool: ...
    @property
    def has_audio(self) -> bool: ...
    @property
    def duration(self) -> float | None: ...
    @property
    def primary_video(self) -> VideoStream | None: ...
    @property
    def primary_audio(self) -> AudioStream | None: ...


class FFprobe:
    """Асинхронный клиент FFprobe."""

    async def probe(self, path: str | Path) -> MediaInfo: ...
    async def get_duration(self, path: str | Path) -> float | None: ...
    async def get_streams(self, path: str | Path, *, stream_type: str | None = None) -> ...: ...
```

### 3.5 FilterGraph (filters.py)

```python
class Filter:
    """Один фильтр в цепочке."""

    def __init__(self, name: str, **kwargs: str | int | float): ...


class FilterChain:
    """Цепочка фильтров (разделитель ',')."""

    def append(self, filter: Filter) -> Self: ...


class FilterGraph:
    """Simple или Complex filtergraph."""

    # Simple: -vf "scale=1280:720,fps=30"
    @classmethod
    def simple(cls, *filters: Filter) -> Self: ...

    # Complex: -filter_complex "[0:v]scale=...[out]"
    @classmethod
    def complex(cls) -> ComplexFilterGraph: ...


class ComplexFilterGraph(FilterGraph):
    """Complex filtergraph с метками потоков."""

    def chain(self, inputs: list[str], filters: list[Filter], outputs: list[str]) -> Self: ...
```

### 3.6 FFmpegClient (client.py)

**High-level API — то, что используют 95% пользователей:**

```python
class FFmpegClient:
    """Высокоуровневый асинхронный клиент FFmpeg."""

    def __init__(
        self,
        ffmpeg_path: str | Path | None = None,
        ffprobe_path: str | Path | None = None,
        *,
        max_concurrent: int = 4,
        default_timeout: float | None = None,
    ): ...

    # Анализ
    async def probe(self, path: str | Path) -> MediaInfo: ...

    # Транскодирование
    async def transcode(
        self,
        input: str | Path,
        output: str | Path,
        *,
        video_codec: str | None = None,
        audio_codec: str | None = None,
        video_bitrate: str | None = None,
        audio_bitrate: str | None = None,
        resolution: tuple[int, int] | None = None,
        fps: float | None = None,
        preset: str | None = None,
        crf: int | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> ProcessResult: ...

    # Извлечение аудио
    async def extract_audio(
        self,
        input: str | Path,
        output: str | Path,
        *,
        codec: str = "aac",
        bitrate: str = "128k",
        on_progress: ProgressCallback | None = None,
    ) -> ProcessResult: ...

    # Конкатенация
    async def concat(
        self,
        inputs: Sequence[str | Path],
        output: str | Path,
        *,
        method: Literal["demuxer", "filter", "protocol"] = "demuxer",
        on_progress: ProgressCallback | None = None,
    ) -> ProcessResult: ...

    # Обрезка
    async def trim(
        self,
        input: str | Path,
        output: str | Path,
        *,
        start: float | str | None = None,
        end: float | str | None = None,
        duration: float | str | None = None,
        copy: bool = True,
        on_progress: ProgressCallback | None = None,
    ) -> ProcessResult: ...

    # Скриншот / извлечение кадра
    async def screenshot(
        self,
        input: str | Path,
        output: str | Path,
        *,
        timestamp: float | str = 0,
        resolution: tuple[int, int] | None = None,
    ) -> ProcessResult: ...

    # Генерация thumbnails
    async def thumbnails(
        self,
        input: str | Path,
        output_pattern: str | Path,
        *,
        interval: float = 10.0,
        resolution: tuple[int, int] | None = None,
    ) -> ProcessResult: ...

    # Конвертация формата
    async def convert(
        self,
        input: str | Path,
        output: str | Path,
        *,
        copy: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> ProcessResult: ...

    # Нормализация аудио
    async def normalize_audio(
        self,
        input: str | Path,
        output: str | Path,
        *,
        target_lufs: float = -14.0,
        on_progress: ProgressCallback | None = None,
    ) -> ProcessResult: ...
```

### 3.7 Hardware (hardware.py)

```python
@dataclass(frozen=True, slots=True)
class HWAccelInfo:
    """Информация о доступном HW-ускорителе."""

    name: str  # e.g. "cuda", "qsv", "amf"
    encoders: tuple[str, ...]  # e.g. ("h264_nvenc", "hevc_nvenc")
    decoders: tuple[str, ...]  # e.g. ("h264_cuvid", "hevc_cuvid")


class HardwareAccel:
    """Обнаружение и конфигурация HW-ускорения."""

    async def detect(self) -> tuple[HWAccelInfo, ...]:
        """Обнаружить все доступные HW-ускорители."""
        ...

    async def best_encoder(
        self,
        codec: str,
        *,
        prefer_hw: bool = True,
    ) -> str:
        """Выбрать лучший кодировщик для кодека."""
        ...
```

---

## 4. Обработка ошибок

### 4.1 Иерархия исключений

```python
class AsyncFFmpegError(Exception):
    """Базовое исключение async-ffmpeg."""


class FFmpegNotFoundError(AsyncFFmpegError):
    """FFmpeg/FFprobe не найден в системе."""


class FFmpegProcessError(AsyncFFmpegError):
    """Процесс FFmpeg завершился с ошибкой."""

    exit_code: int
    stderr: str
    command: list[str]


class FFmpegTimeoutError(AsyncFFmpegError):
    """Таймаут выполнения FFmpeg."""


class FFmpegCancelledError(AsyncFFmpegError):
    """Операция была отменена."""


class FFprobeError(AsyncFFmpegError):
    """Ошибка FFprobe."""


class InvalidInputError(AsyncFFmpegError):
    """Невалидный входной файл."""


class CodecNotFoundError(AsyncFFmpegError):
    """Запрошенный кодек недоступен."""


class FilterError(AsyncFFmpegError):
    """Ошибка в filtergraph."""


class CommandBuildError(AsyncFFmpegError):
    """Ошибка построения команды."""
```

---

## 5. Модели данных

### 5.1 Принципы

- Все модели — `@dataclass(frozen=True, slots=True)`
- Immutable по умолчанию
- Tuple вместо List для коллекций
- `None` вместо sentinel values
- Все числовые поля — уже распарсенные из строк FFprobe

### 5.2 Конвертация из JSON FFprobe

```python
# FFprobe возвращает строки для числовых полей:
# "duration": "2.000000" → float
# "bit_rate": "8724" → int
# "sample_rate": "44100" → int
# "nb_frames": "60" → int
# "r_frame_rate": "30/1" → float (вычисляем 30.0)
```

---

## 6. Конфигурация и Discovery

### 6.1 Поиск бинарников

Порядок поиска FFmpeg/FFprobe:
1. Явно указанный путь (аргумент конструктора)
2. Переменная окружения `FFMPEG_PATH` / `FFPROBE_PATH`
3. `shutil.which('ffmpeg')` / `shutil.which('ffprobe')` — PATH
4. Платформо-специфичные fallback:
   - Windows: WinGet, Scoop, Chocolatey стандартные пути
   - macOS: Homebrew (`/opt/homebrew/bin/`)
   - Linux: `/usr/bin/`, `/usr/local/bin/`

### 6.2 Валидация версии

```python
async def get_version() -> str:
    """Получить версию FFmpeg."""
    result = await run_process(["ffmpeg", "-version"])
    # Parse "ffmpeg version 9.0.1-full_build..."
    return version_string
```

---

## 7. Thread Safety и Concurrency

- Каждая операция создаёт новый subprocess — нет shared state
- `asyncio.Semaphore` для ограничения concurrent процессов
- Все модели immutable — thread-safe по определению
- ProcessRunner — одноразовый (один run per instance)
- FFmpegClient — многоразовый, потокобезопасный
