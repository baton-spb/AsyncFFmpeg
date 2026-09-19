# Интеграция с async-yt-dlp

Библиотека `async-ffmpeg` разработана для бесшовной совместной работы с `async-yt-dlp`.

---

## 1. Архитектурный принцип: слабая связность (Loose Coupling)

Между библиотеками **нет** жестких циклических импортов. Интеграция основана на протоколе `DownloadResultProtocol`:
```python
@runtime_checkable
class DownloadResultProtocol(Protocol):
    @property
    def filepath(self) -> Path: ...
    @property
    def title(self) -> str | None: ...
    @property
    def duration(self) -> float | None: ...
```

Любой объект, возвращаемый методом загрузки `async-yt-dlp` (или любой пользовательский класс с соответствующими свойствами), напрямую принимается функциями постобработки `async-ffmpeg`.

---

## 2. Использование: Скачивание → Транскодирование

```python
import asyncio
from async_yt_dlp import AsyncYoutubeDL
from async_ffmpeg.integration import process_download_result

async def main():
    # 1. Скачиваем видео через async-yt-dlp
    async with AsyncYoutubeDL() as ytdl:
        download_res = await ytdl.download("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    # 2. Передаем объект загрузки напрямую в ffmpeg
    processed = await process_download_result(
        download=download_res,
        action="transcode",
        resolution=(1280, 720),
        video_codec="libx264",
        crf=23,
    )

    print(f"Исходный файл: {processed.source}")
    print(f"Обработанный файл: {processed.output}")
    print(f"Длительность обработки: {processed.duration_seconds:.2f} сек")

asyncio.run(main())
```

---

## 3. Извлечение MP3 / M4A аудио

```python
from async_ffmpeg.integration import extract_download_audio

# Преобразует скачанное видео в аудиофайл
audio_res = await extract_download_audio(
    download=download_res,
    codec="libmp3lame",
    bitrate="192k",
)
print("Аудио сохранено в:", audio_res.output)
```

---

## 4. Использование в качестве Post-Processor хука

```python
from async_ffmpeg.integration import DownloadPostProcessor

# Создаем хук с заданными параметрами
transcoder_hook = DownloadPostProcessor(
    action="transcode",
    resolution=(1920, 1080),
    video_codec="libx264",
)

# Передаем в пайплайн обработки
result = await transcoder_hook(download_res)
```
