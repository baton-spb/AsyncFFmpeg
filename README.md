# aio-ffmpeg

[![CI](https://github.com/baton-spb/aio-ffmpeg/actions/workflows/ci.yml/badge.svg)](https://github.com/baton-spb/aio-ffmpeg/actions)
[![PyPI version](https://img.shields.io/pypi/v/aio-ffmpeg.svg)](https://pypi.org/project/aio-ffmpeg/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Typing: Typed](https://img.shields.io/badge/typing-typed-green.svg)](https://peps.python.org/pep-0561/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Строго типизированная асинхронная обёртка над `ffmpeg` и `ffprobe` для Python 3.11+.

Процессы запускаются через `asyncio.create_subprocess_exec()`. Нет зависимостей времени выполнения — только стандартная библиотека Python.

---

## Сравнение с аналогами

| Возможность | `aio-ffmpeg` | `ffmpeg-python` | `moviepy` | `subprocess` |
|:---|:---:|:---:|:---:|:---:|
| Асинхронность (`asyncio`) | Да | Нет | Нет | Ручная реализация |
| Зависимости runtime | 0 (stdlib) | 2 | 10+ | 0 |
| Строгая типизация (`mypy --strict`) | Да | Нет | Частичная | Нет |
| Парсинг прогресса | Да (`-progress pipe:1`) | Нет | Tqdm | Ручной |
| Graceful shutdown | Да (`q\n` → SIGINT) | Нет | Нет | Нет |
| Автоопределение GPU | Да (NVENC/AMF/QSV/VideoToolbox) | Нет | Нет | Нет |

---

## Возможности

- **Асинхронный запуск процессов**: `asyncio.create_subprocess_exec()`, контроль конкурентности через `asyncio.Semaphore`.
- **Типизация**: frozen dataclass-модели со `slots=True`, PEP 561 `py.typed`, `mypy --strict`.
- **Прогресс**: потоковый разбор протокола `-progress pipe:1` (кадры, время, битрейт, скорость, процент).
- **Graceful shutdown**: отправка `q` в stdin перед системными сигналами завершения. Предотвращает повреждение заголовков MP4.
- **Три уровня API**:
  - `FFmpegClient` — готовые методы для типовых задач.
  - `MediaPipeline` — декларативный конвейер цепочек обработки.
  - `FFmpegCommand` — построитель аргументов CLI с валидацией.
- **FFprobe**: типизированный разбор контейнеров, видео/аудио/субтитр-потоков, глав и метаданных.
- **Аппаратное ускорение**: автоопределение NVENC, AMF, QSV, D3D11VA, VideoToolbox.
- **Интеграция с `async-yt-dlp`**: конвейер загрузки и постобработки медиафайлов.

---

## Методы `FFmpegClient`

| Метод | Назначение |
|:---|:---|
| `transcode(...)` | Перекодирование с контролем кодеков, битрейта, разрешения, FPS и фильтров |
| `two_pass_transcode(...)` | Двухпроходное кодирование с контролем битрейта |
| `extract_audio(...)` | Извлечение аудиодорожки (`-vn`) в AAC, MP3, FLAC, OPUS, WAV |
| `trim(...)` | Обрезка по меткам времени (stream copy или перекодирование) |
| `concat(...)` | Склейка файлов через demuxer или граф фильтров |
| `convert(...)` | Смена контейнера (remuxing, stream copy) |
| `scale(...)` | Масштабирование видео |
| `normalize_audio(...)` | Двухпроходная нормализация по EBU R128 (фильтр `loudnorm`) |
| `screenshot(...)` | Извлечение кадра по временной метке |
| `thumbnails(...)` | Генерация миниатюр по интервалу, количеству или частоте кадров |
| `create_contact_sheet(...)` | Раскадровка — сетка миниатюр (`tile`) |
| `detect_silence(...)` | Обнаружение тишины и пауз (`SilenceInterval`) |
| `probe(...)` | Анализ метаданных файла → типизированный `MediaInfo` |
| `pipeline(...)` | Создание `MediaPipeline` для декларативной обработки |

---

## Установка

Требуется Python **3.11+**, установленные в системе `ffmpeg` и `ffprobe` (в `PATH` или через аргументы клиента / переменную `FFMPEG_PATH`).

```bash
# Базовая установка (без runtime-зависимостей):
pip install aio-ffmpeg

# С интеграцией с async-yt-dlp:
pip install "aio-ffmpeg[ytdlp]"
```

Или через `uv`:
```bash
uv add aio-ffmpeg
```

---

## Быстрый старт

### 1. Анализ медиафайла

```python
import asyncio
from aio_ffmpeg import FFmpegClient


async def main() -> None:
    client = FFmpegClient()
    info = await client.probe("video.mp4")

    print(f"Формат: {info.format.format_long_name}")
    print(f"Длительность: {info.duration} сек")

    if info.primary_video:
        v = info.primary_video
        print(f"Видео: {v.codec_name}, {v.width}x{v.height} @ {v.frame_rate:.2f} fps")

    if info.primary_audio:
        a = info.primary_audio
        print(f"Аудио: {a.codec_name}, {a.sample_rate} Hz, каналов: {a.channels}")


asyncio.run(main())
```

### 2. Транскодирование с прогрессом

```python
import asyncio
from aio_ffmpeg import FFmpegClient, ProgressInfo


async def main() -> None:
    client = FFmpegClient()

    async def on_progress(p: ProgressInfo) -> None:
        print(f"Прогресс: {p.percent:.1f}% | Скорость: {p.speed} | FPS: {p.fps:.1f}")

    result = await client.transcode(
        input="input.mp4",
        output="output_720p.mp4",
        video_codec="libx264",
        crf=23,
        resolution=(1280, 720),
        audio_codec="aac",
        audio_bitrate="128k",
        on_progress=on_progress,
    )
    print(f"Готово за {result.duration_seconds:.2f} сек")


asyncio.run(main())
```

### 3. Декларативный конвейер (`MediaPipeline`)

```python
import asyncio
from aio_ffmpeg import FFmpegClient


async def main() -> None:
    client = FFmpegClient()

    # обрезка → масштабирование → нормализация звука → вывод
    await (
        client.pipeline("input.mp4")
        .trim(start=10, duration=60)
        .scale(1280, 720)
        .normalize_audio(target_lufs=-16.0)
        .output("highlight_720p.mp4")
        .run()
    )


asyncio.run(main())
```

### 4. Интеграция с `async-yt-dlp`

```python
import asyncio
from aio_ffmpeg import FFmpegClient
from aio_ffmpeg.integration import process_download_result


async def main() -> None:
    client = FFmpegClient()

    # download_result — объект с протоколом DownloadResultProtocol
    post_result = await process_download_result(
        download_result,
        action="extract_audio",
        client=client,
        audio_format="mp3",
        audio_bitrate="320k",
    )
    print(f"Результат: {post_result.output_path}")


asyncio.run(main())
```

---

## Примеры

В каталоге [`examples/`](examples/) — готовые примеры:

- [`simple_transcode.py`](examples/simple_transcode.py) — перекодирование с прогрессом
- [`extract_audio.py`](examples/extract_audio.py) — извлечение звуковых дорожек
- [`video_thumbnails.py`](examples/video_thumbnails.py) — скриншоты, миниатюры, раскадровка
- [`watermark_and_filters.py`](examples/watermark_and_filters.py) — водяные знаки и фильтры через `MediaPipeline`
- [`stream_concat.py`](examples/stream_concat.py) — склейка медиафайлов
- [`hardware_acceleration.py`](examples/hardware_acceleration.py) — кодирование с аппаратным ускорением
- [`ytdlp_pipeline.py`](examples/ytdlp_pipeline.py) — конвейер с `async-yt-dlp`

---

## Разработка

```bash
# Dev-окружение
uv sync --extra dev

# Линтинг
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# Типизация
uv run mypy src/

# Тесты
uv run pytest tests/ -v
```

---

## Лицензия

Распространяется под лицензией [MIT](LICENSE).
