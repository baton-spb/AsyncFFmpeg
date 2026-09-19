"""Пример наложения водяного знака через MediaPipeline."""

import asyncio
import sys
from pathlib import Path

from aio_ffmpeg import MediaPipeline


async def main() -> None:
    if len(sys.argv) < 4:
        print("Использование: python watermark.py <видео> <логотип_png> <выходной_файл>")
        return

    in_video = Path(sys.argv[1])
    logo = Path(sys.argv[2])
    out_video = Path(sys.argv[3])

    pipeline = (
        MediaPipeline(in_video)
        .watermark(logo, position="bottom-right", margin=20, opacity=0.8)
        .video_codec("libx264", preset="faster", crf=22)
        .audio_codec("copy")
        .output(out_video)
    )

    print("Запуск конвейера с наложением логотипа...")
    res = await pipeline.run()
    if res.success:
        print(f"Файл успешно сохранен в '{out_video}' за {res.duration_seconds:.2f} сек.")
    else:
        print("Ошибка при обработке:")
        print(res.stderr_text)


if __name__ == "__main__":
    asyncio.run(main())
