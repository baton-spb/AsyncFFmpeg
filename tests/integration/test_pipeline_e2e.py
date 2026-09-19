"""Интеграционные сквозные (E2E) тесты для библиотеки async_ffmpeg."""

from pathlib import Path

import pytest

from async_ffmpeg import FFmpegClient


@pytest.mark.asyncio
async def test_pipeline_e2e_full_workflow(tmp_path: Path) -> None:
    """Полный сквозной тест конвейера: генерация видео+аудио, фильтры, кодирование и верификация."""
    source_file = tmp_path / "source_e2e.mp4"
    output_file = tmp_path / "result_e2e.mp4"

    client = FFmpegClient()

    # 1. Генерируем тестовый файл с видео и звуком через FFmpegCommand
    init_cmd = (
        client.create_command()
        .overwrite()
        .input("testsrc2=s=640x480:d=1.5", f="lavfi")
        .input("sine=frequency=440:d=1.5", f="lavfi")
        .video_codec("libx264")
        .preset("ultrafast")
        .audio_codec("aac")
        .output(source_file)
    )
    res_init = await init_cmd.execute()
    assert res_init.success
    assert source_file.exists()

    # 2. Выполняем цепочку обработки через MediaPipeline
    pipeline = (
        client.pipeline(source_file)
        .trim(start=0.2, duration=1.0)
        .scale(320, 240)
        .fps(20)
        .volume("2dB")
        .normalize_audio(target_lufs=-14.0)
        .video_codec("libx264", preset="ultrafast", crf=26)
        .audio_codec("aac", bitrate="96k")
        .metadata("title", "EndToEndTest")
        .output(output_file)
    )

    result = await pipeline.run()
    assert result.success
    assert output_file.exists()
    assert output_file.stat().st_size > 0

    # 3. Детально валидируем полученный результат через FFprobe
    info = await client.probe(output_file)
    assert info.has_video
    assert info.has_audio
    assert info.primary_video is not None
    assert info.primary_video.width == 320
    assert info.primary_video.height == 240
    assert info.primary_audio is not None
    assert info.primary_audio.codec_name == "aac"
    assert info.format.tags.get("title") == "EndToEndTest"
    assert info.duration is not None
    assert 0.8 <= info.duration <= 1.3


@pytest.mark.asyncio
async def test_client_e2e_audio_and_concat(tmp_path: Path) -> None:
    """Сквозной тест: извлечение аудио и последующая конкатенация сегментов."""
    client = FFmpegClient()

    # Создаем 2 видеосегмента
    seg1 = tmp_path / "seg1.mp4"
    seg2 = tmp_path / "seg2.mp4"

    cmd1 = (
        client.create_command()
        .overwrite()
        .input("color=c=red:s=320x240:d=0.5", f="lavfi")
        .input("sine=frequency=440:d=0.5", f="lavfi")
        .video_codec("libx264")
        .preset("ultrafast")
        .audio_codec("aac")
        .output(seg1)
    )
    await cmd1.execute()

    cmd2 = (
        client.create_command()
        .overwrite()
        .input("color=c=blue:s=320x240:d=0.5", f="lavfi")
        .input("sine=frequency=880:d=0.5", f="lavfi")
        .video_codec("libx264")
        .preset("ultrafast")
        .audio_codec("aac")
        .output(seg2)
    )
    await cmd2.execute()

    # Проверяем извлечение аудио
    extracted_audio = tmp_path / "extracted.aac"
    res_audio = await client.extract_audio(seg1, extracted_audio)
    assert res_audio.success
    assert extracted_audio.exists()

    # Конкатенируем сегменты через фильтр
    concat_out = tmp_path / "concatenated.mp4"
    res_concat = await client.concat([seg1, seg2], concat_out, method="filter")
    assert res_concat.success
    assert concat_out.exists()

    info = await client.probe(concat_out)
    assert info.has_video
    assert info.has_audio
    assert info.duration is not None
    assert 0.8 <= info.duration <= 1.3
