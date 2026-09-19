# Конвейер операций MediaPipeline

`MediaPipeline` — это fluent интерфейс для построения цепочек преобразований медиаданных. Все операции компилируются в единую команду FFmpeg и выполняются в одном процессе без создания промежуточных временных файлов.

---

## 1. Зачем нужен MediaPipeline?

Вместо последовательного выполнения нескольких команд (например, сначала обрезать файл в temp1, затем наложить логотип в temp2, затем изменить громкость в temp3), что приводит к многократному сжатию с потерей качества и лишней нагрузке на диск:
`MediaPipeline` строит единый граф фильтров и опций кодирования, сжимая видео один-единственный раз в конечном контейнере.

---

## 2. Валидация на этапе сборки (Build-time Validation)

При вызове `.to_command()` или `.run()` конвейер проверяет совместимость всех указанных параметров:
- Запрет сочетания `copy_video` (stream copy) с фильтрами видео (`scale`, `crop`, `watermark`).
- Запрет сочетания `copy_audio` с фильтрами аудио (`volume`, `loudnorm`).
- Запрет указания опций видео вместе с флагом `no_video()`.
- Запрет указания опций аудио вместе с флагом `no_audio()`.
- Обязательное наличие хотя бы одного входа (`input`) и выхода (`output`).

При обнаружении конфликта выбрасывается понятное исключение `CommandBuildError` **до** запуска подпроцесса FFmpeg.

---

## 3. Поддерживаемые операции

| Категория | Методы | Описание |
|---|---|---|
| **Входы и HW** | `input(target, **opts)`<br>`hwaccel(name, ...)` | Добавление источников и аппаратного ускорения |
| **Тайминг** | `trim(start, end, duration, fast_seek=True)`<br>`seek(start)`<br>`duration(dur)` | Обрезка и позиционирование |
| **Геометрия** | `scale(w, h, keep_aspect_ratio=False)`<br>`crop(w, h, x, y)`<br>`pad(w, h, x, y, color)` | Изменение размеров и соотношения сторон |
| **Ориентация** | `rotate(angle)`<br>`vflip()`<br>`hflip()`<br>`transpose(dir)` | Повороты и зеркальные отражения |
| **Фильтры видео** | `blur(radius)`<br>`sharpen(luma)`<br>`drawtext(text, ...)`<br>`video_filter(f)` | Размытие, резкость, надписи, кастомные фильтры |
| **Водяной знак** | `watermark(path, position, margin, opacity)` | Автоматический complex filtergraph с наложением логотипа |
| **Аудио** | `volume(level)`<br>`normalize_audio(lufs, tp, lra)`<br>`afade(type, start, dur)`<br>`atempo(speed)`<br>`audio_filter(f)` | Регулировка уровня, EBU R128 loudnorm, фейды, скорость |
| **Кодеки** | `video_codec(codec, ...)`<br>`audio_codec(codec, ...)`<br>`copy_video()`<br>`copy_audio()`<br>`copy_all()` | Выбор кодеков или режим прямого копирования |
| **Качество** | `crf(val)`<br>`preset(name)`<br>`bitrate(video, audio)` | Параметры битрейта и степени сжатия |
| **Метаданные** | `metadata(key, value)`<br>`map_stream(spec)`<br>`extra_args(*args)` | Теги, маппинг потоков, сырые CLI флаги |
| **Выполнение** | `to_command()`<br>`build()`<br>`preview()`<br>`run(...)` | Компиляция, предпросмотр и асинхронный запуск |

---

## 4. Пример комплексного конвейера

```python
import asyncio
from aio_ffmpeg import FFmpegClient, ProgressInfo


async def main():
    client = FFmpegClient()

    def on_prog(p: ProgressInfo):
        pct = f"{p.percentage:.1f}%" if p.percentage else "..."
        print(f"\rОбработка: {pct} | FPS: {p.fps:.1f}", end="")

    pipeline = (
        client.pipeline("raw_camera_footage.mp4")
        # 1. Точная обрезка
        .trim(start="00:00:15", duration=45.0)
        # 2. Преобразования видео
        .scale(1920, 1080)
        .fps(30)
        .sharpen(luma_amount=1.2)
        # 3. Наложение полупрозрачного логотипа в правый верхний угол
        .watermark("assets/logo.png", position="top-right", margin=25, opacity=0.8)
        # 4. Обработка звука
        .volume("1.5dB")
        .afade(type="in", start_time=0.0, duration=1.0)
        .afade(type="out", start_time=44.0, duration=1.0)
        .normalize_audio(target_lufs=-14.0)
        # 5. Кодирование
        .video_codec("libx264", preset="faster", crf=22)
        .audio_codec("aac", bitrate="192k")
        # 6. Метаданные и вывод
        .metadata("title", "Promotional Teaser")
        .metadata("artist", "Video Production Team")
        .output("final_teaser.mp4")
    )

    print("Сформированная команда FFmpeg:")
    print(pipeline.preview())

    result = await pipeline.run(on_progress=on_prog)
    print(f"\nУспешно завершено за {result.duration_seconds:.2f} сек!")


asyncio.run(main())
```
