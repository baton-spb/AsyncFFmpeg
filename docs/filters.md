# Построитель фильтров FilterGraph и фабричные функции

Модуль `async_ffmpeg.filters` предоставляет типизированную объектную модель графов фильтров FFmpeg, избавляющую разработчика от ручной конкатенации строк и ошибок экранирования специальных символов (запятых, точек с запятой, двоеточий).

---

## 1. Концепция: Filter, FilterChain, FilterGraph

FFmpeg использует три уровня абстракции для фильтрации:

1. **`Filter`** — отдельный фильтр с параметрами:
   - `Filter("scale", 1280, 720)` → `scale=1280:720`
   - `Filter("loudnorm", I=-14.0, LRA=7.0)` → `loudnorm=I=-14.0:LRA=7.0`
2. **`FilterChain`** — линейная последовательность фильтров, соединенных через запятую:
   - `[0:v]scale=1280:720,fps=30[out]`
3. **`FilterGraph`** / **`ComplexFilterGraph`** — граф из нескольких цепочек, разделенных точкой с запятой:
   - `[0:v]scale=1280:720[base];[1:v]scale=200:200[logo];[base][logo]overlay=10:10[out]`

---

## 2. Фабричные функции частых фильтров

В библиотеку встроены готовые фабричные функции, проверяющие аргументы:

### Видео фильтры
- `scale(width, height, force_original_aspect_ratio=None, flags=None)` — изменение размера.
- `crop(w, h, x=0, y=0)` — обрезка кадра.
- `pad(w, h, x=0, y=0, color="black")` — добавление полей.
- `fps(rate)` — изменение частоты кадров.
- `rotate(angle, fillcolor="black")` — поворот на угол в радианах.
- `vflip()` / `hflip()` — вертикальное и горизонтальное отражение.
- `transpose(direction=1)` — поворот на 90 градусов.
- `vtrim(start=None, end=None, duration=None)` — обрезка видео.
- `setpts(expr="PTS-STARTPTS")` — пересчет временных меток.
- `overlay(x=0, y=0, eof_action="repeat", shortest=False)` — наложение видеопотоков.
- `drawtext(text, x=10, y=10, fontsize=None, fontcolor=None, ...)` — наложение текста.
- `video_format(pix_fmts="yuv420p")` — выбор пиксельного формата.

### Аудио фильтры
- `volume(level)` — громкость (`volume(1.5)` или `volume("6dB")`).
- `loudnorm(i=-14.0, lra=7.0, tp=-1.0)` — нормализация громкости (EBU R128).
- `afade(type="in"|"out", start_time=0.0, duration=1.0)` — fade in / fade out.
- `atempo(speed)` — изменение скорости без питч-шифта (от 0.5 до 2.0).
- `atrim(start=None, end=None, duration=None)` — обрезка звука.
- `aresample(sample_rate)` — ресемплинг частоты дискретизации.
- `pan(layout, *matrix)` — маршрутизация каналов.

### Утилиты
- `concat(n=2, v=1, a=1)` — конкатенация медиапотоков.
- `split(outputs=2)` / `asplit(outputs=2)` — дублирование потоков.

---

## 3. Примеры построения графов

### Простой граф (Simple FilterGraph, для -vf / -af)

```python
from async_ffmpeg.filters import FilterGraph, scale, fps

fg = FilterGraph.simple(
    scale(1280, 720),
    fps(30),
)
print(str(fg))
# Результат: scale=1280:720,fps=30
```

### Комплексный граф (ComplexFilterGraph, для -filter_complex)

```python
from async_ffmpeg.filters import FilterGraph, scale, overlay

fg = (
    FilterGraph.complex()
    .chain(["0:v"], [scale(1920, 1080)], ["bg"])
    .chain(["1:v"], [scale(160, 90)], ["logo"])
    .chain(["bg", "logo"], [overlay("main_w-overlay_w-20", "20")], ["outv"])
)

print(str(fg))
# Результат:
# [0:v]scale=1920:1080[bg];[1:v]scale=160:90[logo];[bg][logo]overlay=main_w-overlay_w-20:20:eof_action=repeat[outv]
```
