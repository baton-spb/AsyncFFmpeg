"""Пример сквозного конвейера: скачивание через async-yt-dlp и постобработка через async-ffmpeg."""

import asyncio
import sys
from pathlib import Path

from async_ffmpeg import FFmpegClient
from async_ffmpeg.integration import extract_download_audio, process_download_result


async def main() -> None:
    """Точка входа демонстрационного скрипта связки async-yt-dlp и async-ffmpeg."""
    try:
        from async_yt_dlp import AsyncYTDLP, YTDLPOptions  # type: ignore[import-not-found]
    except ImportError:
        print("Ошибка: библиотека async-yt-dlp не установлена.")
        print("Установите ее командой: pip install async-yt-dlp или uv add async-yt-dlp")
        sys.exit(1)

    work_dir = Path("./output_examples/ytdlp_pipeline")
    work_dir.mkdir(parents=True, exist_ok=True)

    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/watch?v=BaW_jenozKc"

    print(f"1. Скачивание исходного медиа через AsyncYTDLP: {url}")
    ytdlp_opts = YTDLPOptions(
        output_path=work_dir,
        output_template="%(id)s_raw.%(ext)s",
        format="bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    )

    async with AsyncYTDLP(default_options=ytdlp_opts) as ytdlp:
        dl_result = await ytdlp.download(url)

    print("\n[OK] Скачивание завершено:")
    print(f"  Файл: {dl_result.filepath.name} ({dl_result.file_size / (1024 * 1024):.2f} MiB)")
    print(f"  Название: {dl_result.title}")

    # 2. Прямая передача объекта dl_result в async-ffmpeg
    ffmpeg = FFmpegClient()

    print("\n2. Транскодирование скачанного медиа в оптимизированный 720p H.264...")
    transcode_res = await process_download_result(
        download=dl_result,
        action="transcode",
        video_codec="libx264",
        crf=23,
        resolution=(1280, 720),
        client=ffmpeg,
    )

    if transcode_res.result.is_success:
        out_file = transcode_res.output
        size_mb = out_file.stat().st_size / (1024 * 1024)
        print(f"[OK] Транскодированное видео готово: {out_file.name} ({size_mb:.2f} MiB)")
        if transcode_res.media_info and transcode_res.media_info.primary_video:
            v = transcode_res.media_info.primary_video
            print(f"  Параметры: {v.width}x{v.height}, кодек: {v.codec_name}")

    print("\n3. Извлечение отдельной MP3-аудиодорожки...")
    audio_res = await extract_download_audio(
        download=dl_result,
        codec="libmp3lame",
        bitrate="192k",
        client=ffmpeg,
    )

    if audio_res.result.is_success:
        print(f"[OK] Аудиодорожка извлечена: {audio_res.output.name}")

    print("\nКонвейер интеграции успешно выполнен!")


if __name__ == "__main__":
    asyncio.run(main())
