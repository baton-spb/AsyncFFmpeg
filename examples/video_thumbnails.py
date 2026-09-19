"""Пример извлечения кадров превью (скриншотов) из видео по таймкодам."""

import asyncio
import sys
from pathlib import Path

from aio_ffmpeg import FFmpegClient


async def _ensure_input_file(client: FFmpegClient, target_dir: Path) -> Path:
    """Создает синтетический тестовый видеофайл с динамическим счетчиком кадров.

    Args:
        client: Экземпляр FFmpegClient.
        target_dir: Директория для размещения синтетического файла.

    Returns:
        Путь к готовому входному файлу.
    """
    sample_file = target_dir / "sample_preview.mp4"
    if not sample_file.exists():
        print("Генерация синтетического тестового видео (5 сек)...")
        cmd = (
            client.create_command()
            .overwrite()
            .input("testsrc=size=1280x720:rate=30:duration=5.0", f="lavfi")
            .video_codec("libx264")
            .preset("ultrafast")
            .output(sample_file)
        )
        res = await cmd.execute()
        if not res.is_success:
            raise RuntimeError(f"Не удалось сгенерировать тестовый файл: {res.stderr_text}")
    return sample_file


async def main() -> None:
    """Точка входа демонстрационного скрипта создания превью."""
    work_dir = Path("./output_examples/thumbnails")
    work_dir.mkdir(parents=True, exist_ok=True)

    client = FFmpegClient()

    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
        if not input_path.exists():
            print(f"Ошибка: указанный файл не найден: {input_path}")
            sys.exit(1)
    else:
        input_path = await _ensure_input_file(client, work_dir.parent)

    print(f"Анализ видеофайла: {input_path}")
    info = await client.probe(input_path)
    duration = info.duration or 5.0
    print(f"Общая длительность: {duration:.2f} сек.")

    # Генерируем таймкоды: 20%, 50%, 80% от длительности
    timestamps = [duration * 0.2, duration * 0.5, duration * 0.8]

    print("\nИзвлечение превью кадров:")
    for i, ts in enumerate(timestamps, start=1):
        out_thumb = work_dir / f"thumb_{i}_{ts:.1f}s.jpg"
        print(f"[{i}/{len(timestamps)}] Захват кадра на {ts:.2f}с -> {out_thumb.name}...")

        res = await client.screenshot(
            input=input_path,
            output=out_thumb,
            timestamp=ts,
            resolution=(640, 360),
        )

        if res.is_success and out_thumb.exists():
            print(f"  [OK] Сохранено ({out_thumb.stat().st_size / 1024:.1f} KiB)")
        else:
            print(f"  [ERROR] Ошибка при захвате кадра: {res.stderr_text}")

    print(f"\nВсе превью успешно сохранены в каталоге: {work_dir.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
