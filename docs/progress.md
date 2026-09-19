# Мониторинг прогресса в реальном времени

Библиотека `async-ffmpeg` использует встроенный протокол FFmpeg `-progress pipe:1` для получения чистых, структурированных данных о ходе выполнения процесса вместо ненадежного парсинга текста из stderr.

---

## 1. Протокол -progress pipe:1

При передаче флага `-progress pipe:1` FFmpeg периодически выдает в stdout ключ-значения в следующем формате:
```ini
frame=1420
fps=59.80
stream_0_0_q=28.0
bitrate=2540.5kbits/s
total_size=8492040
out_time_us=24500000
out_time_ms=24500000
out_time=00:00:24.500000
dup_frames=0
drop_frames=0
speed=1.95x
progress=continue
```

В конце обработки отправляется строка `progress=end`.

---

## 2. Структура данных ProgressInfo

Класс `ProgressInfo` инкапсулирует статистику текущего среза времени:

- `frame: int` — текущий номер обработанного кадра.
- `fps: float` — мгновенная скорость обработки кадров в секунду.
- `out_time_seconds: float` — текущая позиция в выходном медиапотоке (в секундах).
- `out_time: str` — строковое представление времени (`"HH:MM:SS.microseconds"`).
- `total_size: int` — накопленный объем записанных данных в байтах.
- `bitrate_kbits: float` — текущий битрейт потока в кбит/с.
- `speed: float | None` — коэффициент скорости относительно реального времени (например `2.5` означает 2.5x).
- `is_finished: bool` — флаг завершения (`True` при `progress=end`).
- `percentage: float | None` — процент завершения (от `0.0` до `100.0`). Доступен, если известна общая длительность входного файла.
- `eta_seconds: float | None` — расчетное оставшееся время до окончания обработки.

---

## 3. Использование в коде

### С FFmpegClient (автоматический расчет процентов)

`FFmpegClient` автоматически запрашивает длительность файла через `FFprobe` и передает в парсер, благодаря чему в коллбэке сразу доступно поле `percentage`:

```python
import asyncio
from async_ffmpeg import FFmpegClient, ProgressInfo


async def main():
    client = FFmpegClient()

    def handle_progress(p: ProgressInfo) -> None:
        if p.percentage is not None:
            bar = "#" * int(p.percentage // 5)
            print(
                f"\r[{bar:<20}] {p.percentage:.1f}% | ETA: {p.eta_seconds:.1f}s | FPS: {p.fps:.1f}",
                end="",
            )
        else:
            print(f"\rВремя: {p.out_time} | Скорость: {p.speed}x", end="")

    await client.transcode(
        "movie.mkv",
        "movie.mp4",
        on_progress=handle_progress,
    )
    print("\nОбработка завершена!")


asyncio.run(main())
```

### С FFmpegCommand (низкоуровневое управление)

```python
cmd = (
    FFmpegCommand()
    .overwrite()
    .progress()
    .stats_period(0.25)  # интервал опроса 250 мс
    .input("input.mp4")
    .video_codec("libx264")
    .output("output.mp4")
)

await cmd.execute(
    total_duration=120.5,  # ручная передача длительности для расчета процентов
    on_progress=handle_progress,
)
```
