# API Design — async-ffmpeg

> **Дата:** 2026-09-19
> **Версия:** 0.1.0-alpha
> **Python:** >= 3.14

---

## 1. Философия API

### 1.1 Принципы

1. **Два уровня API** — Low-level builder (`FFmpegCommand`) для полного контроля, High-level (`FFmpegClient`) для типичных задач
2. **Immutable by default** — все модели frozen dataclass, builder возвращает Self
3. **Progress first-class** — любая операция поддерживает callback прогресса
4. **Explicit is better** — никакой магии, все аргументы именованные
5. **Fail fast** — валидация команд до запуска процесса
6. **Zero runtime deps** — только stdlib Python 3.14+

### 1.2 Именование

- Модули и переменные: `snake_case`
- Классы: `PascalCase`
- Константы: `UPPER_SNAKE_CASE`
- Все публичные имена — англоязычные
- Все docstrings и комментарии — на русском

---

## 2. Быстрый старт (Quick Start)

### 2.1 Простейший пример

```python
import asyncio
from async_ffmpeg import FFmpegClient

async def main():
    client = FFmpegClient()

    # Анализ файла
    info = await client.probe("input.mp4")
    print(f"Длительность: {info.duration}s")
    print(f"Видео: {info.primary_video.codec_name} {info.primary_video.width}x{info.primary_video.height}")

    # Транскодирование с прогрессом
    async def on_progress(p):
        print(f"Прогресс: {p.out_time} | Скорость: {p.speed}")

    await client.transcode(
        "input.mp4", "output.mp4",
        video_codec="libx264",
        crf=23,
        resolution=(1280, 720),
        on_progress=on_progress,
    )

asyncio.run(main())
```

### 2.2 Low-level builder

```python
from async_ffmpeg import FFmpegCommand

cmd = (
    FFmpegCommand()
    .overwrite()
    .no_stdin()
    .input("input.mp4", ss="10", t="30")
    .video_codec("libx264")
    .audio_codec("aac")
    .video_filter("scale=1280:720")
    .output("output.mp4", preset="medium", crf="23")
)

# Посмотреть что получилось
print(cmd.build())
# ['ffmpeg', '-y', '-nostdin', '-ss', '10', '-t', '30', '-i', 'input.mp4',
#  '-vf', 'scale=1280:720', '-c:v', 'libx264', '-c:a', 'aac',
#  '-preset', 'medium', '-crf', '23', 'output.mp4']

result = await cmd.execute()
```

### 2.3 Прогресс с процентом

```python
from async_ffmpeg import FFmpegClient, ProgressInfo

client = FFmpegClient()

# Получаем длительность
info = await client.probe("input.mp4")
total_us = int(info.duration * 1_000_000)

async def on_progress(p: ProgressInfo):
    if total_us > 0:
        percent = (p.out_time_us / total_us) * 100
        print(f"{percent:.1f}% | {p.speed}")

await client.transcode("input.mp4", "output.mp4", on_progress=on_progress)
```

---

## 3. FFmpegClient API

### 3.1 Конструктор

```python
class FFmpegClient:
    def __init__(
        self,
        ffmpeg_path: str | Path | None = None,
        ffprobe_path: str | Path | None = None,
        *,
        max_concurrent: int = 4,
        default_timeout: float | None = None,
        temp_dir: str | Path | None = None,
    ) -> None: ...
```

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `ffmpeg_path` | str/Path/None | None | Путь к ffmpeg (автопоиск если None) |
| `ffprobe_path` | str/Path/None | None | Путь к ffprobe (автопоиск если None) |
| `max_concurrent` | int | 4 | Макс. параллельных процессов |
| `default_timeout` | float/None | None | Таймаут по умолчанию (сек) |
| `temp_dir` | str/Path/None | None | Директория для временных файлов |

### 3.2 Основные операции

#### probe() — Анализ медиафайла

```python
async def probe(
    self,
    path: str | Path,
    *,
    timeout: float | None = None,
) -> MediaInfo: ...
```

#### transcode() — Транскодирование

```python
async def transcode(
    self,
    input: str | Path,
    output: str | Path,
    *,
    video_codec: str | None = None,       # "libx264", "libx265", "copy"
    audio_codec: str | None = None,       # "aac", "libopus", "copy"
    video_bitrate: str | None = None,     # "5M", "2500k"
    audio_bitrate: str | None = None,     # "128k", "192k"
    resolution: tuple[int, int] | None = None,  # (1280, 720)
    fps: float | None = None,             # 30.0
    preset: str | None = None,            # "ultrafast"..."veryslow"
    crf: int | None = None,               # 0-51 для x264
    pixel_format: str | None = None,      # "yuv420p"
    video_filters: str | None = None,     # "scale=1280:720"
    audio_filters: str | None = None,     # "volume=1.5"
    metadata: dict[str, str] | None = None,
    start: float | str | None = None,     # Начальная позиция
    duration: float | str | None = None,  # Длительность
    extra_args: Sequence[str] | None = None,
    timeout: float | None = None,
    on_progress: ProgressCallback | None = None,
) -> ProcessResult: ...
```

#### extract_audio() — Извлечение аудио

```python
async def extract_audio(
    self,
    input: str | Path,
    output: str | Path,
    *,
    codec: str = "aac",
    bitrate: str = "128k",
    sample_rate: int | None = None,
    channels: int | None = None,
    timeout: float | None = None,
    on_progress: ProgressCallback | None = None,
) -> ProcessResult: ...
```

#### trim() — Обрезка

```python
async def trim(
    self,
    input: str | Path,
    output: str | Path,
    *,
    start: float | str | None = None,
    end: float | str | None = None,
    duration: float | str | None = None,
    copy: bool = True,                  # Stream copy по умолчанию (быстро)
    timeout: float | None = None,
    on_progress: ProgressCallback | None = None,
) -> ProcessResult: ...
```

#### concat() — Конкатенация

```python
async def concat(
    self,
    inputs: Sequence[str | Path],
    output: str | Path,
    *,
    method: Literal["demuxer", "filter", "protocol"] = "demuxer",
    timeout: float | None = None,
    on_progress: ProgressCallback | None = None,
) -> ProcessResult: ...
```

#### screenshot() — Скриншот

```python
async def screenshot(
    self,
    input: str | Path,
    output: str | Path,
    *,
    timestamp: float | str = 0,
    resolution: tuple[int, int] | None = None,
    quality: int = 2,                   # JPEG quality (2 = best)
    timeout: float | None = None,
) -> ProcessResult: ...
```

#### convert() — Конвертация контейнера

```python
async def convert(
    self,
    input: str | Path,
    output: str | Path,
    *,
    copy: bool = True,                  # Stream copy (без перекодирования)
    timeout: float | None = None,
    on_progress: ProgressCallback | None = None,
) -> ProcessResult: ...
```

#### normalize_audio() — Нормализация громкости

```python
async def normalize_audio(
    self,
    input: str | Path,
    output: str | Path,
    *,
    target_lufs: float = -14.0,
    target_tp: float = -1.0,
    target_lra: float = 7.0,
    codec: str | None = None,
    timeout: float | None = None,
    on_progress: ProgressCallback | None = None,
) -> ProcessResult: ...
```

#### scale() — Изменение разрешения

```python
async def scale(
    self,
    input: str | Path,
    output: str | Path,
    *,
    width: int,
    height: int,
    video_codec: str = "libx264",
    crf: int = 23,
    audio_codec: str = "copy",
    timeout: float | None = None,
    on_progress: ProgressCallback | None = None,
) -> ProcessResult: ...
```

---

## 4. FFmpegCommand API (Low-level Builder)

### 4.1 Fluent Builder

```python
class FFmpegCommand:
    """Immutable builder. Каждый метод возвращает новый объект."""

    # === Глобальные опции ===
    def overwrite(self, yes: bool = True) -> Self: ...
    def no_stdin(self) -> Self: ...
    def loglevel(self, level: str) -> Self: ...
    def progress(self, url: str = "pipe:1") -> Self: ...
    def stats_period(self, seconds: float) -> Self: ...
    def global_option(self, key: str, value: str | None = None) -> Self: ...

    # === Входные файлы ===
    def input(self, path: str | Path, **opts: str | int | float) -> Self: ...
    # Примеры opts: ss="10", t="30", hwaccel="auto", f="lavfi"

    # === Фильтры ===
    def video_filter(self, fg: str | FilterGraph) -> Self: ...
    def audio_filter(self, fg: str | FilterGraph) -> Self: ...
    def complex_filter(self, fg: str | FilterGraph) -> Self: ...

    # === Кодеки и потоки ===
    def video_codec(self, codec: str, stream: str | None = None) -> Self: ...
    def audio_codec(self, codec: str, stream: str | None = None) -> Self: ...
    def subtitle_codec(self, codec: str) -> Self: ...
    def map_stream(self, spec: str) -> Self: ...
    def no_video(self) -> Self: ...        # -vn
    def no_audio(self) -> Self: ...        # -an
    def no_subtitles(self) -> Self: ...    # -sn

    # === Выходные файлы ===
    def output(self, path: str | Path, **opts: str | int | float) -> Self: ...
    # Примеры opts: preset="medium", crf="23", b_v="5M", b_a="128k"

    # === Metadata ===
    def metadata(self, key: str, value: str) -> Self: ...

    # === Сборка и выполнение ===
    def build(self) -> list[str]: ...
    def build_pretty(self) -> str: ...     # Human-readable multiline

    async def execute(
        self,
        *,
        timeout: float | None = None,
        on_progress: ProgressCallback | None = None,
        on_stderr: StderrCallback | None = None,
    ) -> ProcessResult: ...
```

### 4.2 Примеры использования builder

```python
# Конвертация с фильтрами
cmd = (
    FFmpegCommand()
    .overwrite()
    .no_stdin()
    .progress()
    .stats_period(0.3)
    .input("input.mp4", ss="10", t="30")
    .video_filter("scale=1280:720,fps=30")
    .video_codec("libx264")
    .audio_codec("aac")
    .output("output.mp4", preset="medium", crf="23", b_a="128k")
)
result = await cmd.execute()

# Сложный filtergraph
cmd = (
    FFmpegCommand()
    .overwrite()
    .input("background.mp4")
    .input("overlay.png")
    .complex_filter('[0:v]scale=1920:1080[bg];[1:v]scale=200:200[fg];[bg][fg]overlay=10:10[out]')
    .map_stream("[out]")
    .map_stream("0:a")
    .video_codec("libx264")
    .audio_codec("copy")
    .output("output.mp4")
)
```

---

## 5. FFprobe API

### 5.1 Клиент

```python
class FFprobe:
    def __init__(
        self,
        ffprobe_path: str | Path | None = None,
        *,
        timeout: float = 30.0,
    ) -> None: ...

    async def probe(self, path: str | Path) -> MediaInfo: ...
    async def get_duration(self, path: str | Path) -> float | None: ...
    async def get_resolution(self, path: str | Path) -> tuple[int, int] | None: ...
    async def get_codecs(self, path: str | Path) -> dict[str, str]: ...
```

---

## 6. FilterGraph API

### 6.1 Simple Filters (helper functions)

```python
# Фабричные функции для частых фильтров
def scale(width: int | str, height: int | str) -> Filter: ...
def fps(rate: float | int) -> Filter: ...
def crop(w: int, h: int, x: int = 0, y: int = 0) -> Filter: ...
def rotate(angle: float) -> Filter: ...
def pad(w: int, h: int, x: int = 0, y: int = 0) -> Filter: ...
def trim(start: float | None = None, end: float | None = None) -> Filter: ...
def setpts(expr: str) -> Filter: ...

# Аудио
def volume(level: float | str) -> Filter: ...
def atempo(speed: float) -> Filter: ...
def afade(type: str, duration: float) -> Filter: ...
def loudnorm(i: float = -14, lra: float = 7, tp: float = -1) -> Filter: ...
```

### 6.2 Построение графа

```python
# Simple filtergraph
fg = FilterGraph.simple(
    scale(1280, 720),
    fps(30),
)
# Результат: "scale=1280:720,fps=30"

# Complex filtergraph
fg = (
    FilterGraph.complex()
    .chain(["0:v"], [scale(1280, 720)], ["scaled"])
    .chain(["1:v"], [scale(200, 200)], ["overlay_src"])
    .chain(["scaled", "overlay_src"], [overlay(10, 10)], ["out"])
)
# Результат: "[0:v]scale=1280:720[scaled];[1:v]scale=200:200[overlay_src];[scaled][overlay_src]overlay=10:10[out]"
```

---

## 7. Интеграция с async-yt-dlp

### 7.1 Принцип: НЕТ circular dependencies

```
async-yt-dlp  ←──(optional import)──  async-ffmpeg
     │                                      │
     └──────────── integration ─────────────┘
         (отдельный модуль или bridge)
```

### 7.2 Протокол интеграции

`async-ffmpeg` определяет Protocol, который async-yt-dlp может реализовать:

```python
# В async_ffmpeg/_types.py
from typing import Protocol

class DownloadResult(Protocol):
    """Протокол для результата скачивания."""
    @property
    def filepath(self) -> Path: ...
    @property
    def title(self) -> str | None: ...
    @property
    def duration(self) -> float | None: ...
```

### 7.3 Опциональная интеграция (extra dependency)

В `pyproject.toml`:
```toml
[project.optional-dependencies]
ytdlp = ["async-yt-dlp>=0.1.0"]
```

В коде:
```python
# async_ffmpeg/integration/__init__.py
try:
    from async_yt_dlp import DownloadResult as _YTDLPResult
    HAS_YTDLP = True
except ImportError:
    HAS_YTDLP = False
```

---

## 8. Обработка ошибок

### 8.1 Паттерны

```python
try:
    result = await client.transcode("input.mp4", "output.mp4")
except FFmpegNotFoundError:
    print("FFmpeg не установлен!")
except InvalidInputError as e:
    print(f"Невалидный файл: {e}")
except FFmpegProcessError as e:
    print(f"FFmpeg ошибка (exit {e.exit_code}): {e.stderr}")
except FFmpegTimeoutError:
    print("Превышен таймаут!")
except FFmpegCancelledError:
    print("Операция отменена")
```

### 8.2 ProcessResult содержит полную информацию

```python
result = await cmd.execute()
if result.exit_code != 0:
    print(f"stderr: {result.stderr.decode()}")
    print(f"Время выполнения: {result.duration_seconds:.1f}s")
```

---

## 9. Context Manager

```python
async with FFmpegClient() as client:
    info = await client.probe("input.mp4")
    await client.transcode("input.mp4", "output.mp4")
# Автоматическая очистка ресурсов и временных файлов
```

---

## 10. Конфигурация через env vars

| Переменная | Описание |
|-----------|----------|
| `FFMPEG_PATH` | Путь к ffmpeg |
| `FFPROBE_PATH` | Путь к ffprobe |
| `ASYNC_FFMPEG_MAX_CONCURRENT` | Макс. параллельных процессов |
| `ASYNC_FFMPEG_TIMEOUT` | Таймаут по умолчанию (сек) |
| `ASYNC_FFMPEG_TEMP_DIR` | Директория для temp файлов |
