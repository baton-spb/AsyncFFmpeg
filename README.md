# async-ffmpeg

[![CI](http://localhost:3000/6aton/AsyncFFmpeg/actions/workflows/ci.yml/badge.svg)](http://localhost:3000/6aton/AsyncFFmpeg/actions)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![Typing: Typed](https://img.shields.io/badge/typing-typed-green.svg)](https://peps.python.org/pep-0561/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**async-ffmpeg** — современная, строго типизированная, production-ready асинхронная библиотека-обёртка над `ffmpeg` и `ffprobe` для Python 3.14+.

Она построена непосредственно поверх `asyncio.create_subprocess_exec()` без C-библиотек, без устаревших binding-ов и с нулевыми зависимостями времени выполнения (zero runtime dependencies).

---

## Ключевые возможности

- 🚀 **Полноценная асинхронность**: неблокирующий запуск процессов через `asyncio.create_subprocess_exec()`, контроль конкурентности через `asyncio.Semaphore`.
- 🛡️ **Строгая типизация**: полная совместимость с `mypy --strict`, frozen dataclass-модели со `slots=True`, PEP 561 (`py.typed`).
- 📊 **Машиночитаемый прогресс**: чтение и парсинг протокола `-progress pipe:1` (кадры, время, битрейт, скорость, процент выполнения).
- 🛑 **Graceful Shutdown**: корректная финализация медиафайлов через отправку `q` в stdin (предотвращение битых moov atom / заголовков MP4).
- 🧩 **Двухуровневый API**:
  - **High-level (`FFmpegClient`)**: готовые методы `transcode()`, `extract_audio()`, `trim()`, `concat()`, `screenshot()`, `normalize_audio()`, `probe()`.
  - **Low-level (`FFmpegCommand`)**: строгий builder команд с контролем порядка аргументов (global → input opts → inputs → filters → output opts → outputs).
- 🔍 **Типизированный FFprobe**: парсинг формата, видео/аудио потоков, глав и тегов в строгие модели данных.
- ⚡ **Аппаратное ускорение**: автоопределение и конфигурация NVENC, AMF, QSV, D3D11VA, VideoToolbox.
- 🔗 **Интеграция с async-yt-dlp**: бесшовная цепочка скачивание → постобработка без циклических зависимостей.

---

## Установка

```bash
# Базовая установка
pip install async-ffmpeg

# С поддержкой интеграции с async-yt-dlp
pip install "async-ffmpeg[ytdlp]"
```

Или с использованием `uv`:

```bash
uv add async-ffmpeg
```

Требования:
- Python >= 3.14
- Установленный в системе `ffmpeg` и `ffprobe` (в `PATH` или указанный явно через путь / переменную окружения `FFMPEG_PATH`)

---

## Быстрый старт

### Анализ медиафайла (FFprobe)

```python
import asyncio
from async_ffmpeg import FFmpegClient

async def main():
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

### Транскодирование с отслеживанием прогресса

```python
import asyncio
from async_ffmpeg import FFmpegClient, ProgressInfo

async def main():
    client = FFmpegClient()

    async def on_progress(p: ProgressInfo) -> None:
        print(f"Время: {p.out_time} | Скорость: {p.speed} | FPS: {p.fps:.1f}")

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
    print(f"Успешно за {result.duration_seconds:.2f} сек!")

asyncio.run(main())
```

### Конструктор команд (FFmpegCommand)

```python
from async_ffmpeg import FFmpegCommand

cmd = (
    FFmpegCommand()
    .overwrite()
    .no_stdin()
    .progress()
    .input("source.mov", ss="00:01:00", t="30")
    .video_filter("scale=1920:1080,fps=30")
    .video_codec("libx264")
    .output("clip.mp4", preset="slow", crf="21")
)

# Просмотр аргументов
print(cmd.build())

# Асинхронное выполнение
result = await cmd.execute()
```

---

## Архитектура и документация

Подробная проектная документация доступна в каталоге [`docs/`](docs/):
- [`research.md`](docs/research.md) — Исследование поведения FFmpeg CLI, протокола `-progress`, кодов возврата и аппаратных декодеров.
- [`architecture.md`](docs/architecture.md) — Системная архитектура, слои абстракции, управление процессами.
- [`api-design.md`](docs/api-design.md) — Детальное описание публичного API и сигнатур.

---

## Разработка и тестирование

```bash
# Установка dev-окружения
uv sync --all-extras

# Запуск линтеров и проверки типов
uv run ruff check .
uv run ruff format --check .
uv run mypy src/ --strict

# Запуск тестов
uv run pytest -v
```

---

## Лицензия

Распространяется под лицензией [MIT](LICENSE).
