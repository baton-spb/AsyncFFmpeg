"""Пример объединения нескольких видеосегментов (конкатенация) в единый файл."""

import asyncio
from pathlib import Path

from aio_ffmpeg import FFmpegClient, ProgressInfo


async def _generate_segments(client: FFmpegClient, target_dir: Path) -> list[Path]:
    """Генерирует три разноцветных синтетических сегмента для демонстрации склейки.

    Args:
        client: Экземпляр FFmpegClient.
        target_dir: Директория для размещения сегментов.

    Returns:
        Список путей к сформированным сегментам.
    """
    colors = [("red", 600), ("green", 800), ("blue", 1000)]
    segment_paths: list[Path] = []

    for i, (color, freq) in enumerate(colors, start=1):
        seg_file = target_dir / f"segment_{i}_{color}.mp4"
        if not seg_file.exists():
            print(f"Генерация сегмента #{i} ({color}, 1.5 сек)...")
            cmd = (
                client.create_command()
                .overwrite()
                .input(f"color=c={color}:s=640x360:d=1.5", f="lavfi")
                .input(f"sine=frequency={freq}:d=1.5", f="lavfi")
                .video_codec("libx264")
                .preset("ultrafast")
                .audio_codec("aac")
                .output(seg_file)
            )
            await cmd.execute()
        segment_paths.append(seg_file)

    return segment_paths


async def main() -> None:
    """Точка входа демонстрационного скрипта конкатенации."""
    work_dir = Path("./output_examples/concat")
    work_dir.mkdir(parents=True, exist_ok=True)

    client = FFmpegClient()

    segments = await _generate_segments(client, work_dir)
    output_file = work_dir / "concatenated_result.mp4"

    print(f"\nСегменты для объединения ({len(segments)} шт.):")
    for s in segments:
        print(f" - {s.name}")

    print(f"\nВыходной файл: {output_file}")
    print("Запуск конкатенации...")

    def on_progress(p: ProgressInfo) -> None:
        if p.out_time:
            print(
                f"\rОбработано времени: {p.out_time} | Скорость: {p.speed or 'N/A'}",
                end="",
                flush=True,
            )

    result = await client.concat(
        inputs=segments,
        output=output_file,
        on_progress=on_progress,
    )

    print()
    if result.is_success and output_file.exists():
        info = await client.probe(output_file)
        print("Конкатенация успешно завершена!")
        print(f"Результирующая длительность: {info.duration or 0:.2f} сек.")
        print(f"Размер: {output_file.stat().st_size / (1024 * 1024):.2f} MiB")
    else:
        print("Ошибка при склейке:")
        print(result.stderr_text)


if __name__ == "__main__":
    asyncio.run(main())
