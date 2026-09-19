# Аппаратное ускорение (Hardware Acceleration)

Модуль `async_ffmpeg.hardware` обеспечивает автоматическое обнаружение, верификацию и безопасное использование аппаратных ускорителей GPU / SoC (NVIDIA NVENC, Intel QSV, AMD AMF, Apple VideoToolbox, Windows MediaFoundation, D3D11VA, DXVA2, VAAPI).

---

## 1. Зачем нужна верификация аппаратного энкодера?

Наличие энкодера в списке `ffmpeg -encoders` не гарантирует его реальную работоспособность. Например:
- Устаревший видеодрайвер NVIDIA вызовет фатальный сбой: `Driver does not support required nvenc API version`.
- Видеокарта может быть отключена или не поддерживать кодек B-кадров.

Класс `HardwareAccel` предоставляет метод `test_encoder()`, который выполняет тестовое микрокодирование 1 синтетического кадра перед запуском длинных очередей. Если аппаратный энкодер недоступен, библиотека безопасно падает назад (fallback) на программный CPU-кодек (например, `libx264`).

---

## 2. Обнаружение аппаратных возможностей

```python
import asyncio
from async_ffmpeg import HardwareAccel

async def main():
    hw = HardwareAccel()
    caps = await hw.detect_hardware()

    print("Доступные платформы HW:", caps.available_accels)
    print("Поддержка CUDA:", caps.has_cuda)
    print("Поддержка NVENC:", caps.has_nvenc)
    print("Поддержка Intel QSV:", caps.has_qsv)
    print("Поддержка AMD AMF:", caps.has_amf)
    print("Поддержка D3D11VA:", caps.has_d3d11va)

    # Интеллектуальный подбор лучшего кодека
    best_h264 = await hw.best_encoder("h264", prefer_hw=True, verify_working=True)
    print(f"Выбранный H.264 кодировщик: {best_h264}")

asyncio.run(main())
```

---

## 3. Таблица поддерживаемых аппаратных платформ

| Платформа | Флаг HWAccel | Энкодер H.264 | Энкодер HEVC (H.265) | Энкодер AV1 |
|---|---|---|---|---|
| **NVIDIA** | `cuda` | `h264_nvenc` | `hevc_nvenc` | `av1_nvenc` |
| **Intel** | `qsv` | `h264_qsv` | `hevc_qsv` | `av1_qsv` |
| **AMD** | `amf` | `h264_amf` | `hevc_amf` | `av1_amf` |
| **Apple Silicon** | `videotoolbox` | `h264_videotoolbox` | `hevc_videotoolbox` | `av1_videotoolbox` |
| **Windows** | `d3d11va` / `dxva2` | `h264_mf` | `hevc_mf` | `av1_mf` |
| **Linux** | `vaapi` | `h264_vaapi` | `hevc_vaapi` | `av1_vaapi` |

---

## 4. Использование в MediaPipeline

```python
from async_ffmpeg import MediaPipeline

pipeline = (
    MediaPipeline("source.mkv")
    .hwaccel("cuda", device="0", output_format="cuda")
    .video_codec("h264_nvenc")
    .preset("p4")
    .output("output.mp4")
)
```
