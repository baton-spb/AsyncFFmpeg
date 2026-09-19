# Построитель команд FFmpegCommand

Класс `FFmpegCommand` представляет собой строгий, типизированный fluent builder для создания низкоуровневых команд CLI FFmpeg с контролем синтаксиса и порядка следования аргументов.

---

## 1. Порядок аргументов FFmpeg

FFmpeg критически чувствителен к порядку аргументов:
```
ffmpeg [глобальные флаги] [опции входа] -i input [фильтры] [опции выхода] output
```

`FFmpegCommand` гарантирует, что даже если вы вызываете методы в произвольном порядке, итоговая строка всегда сериализуется строго по правилам FFmpeg:
1. `[ffmpeg_executable]`
2. `[global_options]` (`-y`, `-n`, `-nostdin`, `-hide_banner`, `-loglevel`, `-progress`, `-stats_period`, ...)
3. `{[input_options] -i target}` (для каждого входа)
4. `[filters]` (`-vf`, `-af`, `-filter_complex`)
5. `{[stream_maps] [codecs] [bitrates] [metadata] output}` (для каждого выхода)
6. `[extra_args]`

---

## 2. Основные методы

### Глобальные флаги
- `.overwrite(yes: bool = True)` — включает `-y` (перезапись существующих файлов).
- `.no_overwrite()` — включает `-n` (не перезаписывать).
- `.no_stdin(yes: bool = True)` — включает `-nostdin`.
- `.hide_banner(yes: bool = True)` — скрывает баннер сборки `-hide_banner`.
- `.loglevel(level: LogLevel | str)` — устанавливает `-loglevel` (`error`, `warning`, `info`, `quiet` и т.д.).
- `.progress(url: str = "pipe:1", stats_period: float | None = None)` — направляет статистику прогресса в `-progress`.
- `.global_option(key: str, value: str | int | float | None = None)` — произвольная глобальная опция.

### Входные файлы
- `.input(target, **opts)` — добавляет входной файл `-i target`. Переданные kwargs автоматически преобразуются в опции, предшествующие флагу `-i` (например `ss="10"`, `t="30"`, `f="lavfi"`).
- `.hwaccel(name, device=None, output_format=None)` — добавляет флаги аппаратного ускорения (`-hwaccel`, `-hwaccel_device`, `-hwaccel_output_format`) к следующему вызываемому `input()`.

### Фильтры
- `.video_filter(filtergraph)` — устанавливает простой видеофильтр (`-vf`). Принимает строку, `Filter`, `FilterChain` или `FilterGraph`.
- `.audio_filter(filtergraph)` — устанавливает простой аудиофильтр (`-af`).
- `.complex_filter(filtergraph)` — устанавливает комплексный граф фильтров (`-filter_complex`).

### Опции выходных потоков
Опции применяются к следующему вызванному методу `.output()`:
- `.video_codec(codec, stream_spec=None)` — устанавливает кодек видео (`-c:v` или `-c:v:0`).
- `.audio_codec(codec, stream_spec=None)` — устанавливает кодек аудио (`-c:a`).
- `.subtitle_codec(codec)` — устанавливает кодек субтитров (`-c:s`).
- `.codec(codec)` — единый кодек (`-c`).
- `.copy_video()` — алиас для `.video_codec("copy")`.
- `.copy_audio()` — алиас для `.audio_codec("copy")`.
- `.copy_all()` — алиас для `.codec("copy")`.
- `.preset(preset)` — пресет кодировщика (`-preset ultrafast/fast/medium/...`).
- `.crf(value)` — фактор постоянного качества (`-crf`).
- `.video_bitrate(bitrate)` — битрейт видео (`-b:v`).
- `.audio_bitrate(bitrate)` — битрейт аудио (`-b:a`).
- `.fps(rate)` — выходная частота кадров (`-r`).
- `.resolution(w, h)` — выходное разрешение (`-s WxH`).
- `.no_video()` — отключить видео (`-vn`).
- `.no_audio()` — отключить аудио (`-an`).
- `.no_subtitles()` — отключить субтитры (`-sn`).
- `.map_stream(spec)` — маршрутизация потока (`-map spec`).
- `.metadata(key, value)` — тег метаданных (`-metadata key=value`).
- `.output_option(key, value)` — произвольная опция для данного выхода.
- `.output(target, **opts)` — финализирует конфигурацию выхода и добавляет целевой файл.

### Сборка и исполнение
- `.build(ffmpeg_path="ffmpeg") -> list[str]` — возвращает список аргументов для передачи в `asyncio.create_subprocess_exec`.
- `.build_pretty() -> str` — возвращает красиво форматированную команду с переносами строк и обратными слэшами для удобного логирования и отладки.
- `await .execute(...) -> ProcessResult` — запускает процесс асинхронно через `ProcessRunner`.

---

## 3. Пример использования

```python
import asyncio
from aio_ffmpeg import FFmpegCommand


async def main():
    cmd = (
        FFmpegCommand()
        .overwrite()
        .no_stdin()
        .progress()
        .stats_period(0.5)
        .hwaccel("cuda")
        .input("input.ts", ss="00:01:00", t="60")
        .video_codec("h264_nvenc")
        .preset("p4")
        .video_bitrate("4M")
        .audio_codec("aac")
        .audio_bitrate("192k")
        .metadata("encoder", "async-ffmpeg")
        .output("output.mp4")
    )

    print("Команда FFmpeg:")
    print(cmd.build_pretty())

    result = await cmd.execute()
    print("Код возврата:", result.exit_code)


asyncio.run(main())
```
