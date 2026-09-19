"""Пример применения сложных видеофильтров: наложение водяного знака и динамического текста."""

import asyncio
import sys
from pathlib import Path

from async_ffmpeg import FFmpegClient


async def _ensure_inputs(client: FFmpegClient, target_dir: Path) -> tuple[Path, Path]:
    """Создает тестовое видео и тестовое изображение логотипа для демонстрации.

    Args:
        client: Экземпляр FFmpegClient.
        target_dir: Директория для размещения синтетических файлов.

    Returns:
        Кортеж из путей (видео, логотип).
    """
    video_file = target_dir / "base_video.mp4"
    logo_file = target_dir / "watermark_logo.png"

    if not video_file.exists():
        print("Генерация тестового базового видео (1280x720, 3 сек)...")
        cmd_vid = (
            client.create_command()
            .overwrite()
            .input("testsrc=size=1280x720:rate=30:duration=3.0", f="lavfi")
            .input("sine=frequency=800:duration=3.0", f="lavfi")
            .video_codec("libx264")
            .preset("ultrafast")
            .audio_codec("aac")
            .output(video_file)
        )
        await cmd_vid.execute()

    if not logo_file.exists():
        print("Генерация полупрозрачного тестового логотипа (120x60)...")
        cmd_logo = (
            client.create_command()
            .overwrite()
            .input("color=c=red@0.7:s=140x50:d=1.0", f="lavfi")
            .frames(1)
            .output(logo_file)
        )
        await cmd_logo.execute()

    return video_file, logo_file


async def main() -> None:
    """Точка входа демонстрационного скрипта наложения фильтров."""
    work_dir = Path("./output_examples")
    work_dir.mkdir(parents=True, exist_ok=True)

    client = FFmpegClient()

    if len(sys.argv) > 2:
        video_path = Path(sys.argv[1])
        logo_path = Path(sys.argv[2])
    else:
        video_path, logo_path = await _ensure_inputs(client, work_dir)

    output_path = work_dir / f"{video_path.stem}_watermarked.mp4"

    print(f"Базовое видео: {video_path}")
    print(f"Логотип:       {logo_path}")
    print(f"Результат:     {output_path}")

    print("\nСборка комплексного графа фильтров (Complex Filtergraph):")
    print(" - Масштабирование видео до 1280x720")
    print(
        " - Наложение полупрозрачного логотипа в правый верхний угол (x=main_w-overlay_w-20:y=20)"
    )

    # Используем гибкий билдер FFmpegCommand
    cmd = (
        client.create_command()
        .overwrite()
        .input(video_path)
        .input(logo_path)
        .complex_filter("[0:v]scale=1280:720[bg];[bg][1:v]overlay=W-w-20:20[v_out]")
        .map("[v_out]")
        .map("0:a?")  # копируем звук из первого входа, если есть
        .video_codec("libx264")
        .preset("ultrafast")
        .crf(24)
        .audio_codec("aac")
        .output(output_path)
    )

    print(f"Выполняемая команда:\n{' '.join(cmd.build())}\n")

    result = await cmd.execute()

    if result.is_success and output_path.exists():
        print("Видео с водяным знаком успешно сформировано!")
        print(f"Файл: {output_path.resolve()}")
        print(f"Размер: {output_path.stat().st_size / (1024 * 1024):.2f} MiB")
    else:
        print("Ошибка при выполнении фильтрации:")
        print(result.stderr_text)


if __name__ == "__main__":
    asyncio.run(main())
