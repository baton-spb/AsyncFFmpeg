"""Пример детального анализа медиафайла с помощью FFprobe."""

import asyncio
import sys
from pathlib import Path

from aio_ffmpeg import FFmpegClient


async def main() -> None:
    if len(sys.argv) < 2:
        print("Использование: python probe_media.py <путь_к_медиафайлу>")
        return

    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"Ошибка: файл '{file_path}' не найден.")
        return

    client = FFmpegClient()
    info = await client.probe(file_path)

    print("=" * 60)
    print(f"Файл: {info.format.filename}")
    print(f"Формат: {info.format.format_name} ({info.format.format_long_name})")
    print(f"Длительность: {info.duration:.2f} сек")
    print(f"Размер: {info.format.size or 0 / (1024 * 1024):.2f} МБ")
    print(f"Битрейт: {info.format.bit_rate or 0 // 1000} кбит/с")
    print("=" * 60)

    if info.video_streams:
        print("\n--- Видеопотоки ---")
        for i, vs in enumerate(info.video_streams):
            fps_val = f"{vs.frame_rate:.2f}" if vs.frame_rate else "N/A"
            print(
                f"  [#{i}] Кодек: {vs.codec_name} | {vs.width}x{vs.height} | {fps_val} fps | PixFmt: {vs.pix_fmt}"
            )

    if info.audio_streams:
        print("\n--- Аудиопотоки ---")
        for i, as_ in enumerate(info.audio_streams):
            br_val = f"{as_.bit_rate // 1000}k" if as_.bit_rate else "N/A"
            print(
                f"  [#{i}] Кодек: {as_.codec_name} | Каналов: {as_.channels} ({as_.channel_layout}) | Частота: {as_.sample_rate} Гц | Битрейт: {br_val}"
            )

    if info.subtitle_streams:
        print("\n--- Субтитры ---")
        for i, ss in enumerate(info.subtitle_streams):
            lang = ss.tags.get("language", "und")
            print(f"  [#{i}] Кодек: {ss.codec_name} | Язык: {lang}")


if __name__ == "__main__":
    asyncio.run(main())
