# Исследование FFmpeg / FFprobe для async-ffmpeg

> **Дата:** 2026-09-19
> **Версия FFmpeg:** 9.0.1-full_build (gyan.dev, gcc 16.1.0)
> **Версия FFprobe:** 9.0.1-full_build
> **ОС тестирования:** Windows 11

---

## 1. Архитектура FFmpeg CLI

### 1.1 Конвейер обработки

FFmpeg работает по конвейерной архитектуре:

```
Demuxer → Decoder → [Filtergraph] → Encoder → Muxer
```

**Ключевые компоненты:**

| Компонент | Роль | Входные данные | Выходные данные |
|-----------|------|----------------|-----------------|
| **Demuxer** | Разбирает контейнер (mp4, mkv и т.д.) | Файл / URL / pipe | Пакеты (packets) |
| **Decoder** | Декодирует сжатые пакеты | Пакеты | Сырые кадры (frames) |
| **Filtergraph** | Обработка и трансформация кадров | Сырые кадры | Обработанные кадры |
| **Encoder** | Кодирует кадры обратно | Обработанные кадры | Сжатые пакеты |
| **Muxer** | Записывает в контейнер | Пакеты | Файл / pipe / URL |

### 1.2 Streamcopy (копирование без перекодирования)

При `-c copy` конвейер упрощается:

```
Demuxer → Muxer  (без Decoder/Encoder/Filtergraph)
```

**Ключевые свойства streamcopy:**
- Мгновенная скорость (нет декодирования/кодирования)
- Нулевая потеря качества
- Невозможно применять фильтры
- Может не работать при несовместимости форматов контейнеров

### 1.3 Порядок аргументов CLI

**КРИТИЧЕСКИ ВАЖНО** — FFmpeg требует строгого порядка аргументов:

```
ffmpeg [global_options] {[input_options] -i input} ... {[output_options] output} ...
```

Детальный порядок:
1. **Глобальные опции** (`-y`, `-n`, `-progress`, `-stats_period`, `-loglevel`, `-nostdin`)
2. **Опции входного файла** (`-ss`, `-t`, `-f`, `-hwaccel`) — перед `-i`
3. **Входные файлы** (`-i input.mp4`)
4. **Фильтры** (`-vf`, `-af`, `-filter_complex`)
5. **Опции выходного файла** (`-c:v`, `-c:a`, `-b:v`, `-r`, `-s`, `-map`)
6. **Выходные файлы** (`output.mp4`)

**Пример полной команды:**
```bash
ffmpeg -y -loglevel quiet -progress pipe:1 -stats_period 0.5 \
       -ss 10 -t 30 -i input.mp4 \
       -vf "scale=1280:720" \
       -c:v libx264 -preset medium -crf 23 \
       -c:a aac -b:a 128k \
       output.mp4
```

---

## 2. Протокол прогресса (-progress)

### 2.1 Формат вывода

FFmpeg поддерживает машиночитаемый вывод прогресса через флаг `-progress url`.

При `-progress pipe:1` прогресс пишется в stdout в формате `key=value`:

```
frame=16
fps=0.00
stream_0_0_q=29.0
bitrate=   0.8kbits/s
total_size=48
out_time_us=466667
out_time_ms=466667
out_time=00:00:00.466667
dup_frames=0
drop_frames=0
speed=2.32x
progress=continue
```

### 2.2 Ключи прогресса

| Ключ | Тип | Описание |
|------|-----|----------|
| `frame` | int | Номер текущего обработанного кадра |
| `fps` | float | Скорость кодирования (кадров/сек) |
| `stream_N_M_q` | float | Качество потока N, вход M (quantizer) |
| `bitrate` | string | Текущий битрейт выхода (e.g. `0.8kbits/s`, `N/A`) |
| `total_size` | int/string | Текущий размер файла в байтах (или `N/A`) |
| `out_time_us` | int | Текущая позиция в микросекундах |
| `out_time_ms` | int | Текущая позиция в миллисекундах |
| `out_time` | string | Текущая позиция в формате `HH:MM:SS.ffffff` |
| `dup_frames` | int | Количество дублированных кадров |
| `drop_frames` | int | Количество пропущенных кадров |
| `speed` | string | Скорость обработки (e.g. `2.32x`, `N/A`) |
| `progress` | string | `continue` или `end` — маркер конца блока |

### 2.3 Ключевые наблюдения из экспериментов

1. **Блоки разделяются строкой `progress=`** — это последний ключ в каждом блоке
2. **`progress=continue`** — промежуточный отчёт
3. **`progress=end`** — финальный отчёт, процесс завершается
4. **Для аудио-only** — поле `frame` отсутствует
5. **`bitrate` и `total_size`** — могут быть `N/A` при выводе в `/dev/null` или `NUL`
6. **`speed`** — может содержать пробелы (e.g. `speed=  15x`), нужна обрезка

### 2.4 Управление частотой

```bash
-stats_period 0.5    # Обновление каждые 0.5 сек (по умолчанию)
-stats_period 0.2    # Более частые обновления
-stats_period 2.0    # Реже — для длинных задач
```

### 2.5 Вычисление процента завершения

Для вычисления процента нужно знать **общую длительность** (из ffprobe):

```python
percent = (out_time_us / total_duration_us) * 100
```

---

## 3. FFprobe — анализ медиафайлов

### 3.1 Основные флаги

```bash
ffprobe -v quiet -print_format json -show_format -show_streams [-show_chapters] input.mp4
```

| Флаг | Описание |
|------|----------|
| `-v quiet` | Подавить весь лишний вывод |
| `-v error` | Только ошибки |
| `-print_format json` | Вывод в JSON |
| `-show_format` | Информация о контейнере |
| `-show_streams` | Информация о потоках |
| `-show_chapters` | Информация о главах |
| `-select_streams v` | Только видео-потоки |
| `-select_streams a` | Только аудио-потоки |
| `-show_entries` | Выбрать конкретные поля |

### 3.2 Структура JSON-вывода

#### Полный вывод (-show_format -show_streams)

```json
{
    "streams": [
        {
            "index": 0,
            "codec_name": "h264",
            "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
            "profile": "Constrained Baseline",
            "codec_type": "video",
            "codec_tag_string": "avc1",
            "width": 640,
            "height": 480,
            "coded_width": 640,
            "coded_height": 480,
            "has_b_frames": 0,
            "sample_aspect_ratio": "1:1",
            "display_aspect_ratio": "4:3",
            "pix_fmt": "yuv420p",
            "level": 30,
            "field_order": "progressive",
            "r_frame_rate": "30/1",
            "avg_frame_rate": "30/1",
            "time_base": "1/15360",
            "start_time": "0.000000",
            "duration": "2.000000",
            "bit_rate": "8724",
            "nb_frames": "60",
            "disposition": {
                "default": 1,
                "dub": 0,
                "...": "..."
            },
            "tags": {
                "language": "und",
                "handler_name": "VideoHandler",
                "encoder": "Lavc63.1.101 libx264"
            }
        },
        {
            "index": 1,
            "codec_name": "aac",
            "codec_long_name": "AAC (Advanced Audio Coding)",
            "profile": "LC",
            "codec_type": "audio",
            "sample_fmt": "fltp",
            "sample_rate": "44100",
            "channels": 1,
            "channel_layout": "mono",
            "duration": "2.000000",
            "bit_rate": "69694",
            "nb_frames": "88",
            "tags": {
                "language": "und",
                "handler_name": "SoundHandler"
            }
        }
    ],
    "format": {
        "filename": "test_sample.mp4",
        "nb_streams": 2,
        "nb_programs": 0,
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "format_long_name": "QuickTime / MOV",
        "start_time": "0.000000",
        "duration": "2.000000",
        "size": "23000",
        "bit_rate": "92000",
        "probe_score": 100,
        "tags": {
            "major_brand": "isom",
            "title": "Test Video",
            "artist": "Test Artist",
            "encoder": "Lavf63.1.101"
        }
    }
}
```

#### Выборочные поля (-show_entries)

```bash
ffprobe -v error -show_entries stream=codec_name,codec_type,width,height,sample_rate,channels,bit_rate,duration -of json input.mp4
```

Вывод:
```json
{
    "programs": [],
    "stream_groups": [],
    "streams": [
        {
            "codec_name": "h264",
            "codec_type": "video",
            "width": 640,
            "height": 480,
            "duration": "2.000000",
            "bit_rate": "8724"
        },
        {
            "codec_name": "aac",
            "codec_type": "audio",
            "sample_rate": "44100",
            "channels": 1,
            "duration": "2.000000",
            "bit_rate": "69694"
        }
    ]
}
```

### 3.3 Важные типы полей

- `duration` — всегда строка (`"2.000000"`)
- `width`, `height`, `channels` — числа (int)
- `bit_rate`, `sample_rate` — строки
- `nb_frames` — строка
- Некоторые поля могут отсутствовать для определённых кодеков

---

## 4. Filtergraph (фильтры)

### 4.1 Простые фильтры (Simple filtergraph)

Привязаны к конкретному потоку. Используют `-vf` (видео) и `-af` (аудио):

```bash
ffmpeg -i input.mp4 -vf "scale=1280:720,fps=30" output.mp4
ffmpeg -i input.mp4 -af "volume=1.5,atempo=2.0" output.mp3
```

Формат: `фильтр1=аргументы,фильтр2=аргументы,...`

### 4.2 Сложные фильтры (Complex filtergraph)

Используют `-filter_complex` и ссылки на потоки `[label]`:

```bash
ffmpeg -i input1.mp4 -i input2.mp4 \
  -filter_complex "[0:v]scale=320:240[bg];[1:v]scale=80:60[fg];[bg][fg]overlay=10:10[out]" \
  -map "[out]" -c:v libx264 output.mp4
```

**Синтаксис:**
- `[0:v]` — ссылка на видео-поток из входного файла 0
- `[label]` — именованный выход фильтра
- `;` — разделитель цепочек фильтров
- `,` — разделитель фильтров в одной цепочке

### 4.3 Ключевые фильтры (доступные в FFmpeg 9.0.1)

#### Видео-фильтры
| Фильтр | Тип | Описание |
|--------|-----|----------|
| `scale` | V→V | Масштабирование видео |
| `crop` | V→V | Обрезка видео |
| `overlay` | VV→V | Наложение видео поверх другого |
| `drawtext` | V→V | Отрисовка текста на видео |
| `rotate` | V→V | Вращение |
| `pad` | V→V | Добавление полей |
| `fps` | V→V | Изменение частоты кадров |
| `trim` | V→V | Обрезка по времени |
| `setpts` | V→V | Изменение временных меток |
| `concat` | NV→V | Конкатенация сегментов |
| `split` | V→VV | Дублирование потока |
| `boxblur` | V→V | Размытие |
| `unsharp` | V→V | Повышение резкости |
| `yadif` | V→V | Деинтерлейсинг |
| `nlmeans` | V→V | Шумоподавление |
| `colorbalance` | V→V | Цветокоррекция |

#### Аудио-фильтры
| Фильтр | Тип | Описание |
|--------|-----|----------|
| `volume` | A→A | Регулировка громкости |
| `loudnorm` | A→A | Нормализация громкости (EBU R128) |
| `atempo` | A→A | Изменение темпа аудио |
| `afade` | A→A | Затухание/нарастание |
| `amix` | AA→A | Микширование аудио-потоков |
| `aresample` | A→A | Ресемплирование |
| `amerge` | AA→A | Объединение каналов |

### 4.4 Фильтр concat

Особый фильтр для конкатенации — принимает **N сегментов**:

```
concat AVOptions:
  n  <int>  число сегментов (по умолчанию: 2)
  v  <int>  число видео-потоков (по умолчанию: 1)
  a  <int>  число аудио-потоков (по умолчанию: 0)
  unsafe <boolean>  разрешить небезопасный режим (по умолчанию: false)
```

### 4.5 Фильтр loudnorm (EBU R128)

Двухпроходная нормализация громкости:

```
loudnorm AVOptions:
  I   <double>  целевая интегральная громкость (LUFS) (по умолчанию: -24)
  LRA <double>  целевой диапазон громкости (LU) (по умолчанию: 7)
  TP  <double>  целевой true peak (dBTP) (по умолчанию: -2)
```

---

## 5. Управление процессом

### 5.1 Коды возврата (Exit Codes)

На основе экспериментов на Windows:

| Сценарий | Exit Code |
|----------|-----------|
| Успешное завершение | `0` |
| Входной файл не найден | `-2` (ENOENT в Windows) |
| Несуществующий кодек | ненулевой (varies) |
| Файл существует + `-n` | `0` (но stderr сообщает об ошибке) |

**ВАЖНО:** Коды возврата НЕ стандартизированы в FFmpeg. Основной принцип:
- `0` = успех
- Любое другое значение = ошибка
- Тип ошибки определяется по stderr, не по коду возврата

### 5.2 Грациозное завершение процесса

#### Метод 1: Отправка 'q' в stdin (РЕКОМЕНДУЕТСЯ)

```python
process.stdin.write(b'q')
process.stdin.flush()
await process.wait()
```

**Почему это лучший метод:**
- FFmpeg корректно финализирует заголовки файлов (moov atom в MP4)
- Работает на всех ОС
- Не вызывает повреждения файла

#### Метод 2: SIGINT (Unix) / Ctrl+C (Windows)

На Unix:
```python
process.send_signal(signal.SIGINT)
```

На Windows — сложнее, требует `GenerateConsoleCtrlEvent` или `AttachConsole`.

#### НЕЛЬЗЯ делать:
- `process.kill()` / `process.terminate()` без крайней необходимости — повреждает файлы
- `taskkill /F` на Windows — мгновенное уничтожение без очистки

### 5.3 Флаги для не-интерактивного режима

```bash
-nostdin    # Отключить чтение stdin
-y          # Перезаписывать выходные файлы без запроса
-n          # НЕ перезаписывать (exit при существующем файле)
```

**ВАЖНО для автоматизации:** При запуске FFmpeg из Python ВСЕГДА нужно:
1. Использовать `-nostdin` ИЛИ подключить stdin pipe
2. Использовать `-y` (или `-n`) — иначе FFmpeg будет ждать подтверждения

---

## 6. Аппаратное ускорение

### 6.1 Доступные методы (FFmpeg 9.0.1 Windows)

```
cuda, vaapi, dxva2, qsv, d3d11va, opencl, vulkan, d3d12va, amf
```

### 6.2 Ключевые кодеки с HW-ускорением

| API | Кодирование | Декодирование |
|-----|-------------|---------------|
| **NVIDIA NVENC** | h264_nvenc, hevc_nvenc, av1_nvenc | h264_cuvid, hevc_cuvid, av1_cuvid |
| **AMD AMF** | h264_amf, hevc_amf, av1_amf | h264_amf, hevc_amf, vp9_amf, av1_amf |
| **Intel QSV** | h264_qsv, hevc_qsv | h264_qsv, hevc_qsv, av1_qsv, vp8_qsv, vp9_qsv |
| **D3D11/DXVA2** | — | Автоматическое декодирование через `-hwaccel` |

### 6.3 Использование HW-ускорения

```bash
# Автоматическое HW-декодирование
ffmpeg -hwaccel auto -i input.mp4 -c:v libx264 output.mp4

# NVENC кодирование
ffmpeg -i input.mp4 -c:v h264_nvenc -preset p7 output.mp4

# Full HW pipeline (NVIDIA)
ffmpeg -hwaccel cuda -hwaccel_output_format cuda -i input.mp4 -c:v h264_nvenc output.mp4
```

### 6.4 Обнаружение доступных HW-ускорителей

```bash
ffmpeg -hwaccels                     # Список методов
ffmpeg -encoders | grep nvenc        # Проверка кодировщиков
ffmpeg -decoders | grep cuvid        # Проверка декодировщиков
```

---

## 7. Ключевые кодеки

### 7.1 Видео-кодеки

| Кодек | Encoder | Описание | Лицензия |
|-------|---------|----------|----------|
| H.264/AVC | `libx264` | Самый распространённый | GPL |
| H.265/HEVC | `libx265` | Следующее поколение | GPL |
| VP8 | `libvpx` | Открытый (Google) | BSD |
| VP9 | `libvpx-vp9` | Открытый, лучше H.264 | BSD |
| AV1 | `libaom-av1`, `libsvtav1` | Открытый, лучше H.265 | BSD |

### 7.2 Аудио-кодеки

| Кодек | Encoder | Описание |
|-------|---------|----------|
| AAC | `aac` (native) | Самый распространённый |
| MP3 | `libmp3lame` | Устаревший, но популярный |
| Opus | `libopus` | Лучший для VoIP/streaming |
| Vorbis | `libvorbis` | Открытый, OGG |

---

## 8. Patterns для asyncio

### 8.1 Запуск процесса

```python
process = await asyncio.create_subprocess_exec(
    'ffmpeg', *args,
    stdin=asyncio.subprocess.PIPE,    # Для graceful shutdown
    stdout=asyncio.subprocess.PIPE,   # Для прогресса (-progress pipe:1)
    stderr=asyncio.subprocess.PIPE,   # Для логов ошибок
)
```

### 8.2 Параллельное чтение stdout и stderr

**КРИТИЧЕСКИ ВАЖНО:** Нельзя читать stdout и stderr последовательно — deadlock!

Варианты:
1. `communicate()` — читает оба, но ждёт завершения
2. Параллельные `asyncio.Task` для чтения каждого потока
3. `process.stdout.readline()` в цикле для потокового чтения прогресса

```python
async def _read_progress(process):
    """Потоковое чтение прогресса из stdout."""
    block = {}
    async for line in process.stdout:
        line = line.decode().strip()
        if '=' in line:
            key, _, value = line.partition('=')
            block[key] = value.strip()
            if key == 'progress':
                yield dict(block)
                block.clear()
```

### 8.3 Ограничение параллелизма

```python
semaphore = asyncio.Semaphore(max_concurrent)

async def process_file(input_path):
    async with semaphore:
        proc = await asyncio.create_subprocess_exec(...)
        await proc.communicate()
```

### 8.4 Таймауты

```python
try:
    await asyncio.wait_for(process.communicate(), timeout=300)
except asyncio.TimeoutError:
    process.stdin.write(b'q')  # Graceful shutdown
    await asyncio.wait_for(process.wait(), timeout=5)
    if process.returncode is None:
        process.kill()  # Последний resort
```

### 8.5 Группы процессов (Unix)

На Unix для корректного завершения дочерних процессов:

```python
process = await asyncio.create_subprocess_exec(
    *cmd,
    start_new_session=True,  # Unix only: создаёт новую группу процессов
)
# Для завершения всей группы:
os.killpg(os.getpgid(process.pid), signal.SIGINT)
```

На Windows эквивалент — `CREATE_NEW_PROCESS_GROUP`:
```python
import subprocess
# При использовании create_subprocess_exec нет прямого аналога,
# но можно использовать creationflags через subprocess.Popen
```

---

## 9. Форматы контейнеров

### 9.1 Основные форматы

| Формат | Расширения | Видео-кодеки | Аудио-кодеки | Особенности |
|--------|-----------|--------------|--------------|-------------|
| MP4 | .mp4, .m4a, .m4v | H.264, H.265, AV1 | AAC, AC3, MP3 | Наиболее совместимый |
| MKV | .mkv, .mka | Все | Все | Максимальная гибкость |
| WebM | .webm | VP8, VP9, AV1 | Vorbis, Opus | Web-оптимизирован |
| MOV | .mov | H.264, ProRes | AAC, PCM | Apple экосистема |
| AVI | .avi | Все | Все | Устаревший |
| FLV | .flv | H.264 | AAC, MP3 | Streaming |
| TS | .ts | H.264, H.265 | AAC, AC3, MP2 | Broadcast/HLS |
| OGG | .ogg, .ogv | Theora, VP8 | Vorbis, Opus | Открытый |

### 9.2 Только аудио

| Формат | Расширения | Кодеки |
|--------|-----------|--------|
| MP3 | .mp3 | MP3 |
| FLAC | .flac | FLAC (lossless) |
| WAV | .wav | PCM (lossless) |
| OGG/Opus | .opus | Opus |
| M4A | .m4a | AAC |

---

## 10. Конкурентный анализ

### 10.1 Существующие Python-обёртки

| Библиотека | Подход | Async | Минусы |
|-----------|--------|-------|--------|
| `python-ffmpeg` | subprocess, fluent API | Да (частичный) | API не type-safe |
| `ffmpeg-python` | subprocess, fluent API | Нет | Заброшен |
| `PyAV` | C API bindings | Нет | Другая ниша (frame-level) |
| `ffmpeg-asyncio` | asyncio subprocess | Да | Примитивный, нет builder |

### 10.2 Наши преимущества

1. **Строгая типизация** — dataclass модели, generic types
2. **Двухуровневый API** — low-level builder + high-level operations
3. **Machine-readable прогресс** — через `-progress pipe:1`
4. **FilterGraph builder** — type-safe конструктор фильтров
5. **MediaPipeline** — цепочка операций в один процесс FFmpeg
6. **Hardware acceleration discovery** — автоопределение HW
7. **Интеграция с async-yt-dlp** — опциональная, без circular deps
8. **Python 3.14+** — используем новейшие возможности языка

---

## 11. Критические выводы

### 11.1 Для ProcessRunner

- Использовать `asyncio.create_subprocess_exec()`, НЕ `shell=True`
- Всегда передавать `stdin=PIPE` для graceful shutdown через 'q'
- Читать stdout и stderr ПАРАЛЛЕЛЬНО (через asyncio tasks)
- На Windows нет простого способа отправить SIGINT — использовать stdin 'q'
- Обязательно `-nostdin` если не планируем управлять через stdin
- Лучший паттерн: `-nostdin -y -progress pipe:1 -loglevel error`

### 11.2 Для Command Builder

- Строгий порядок аргументов — нарушение = ошибка
- `-map` нужен для ручного управления потоками
- Stream specifiers (`-c:v`, `-c:a`, `-b:v:0`) — мощный механизм
- `-filter_complex` и `-vf`/`-af` взаимоисключающие для одного потока

### 11.3 Для Progress

- Парсить по `progress=continue|end` маркерам
- `speed` содержит trailing пробелы — `.strip()` обязателен
- `bitrate` и `total_size` могут быть `N/A`
- `out_time_us` — наиболее надёжный для вычисления процента
- Для аудио-only нет поля `frame`

### 11.4 Для FFprobe

- Всегда `-v quiet -print_format json`
- Поля `duration`, `bit_rate`, `sample_rate` — строки в JSON, не числа
- Некоторые поля опциональны (зависят от формата/кодека)
- `-show_entries` для минимизации объёма данных
