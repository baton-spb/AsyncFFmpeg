"""Пример извлечения аудиодорожки с конвертацией в MP3 и нормализацией громкости (EBU R128)."""

import asyncio
import sys
from pathlib import Path

from async_ffmpeg import FFmpegClient, ProgressInfo


async def _ensure_input_file(client: FFmpegClient, target_dir: Path) -> Path:
    """Создает синтетический тестовый видеофайл со звуком для демонстрации.

    Args:
        client: Экземпляр FFmpegClient.
        target_dir: Директория для размещения синтетического файла.

    Returns:
        Путь к готовому входному файлу.
    """
    sample_file = target_dir / "sample_video_audio.mp4"
    if not sample_file.exists():
        print("Генерация синтетического тестового медиа со звуком...")
        cmd = (
            client.create_command()
            .overwrite()
            .input("color=c=navy:s=640x360:d=4.0", f="lavfi")
            .input("sine=frequency=440:d=4.0", f="lavfi")
            .video_codec("libx264")
            .preset("ultrafast")
            .audio_codec("aac")
            .output(sample_file)
        )
        res = await cmd.execute()
        if not res.is_success:
            raise RuntimeError(f"Не удалось сгенерировать тестовый файл: {res.stderr_text}")
    return sample_file


async def main() -> None:
    """Точка входа демонстрационного скрипта извлечения аудио."""
    work_dir = Path("./output_examples")
    work_dir.mkdir(parents=True, exist_ok=True)

    client = FFmpegClient()

    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
        if not input_path.exists():
            print(f"Ошибка: указанный файл не найден: {input_path}")
            sys.exit(1)
    else:
        input_path = await _ensure_input_file(client, work_dir)

    output_mp3 = work_dir / f"{input_path.stem}_audio.mp3"

    print(f"Входной файл:   {input_path}")
    print(f"Выходное аудио: {output_mp3}")

    info = await client.probe(input_path)
    if not info.has_audio:
        print("Ошибка: во входном файле отсутствует аудиодорожка.")
        sys.exit(1)

    audio_stream = info.primary_audio
    if audio_stream:
        print(
            f"Исходный кодек: {audio_stream.codec_name}, каналов: {audio_stream.channels}, частота: {audio_stream.sample_rate} Гц"
        )

    print("\nИзвлечение аудиодорожки (MP3, 192k) с нормализацией громкости...")

    def on_progress(p: ProgressInfo) -> None:
        if p.percentage is not None:
            print(f"\rОбработано: {p.percentage:.1f}%", end="", flush=True)
        elif p.out_time:
            print(f"\rВремя: {p.out_time}", end="", flush=True)

    result = await client.extract_audio(
        input=input_path,
        output=output_mp3,
        codec="libmp3lame",
        bitrate="192k",
        on_progress=on_progress,
    )

    print()
    if result.is_success:
        size_kib = output_mp3.stat().st_size / 1024
        print("Аудио успешно извлечено!")
        print(f"Размер MP3: {size_kib:.1f} KiB")
        print(f"Время обработки: {result.duration_seconds:.2f} сек.")
    else:
        print("Ошибка при извлечении аудио:")
        print(result.stderr_text)


if __name__ == "__main__":
    asyncio.run(main())
