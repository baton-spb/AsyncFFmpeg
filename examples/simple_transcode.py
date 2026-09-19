"""Пример базового транскодирования видео с отображением прогресса в реальном времени."""

import asyncio
import sys
from pathlib import Path

from async_ffmpeg import AudioCodec, FFmpegClient, ProgressInfo, Resolution, VideoCodec


def _render_progress_bar(progress: ProgressInfo) -> str:
    """Формирует текстовый индикатор выполнения операции.

    Args:
        progress: Объект с текущими метриками процесса транскодирования.

    Returns:
        Строка с графической шкалой и ключевыми параметрами.
    """
    if progress.percentage is not None:
        pct = progress.percentage
        width = 25
        filled = int(width * pct / 100)
        bar = "=" * filled + ">" if filled < width else "=" * width
        eta = f"{progress.eta_seconds:.1f}s" if progress.eta_seconds is not None else "N/A"
        return f"[{bar:<25}] {pct:5.1f}% | FPS: {progress.fps or 0:4.1f} | Скорость: {progress.speed or 'N/A'} | ETA: {eta}"

    time_str = progress.out_time or "00:00:00"
    return f"Обработано времени: {time_str} | FPS: {progress.fps or 0:4.1f} | Скорость: {progress.speed or 'N/A'}"


async def _ensure_input_file(client: FFmpegClient, target_dir: Path) -> Path:
    """Создает синтетический тестовый видеофайл при отсутствии пользовательского файла.

    Args:
        client: Экземпляр FFmpegClient.
        target_dir: Директория для размещения синтетического файла.

    Returns:
        Путь к готовому входному файлу.
    """
    sample_file = target_dir / "sample_input.mp4"
    if not sample_file.exists():
        print("Генерация синтетического тестового видео (3 сек, 1080p)...")
        cmd = (
            client.create_command()
            .overwrite()
            .input("testsrc=size=1920x1080:rate=30:duration=3.0", f="lavfi")
            .input("sine=frequency=1000:duration=3.0", f="lavfi")
            .video_codec("libx264")
            .preset("ultrafast")
            .audio_codec("aac")
            .output(sample_file)
        )
        res = await cmd.execute()
        if not res.is_success:
            raise RuntimeError(f"Не удалось сгенерировать тестовое видео: {res.stderr_text}")
    return sample_file


async def main() -> None:
    """Точка входа демонстрационного скрипта транскодирования."""
    work_dir = Path("./output_examples")
    work_dir.mkdir(parents=True, exist_ok=True)

    client = FFmpegClient(max_concurrent=2)

    # Определение входного файла (из аргументов или синтетический)
    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
        if not input_path.exists():
            print(f"Ошибка: указанный файл не найден: {input_path}")
            sys.exit(1)
    else:
        input_path = await _ensure_input_file(client, work_dir)

    output_path = work_dir / f"{input_path.stem}_720p.mp4"

    print(f"Входной файл:   {input_path}")
    print(f"Выходной файл:  {output_path}")

    # Анализ исходного медиа
    info = await client.probe(input_path)
    print(f"Длительность:   {info.duration or 0:.2f} сек.")
    if info.primary_video:
        print(
            f"Исходное видео: {info.primary_video.codec_name} {info.primary_video.width}x{info.primary_video.height} @ {info.primary_video.fps or 0:.1f} fps"
        )

    print("\nЗапуск транскодирования в 720p (H.264 / CRF 23)...")

    def on_progress(p: ProgressInfo) -> None:
        bar = _render_progress_bar(p)
        print(f"\r{bar}", end="", flush=True)

    result = await client.transcode(
        input=input_path,
        output=output_path,
        video_codec=VideoCodec.H264,
        crf=23,
        resolution=Resolution.HD_720P,
        audio_codec=AudioCodec.AAC,
        audio_bitrate="128k",
        on_progress=on_progress,
    )

    print()
    if result.is_success:
        out_size = output_path.stat().st_size / (1024 * 1024)
        print("Транскодирование успешно завершено!")
        print(f"Размер файла:   {out_size:.2f} MiB")
        print(f"Время кодирования: {result.duration_seconds:.2f} сек.")
    else:
        print("Ошибка при транскодировании:")
        print(result.stderr_text)


if __name__ == "__main__":
    asyncio.run(main())
