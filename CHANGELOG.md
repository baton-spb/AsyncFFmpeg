# Changelog

Все заметные изменения в проекте `aio-ffmpeg` документируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/),
и проект придерживается [Семантического версионирования](https://semver.org/lang/ru/).

---

## [0.1.0] - 2026-09-19

### Добавлено
- **Высокоуровневый клиент (`FFmpegClient`)**: единый фасад с методами `transcode`, `extract_audio`, `trim`, `concat`, `screenshot`, `thumbnails`, `convert`, `normalize_audio`, `scale`, `two_pass_transcode`, `create_contact_sheet`, `detect_silence` и `probe`.
- **Конструктор команд (`FFmpegCommand`)**: строго упорядоченный fluent-builder аргументов FFmpeg CLI (глобальные опции -> входные параметры -> фильтры -> выходные параметры) с автоматической валидацией конфликтующих флагов.
- **Декларативный конвейер медиа (`MediaPipeline`)**: пошаговое построение цепочек обработки (trim, scale, watermark, audio normalization) с компиляцией в единый процесс FFmpeg и валидацией на этапе сборки.
- **Клиент инспекции (`FFprobe`) и строгие модели данных**: асинхронный запуск `ffprobe` с разбором JSON-вывода в типизированные frozen dataclass-модели (`MediaInfo`, `VideoStream`, `AudioStream`, `SubtitleStream`, `Chapter`, `StreamDisposition`).
- **Модуль аппаратного ускорения (`HardwareAccel`)**: автоматическое обнаружение доступных GPU-ускорителей (CUDA/NVENC, AMD AMF, Intel QSV, D3D11VA, Apple VideoToolbox) и подбор оптимальных кодеков.
- **Диспетчер процессов (`ProcessRunner`)**: асинхронное управление жизненным циклом подпроцессов через `asyncio.create_subprocess_exec()`, ограничение параллельности через `asyncio.Semaphore`, поддержка таймаутов и graceful shutdown (`q\n` -> SIGINT -> SIGKILL).
- **Машиночитаемый парсер прогресса (`ProgressParser`)**: разбор протокола `-progress pipe:1` в реальном времени с вычислением процента выполнения, времени, FPS, битрейта и скорости кодирования.
- **Объектно-ориентированный граф фильтров (`Filter`, `FilterChain`, `FilterGraph`, `ComplexFilterGraph`)**: фабричные функции для видео- и аудиофильтров (`scale`, `fps`, `crop`, `pad`, `rotate`, `overlay`, `drawtext`, `loudnorm`, `volume`, `amix`, `concat` и др.).
- **Модуль интеграции с `async-yt-dlp` (`aio_ffmpeg.integration`)**: функции `process_download_result`, `transcode_download`, `extract_download_audio` и класс `DownloadPostProcessor` на базе слабосвязанного протокола `DownloadResultProtocol`.
- **Комплекс интерактивных примеров (`examples/`)**: 7 готовых сценариев (`simple_transcode`, `extract_audio`, `video_thumbnails`, `watermark_and_filters`, `stream_concat`, `hardware_acceleration`, `ytdlp_pipeline`).
- **Инфраструктура и качество**: 118 автоматических тестов с 100% прохождением, поддержка Python 3.14+, строгая статическая типизация `mypy --strict` без единого `Any`, zero runtime dependencies (только стандартная библиотека Python).
