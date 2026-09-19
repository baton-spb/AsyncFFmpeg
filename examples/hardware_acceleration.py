"""Пример инспекции аппаратного ускорения (GPU) и автоматического выбора кодека."""

import asyncio
from pathlib import Path

from async_ffmpeg import FFmpegClient, HardwareAccel


async def main() -> None:
    """Точка входа демонстрационного скрипта аппаратного ускорения."""
    work_dir = Path("./output_examples")
    work_dir.mkdir(parents=True, exist_ok=True)

    client = FFmpegClient()
    hw = HardwareAccel(ffmpeg_path=client.ffmpeg_path)

    print("Анализ доступных аппаратных возможностей FFmpeg...")
    caps = await hw.detect_hardware()

    print(f"\nПоддерживаемые методы ускорения (HW Accels): {', '.join(caps.available_accels) or 'нет'}")
    hw_encoders = [e.name for e in caps.encoders if e.is_hardware]
    print(f"Доступные аппаратные энкодеры ({len(hw_encoders)} шт.):")
    for enc in sorted(hw_encoders):
        print(f"  [GPU] {enc}")

    print("\nИнтеллектуальный подбор кодеков:")
    for standard_codec in ("h264", "hevc", "av1"):
        best = await hw.best_encoder(standard_codec)
        is_hw = (
            best != f"lib{standard_codec}"
            and best != "libx264"
            and best != "libx265"
            and best != "libsvtav1"
        )
        icon = "[GPU ускорение]" if is_hw else "[CPU программный fallback]"
        print(f" - {standard_codec.upper():<5} -> {best:<18} {icon}")

    # Демонстрация кодирования с выбранным кодеком
    chosen_codec = await hw.best_encoder("h264")
    output_file = work_dir / f"hwaccel_test_{chosen_codec}.mp4"

    print(f"\nТестовое кодирование через энкодер '{chosen_codec}'...")
    cmd = (
        client.create_command()
        .overwrite()
        .input("testsrc=size=1280x720:rate=30:duration=2.0", f="lavfi")
        .video_codec(chosen_codec)
        .output(output_file)
    )

    res = await cmd.execute()
    if res.is_success and output_file.exists():
        print(f"Успешно закодировано через {chosen_codec}!")
        print(f"Файл: {output_file.name} ({output_file.stat().st_size / 1024:.1f} KiB)")
        print(f"Время кодирования: {res.duration_seconds:.2f} сек.")
    else:
        print(f"Ошибка при кодировании через {chosen_codec}:")
        print(res.stderr_text)


if __name__ == "__main__":
    asyncio.run(main())
