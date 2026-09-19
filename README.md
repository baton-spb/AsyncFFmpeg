# async-ffmpeg

[![CI](https://github.com/baton-spb/AsyncFFmpeg/actions/workflows/ci.yml/badge.svg)](https://github.com/baton-spb/AsyncFFmpeg/actions)
[![PyPI version](https://img.shields.io/pypi/v/async-ffmpeg.svg)](https://pypi.org/project/async-ffmpeg/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Typing: Typed](https://img.shields.io/badge/typing-typed-green.svg)](https://peps.python.org/pep-0561/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**async-ffmpeg** — современная, строго типизированная, production-ready асинхронная библиотека-обёртка над `ffmpeg` и `ffprobe` для Python 3.11+.

Она построена непосредственно поверх `asyncio.create_subprocess_exec()` без сторонних C-библиотек, без устаревших binding-ов и с **нулевыми зависимостями времени выполнения** (zero runtime dependencies, только стандартная библиотека Python).

---

## Сравнение с аналогами

| Возможность | `async-ffmpeg` | `ffmpeg-python` | `moviepy` | `subprocess` (ручной) |
|:---|:---:|:---:|:---:|:---:|
| **Нативная асинхронность (`asyncio`)** | **Да** | Нет | Нет | Требует ручной реализации |
| **Зависимости времени выполнения** | **0 (только stdlib)** | 2 | 10+ (тяжёлые) | 0 |
| **Строгая типизация (`mypy --strict`)** | **100% (Zero Any)** | Нет типов | Частичная | Нет |
| **Парсинг прогресса в реальном времени** | **Да (`-progress pipe:1`)** | Нет | Tqdm (базовый) | Ручной парсинг |
| **Безопасная остановка (Graceful Shutdown)** | **Да (`q\n` -> SIGINT)** | Нет | Нет | Нет |
| **Многоуровневый API (Facade / Pipeline / Builder)** | **Да** | Только builder | Только facade | Нет |
| **Автоопределение GPU (CUDA/AMF/QSV/Toolbox)** | **Да** | Нет | Нет | Нет |
| **Поддержка современного Python 3.14+** | **Да** | Заброшен | Медленный | Да |

---

## Ключевые возможности

- **Полноценная асинхронность**: неблокирующий запуск процессов через `asyncio.create_subprocess_exec()`, контроль конкурентности через `asyncio.Semaphore`.
- **Строгая типизация**: 100% соответствие `mypy --strict` и `Zero Any policy`, frozen dataclass-модели со `slots=True`, маркер PEP 561 (`py.typed`).
- **Машиночитаемый прогресс**: чтение и потоковый разбор протокола `-progress pipe:1` (кадры, время, битрейт, скорость кодирования, процент выполнения).
- **Graceful Shutdown**: предотвращение повреждения медиафайлов (битых заголовков MP4 / unclosed `moov` atom) путём отправки `q` в stdin перед отправкой системных сигналов завершения.
- **Трёхуровневый API**:
  - **Facade (`FFmpegClient`)**: готовые методы для решения 95% повседневных задач.
  - **Pipeline (`MediaPipeline`)**: декларативный конвейер цепочек обработки видео и аудио.
  - **Command Builder (`FFmpegCommand`)**: строгий конструктор аргументов CLI с контролем порядка и валидацией конфликтов.
- **Типизированный FFprobe**: детальный разбор контейнеров, видео/аудио/субтитр-потоков, глав и метаданных.
- **Аппаратное ускорение**: автоопределение и конфигурация NVENC, AMF, QSV, D3D11VA, VideoToolbox.
- **Интеграция с `async-yt-dlp`**: бесшовный конвейер загрузки и последующей обработки медиафайлов.

---

## Методы высокоуровневого клиента (`FFmpegClient`)

| Метод | Назначение |
|:---|:---|
| `transcode(...)` | Универсальное перекодирование с контролем кодеков, битрейта, разрешения, FPS и фильтров. |
| `extract_audio(...)` | Извлечение аудиодорожки (`-vn`) с конвертацией в AAC, MP3, FLAC, OPUS или WAV. |
| `trim(...)` | Быстрая обрезка медиафрагментов по меткам времени (со stream copy или перекодированием). |
| `concat(...)` | Склейка нескольких файлов без перекодирования (demuxer) или через граф фильтров. |
| `screenshot(...)` | Извлечение одного кадра в указанной временной метке в высоком качестве. |
| `thumbnails(...)` | Серийная генерация миниатюр по фиксированному интервалу, общему числу или частоте кадров. |
| `convert(...)` | Быстрая смена контейнера (remuxing, например MKV -> MP4) со stream copy. |
| `normalize_audio(...)` | Двухпроходная нормализация громкости по вещательному стандарту EBU R128 (`loudnorm`). |
| `scale(...)` | Масштабирование видеоряда с сохранением исходной аудиодорожки без перекодирования. |
| `two_pass_transcode(...)` | Двухпроходное кодирование с контролем битрейта и автоматической очисткой временных логов. |
| `create_contact_sheet(...)` | Сборка раскадровки (storyboard/contact sheet) в виде сетки миниатюр (`tile`). |
| `detect_silence(...)` | Детектирование тишины и пауз в аудиодорожке с получением интервалов (`SilenceInterval`). |
| `probe(...)` | Детальный анализ метаданных файла или потока с возвратом типизированного `MediaInfo`. |

---

## Установка

```bash
# Базовая установка (zero external dependencies)
uv add async-ffmpeg

# Или через pip:
pip install async-ffmpeg

# С опциональной поддержкой интеграции с async-yt-dlp
pip install "async-ffmpeg[ytdlp]"
```

Требования:
- Python >= 3.14
- Установленный в системе `ffmpeg` и `ffprobe` (в `PATH` или указанный через аргументы клиента / переменную `FFMPEG_PATH`)

---

## Быстрый старт

### 1. Анализ медиафайла (`FFprobe`)

```python
import asyncio
from async_ffmpeg import FFmpegClient


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

### 2. Транскодирование с отслеживанием прогресса

```python
import asyncio
from async_ffmpeg import FFmpegClient, ProgressInfo


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
    print(f"Готово за {result.duration_seconds:.2f} сек!")


asyncio.run(main())
```

### 3. Декларативный конвейер (`MediaPipeline`)

```python
import asyncio
from async_ffmpeg import FFmpegClient


async def main() -> None:
    client = FFmpegClient()

    # Цепочка: обрезка -> масштабирование -> нормализация звука -> вывод
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

### 4. Интеграция с загрузчиком (`async-yt-dlp`)

```python
import asyncio
from async_ffmpeg import FFmpegClient
from async_ffmpeg.integration import process_download_result


async def main() -> None:
    # Загрузка через yt-dlp (или совместимый объект с протоколом DownloadResultProtocol)
    # Предположим, результат загрузки сохранён в download_result
    client = FFmpegClient()

    # Автоматическое извлечение аудиодорожки или конвертация
    post_result = await process_download_result(
        download_result,
        action="extract_audio",
        client=client,
        audio_format="mp3",
        audio_bitrate="320k",
    )
    print(f"Обработано: {post_result.output_path}")


asyncio.run(main())
```

---

## Примеры использования (`examples/`)

В каталоге [`examples/`](examples/) содержатся готовые исполняемые сценарии:

1. [`simple_transcode.py`](examples/simple_transcode.py) — Базовое перекодирование с отслеживанием прогресса в реальном времени.
2. [`extract_audio.py`](examples/extract_audio.py) — Извлечение звуковых дорожек в форматах MP3, AAC, FLAC и нормализация звука.
3. [`video_thumbnails.py`](examples/video_thumbnails.py) — Снятие скриншотов, серийная генерация миниатюр и раскадровка (contact sheet).
4. [`watermark_and_filters.py`](examples/watermark_and_filters.py) — Наложение водяных знаков и комплексных графов фильтров через `MediaPipeline`.
5. [`stream_concat.py`](examples/stream_concat.py) — Склейка медиафайлов через демультиплексор (demuxer) и фильтр объединения.
6. [`hardware_acceleration.py`](examples/hardware_acceleration.py) — Автоматическое обнаружение GPU и кодирование с аппаратным ускорением.
7. [`ytdlp_pipeline.py`](examples/ytdlp_pipeline.py) — Полный конвейер скачивания и последующей обработки с `async-yt-dlp`.

---

## Архитектура и документация

Подробная проектная документация доступна в каталоге [`docs/`](docs/):

- [`architecture.md`](docs/architecture.md) — Системная архитектура, слои абстракции, управление процессами.
- [`api-design.md`](docs/api-design.md) — Детальное описание публичного API и сигнатур.
- [`research.md`](docs/research.md) — Исследование поведения FFmpeg CLI, протокола `-progress` и кодов возврата.
- [`pipeline.md`](docs/pipeline.md) — Руководство по работе с `MediaPipeline`.
- [`hardware.md`](docs/hardware.md) — Конфигурация и использование аппаратного ускорения (GPU).
- [`integration.md`](docs/integration.md) — Взаимодействие с внешними загрузчиками и `async-yt-dlp`.

---

## Разработка и тестирование

```bash
# Установка dev-окружения
uv sync --extra dev

# Проверка форматирования и линтинга
uv run ruff check src/ tests/ examples/ docs/
uv run ruff format --check src/ tests/ examples/ docs/

# Проверка строгой статической типизации
uv run mypy src/

# Запуск тестов
uv run pytest tests/ -v
```

---

## Лицензия

Распространяется под лицензией [MIT](LICENSE).
