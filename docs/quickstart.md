# Быстрый старт с async-ffmpeg

Библиотека `async-ffmpeg` предоставляет удобные асинхронные интерфейсы для работы с медиафайлами любого объема, опираясь на CLI `ffmpeg` и `ffprobe`.

---

## 1. Установка и требования

- Python **3.14+**
- Установленные в системе бинарники `ffmpeg` и `ffprobe` (доступные в системном `PATH` либо настроенные через переменные окружения `FFMPEG_PATH` и `FFPROBE_PATH`).

```bash
# Установка через uv
uv add async-ffmpeg

# Или через pip
pip install async-ffmpeg
```

---

## 2. Основные сценарии использования

### Сценарий 1: Анализ файла через FFprobe

```python
import asyncio
from async_ffmpeg import FFmpegClient

async def main() -> None:
    client = FFmpegClient()
    info = await client.probe("input.mp4")

    print(f"Контейнер: {info.format.format_long_name}")
    print(f"Длительность: {info.duration:.2f} сек")
    print(f"Битрейт: {info.format.bit_rate} bps")

    if info.primary_video:
        v = info.primary_video
        print(f"Видео: {v.codec_name} {v.width}x{v.height} ({v.frame_rate:.2f} fps)")

    if info.primary_audio:
        a = info.primary_audio
        print(f"Аудио: {a.codec_name}, частота {a.sample_rate} Гц, каналы: {a.channels}")

asyncio.run(main())
```

---

### Сценарий 2: Простое и быстрое транскодирование

```python
import asyncio
from async_ffmpeg import FFmpegClient, ProgressInfo

async def main() -> None:
    async with FFmpegClient(max_concurrent=3) as client:
        def on_prog(p: ProgressInfo) -> None:
            pct = f"{p.percentage:.1f}%" if p.percentage is not None else "N/A"
            print(f"Прогресс: {pct} | FPS: {p.fps:.1f} | Скорость: {p.speed}")

        result = await client.transcode(
            input="raw_video.mov",
            output="compressed.mp4",
            video_codec="libx264",
            preset="faster",
            crf=23,
            resolution=(1280, 720),
            audio_codec="aac",
            audio_bitrate="128k",
            on_progress=on_prog,
        )
        print(f"Готово за {result.duration_seconds:.2f} сек!")

asyncio.run(main())
```

---

### Сценарий 3: Fluent Конвейер (MediaPipeline)

Если требуется объединить масштабирование, обрезку, наложение водяного знака и нормализацию громкости в один запуск FFmpeg:

```python
import asyncio
from async_ffmpeg import FFmpegClient

async def main() -> None:
    client = FFmpegClient()
    pipeline = (
        client.pipeline("stream_recording.ts")
        .trim(start=10.0, duration=60.0)
        .scale(1920, 1080)
        .fps(30)
        .watermark("branding.png", position="top-right", margin=20, opacity=0.85)
        .normalize_audio(target_lufs=-14.0)
        .video_codec("libx264", preset="medium", crf=22)
        .audio_codec("aac", bitrate="192k")
        .metadata("title", "Highlighted Moment")
        .output("highlight.mp4")
    )

    result = await pipeline.run()
    print("Конвейер выполнен:", result.success)

asyncio.run(main())
```

---

### Сценарий 4: Извлечение аудиодорожки

```python
import asyncio
from async_ffmpeg import FFmpegClient

async def main() -> None:
    client = FFmpegClient()
    await client.extract_audio(
        input="podcast.mp4",
        output="podcast.mp3",
        codec="libmp3lame",
        bitrate="192k",
    )

asyncio.run(main())
```

---

### Сценарий 5: Создание серии превью-кадров (thumbnails)

```python
import asyncio
from async_ffmpeg import FFmpegClient

async def main() -> None:
    client = FFmpegClient()
    # Извлечет 1 кадр каждые 10 секунд
    await client.thumbnails(
        input="movie.mkv",
        output_pattern="thumbs/frame_%04d.jpg",
        interval=10.0,
        resolution=(320, 180),
    )

asyncio.run(main())
```
