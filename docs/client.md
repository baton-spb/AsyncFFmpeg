# Высокоуровневый клиент FFmpegClient

Класс `FFmpegClient` — это главный высокоуровневый фасад библиотеки `async-ffmpeg` для решения типовых задач медиаобработки с контролем параллелизма, автоматическим расчетом прогресса и централизованным управлением жизненным циклом процессов.

---

## 1. Конструктор и параметры

```python
client = FFmpegClient(
    max_concurrent=4,          # Максимум 4 параллельных процесса FFmpeg
    default_timeout=600.0,      # Таймаут по умолчанию на операцию (сек)
    temp_dir="/tmp/ffmpeg",     # Каталог для временных файлов списков конкатенации
    ffmpeg_path=None,           # Путь к ffmpeg (None = автопоиск)
    ffprobe_path=None,          # Путь к ffprobe (None = автопоиск)
)
```

Также поддерживается контекстный менеджер `async with`:
```python
async with FFmpegClient(max_concurrent=2) as client:
    # При выходе из блока незавершенные процессы корректно закрываются,
    # а временные файлы гарантированно удаляются.
    await client.transcode(...)
```

---

## 2. Справочник методов

### `probe(path, timeout=None) -> MediaInfo`
Детальный структурный анализ медиафайла. Возвращает объект `MediaInfo` с типизированными потоками (`video_streams`, `audio_streams`, `subtitle_streams`), метаданными контейнера и главами.

### `transcode(input, output, ...) -> ProcessResult`
Универсальное транскодирование видео и аудио:
- `video_codec`: например `"libx264"`, `"h264_nvenc"`, `"copy"`.
- `crf`: фактор качества (0-51).
- `preset`: скорость сжатия (`ultrafast` ... `veryslow`).
- `resolution`: кортеж `(ширина, высота)`.
- `fps`: целевая частота кадров.
- `audio_codec`, `audio_bitrate`.
- `on_progress`: коллбэк для получения `ProgressInfo`.

### `extract_audio(input, output, codec="aac", bitrate="128k", sample_rate=None, channels=None) -> ProcessResult`
Быстрое извлечение или перекодирование звуковой дорожки из видео/аудио файла.

### `trim(input, output, start=None, end=None, duration=None, copy=True) -> ProcessResult`
Обрезка видеофрагмента. По умолчанию `copy=True` выполняет мгновенную обрезку по ключевым кадрам без перекодирования (stream copy).

### `concat(inputs, output, method="demuxer"|"filter", has_video=True, has_audio=True) -> ProcessResult`
Склейка нескольких файлов:
- `"demuxer"` — мгновенная склейка однородных файлов без сжатия через временный плейлист.
- `"filter"` — склейка разнородных файлов через фильтр `concat` с перекодированием.

### `screenshot(input, output, timestamp=0, resolution=None, quality=2) -> ProcessResult`
Создание одиночного кадра-скриншота в заданной временной метке.

### `thumbnails(input, output_pattern, interval=None, count=None, fps=None, resolution=None) -> ProcessResult`
Генерация серии кадров-превью:
- По интервалу: `interval=10.0` (кадр каждые 10 секунд).
- По общему количеству: `count=12` (12 равномерно распределенных кадров по длительности видео).
- По частоте: `fps=1` (1 кадр в секунду).

### `convert(input, output, copy=True) -> ProcessResult`
Смена контейнера (например `.mkv` → `.mp4`, `.ts` → `.mp4`) без перекодирования.

### `normalize_audio(input, output, target_lufs=-14.0, target_tp=-1.0, target_lra=7.0) -> ProcessResult`
Нормализация громкости звука по международному стандарту вещания EBU R128 (loudnorm).

### `scale(input, output, width, height, video_codec="libx264", crf=23, preset="medium", audio_codec="copy") -> ProcessResult`
Масштабирование видео в указанное разрешение.

### `pipeline(input=None) -> MediaPipeline`
Создает объект `MediaPipeline`, привязанный к настройкам текущего клиента.
