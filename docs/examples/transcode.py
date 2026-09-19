"""Пример транскодирования видео с контролем параметров и прогрессом."""

import asyncio
import sys
from pathlib import Path

from aio_ffmpeg import FFmpegClient, ProgressInfo


async def main() -> None:
    if len(sys.argv) < 3:
        print("Использование: python transcode.py <входной_файл> <выходной_файл>")
        return

    in_file = Path(sys.argv[1])
    out_file = Path(sys.argv[2])

    client = FFmpegClient()

    def on_progress(p: ProgressInfo) -> None:
        pct_str = f"{p.percentage:.1f}%" if p.percentage is not None else "N/A"
        eta_str = f"{p.eta_seconds:.1f}s" if p.eta_seconds is not None else "N/A"
        print(
            f"\rПрогресс: {pct_str:>6} | Время: {p.out_time} | Скорость: {p.speed}x | ETA: {eta_str}",
            end="",
        )

    print(f"Начало транскодирования '{in_file}' -> '{out_file}'...")
    result = await client.transcode(
        input=in_file,
        output=out_file,
        video_codec="libx264",
        preset="faster",
        crf=23,
        resolution=(1280, 720),
        audio_codec="aac",
        audio_bitrate="128k",
        on_progress=on_progress,
    )
    print(f"\nЗавершено! Время кодирования: {result.duration_seconds:.2f} сек.")


if __name__ == "__main__":
    asyncio.run(main())
