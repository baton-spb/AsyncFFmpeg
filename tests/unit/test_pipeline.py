"""Тесты для высокоуровневого конвейера MediaPipeline (Phase 11)."""

from pathlib import Path

import pytest

from async_ffmpeg import (
    CommandBuildError,
    FFmpegClient,
    MediaPipeline,
    ProcessResult,
    ProgressInfo,
)


def test_pipeline_init_and_input() -> None:
    """Проверяет создание конвейера и добавление входов."""
    p1 = MediaPipeline("input.mp4")
    assert len(p1._inputs) == 1
    assert p1._inputs[0][0] == "input.mp4"

    p2 = MediaPipeline()
    assert len(p2._inputs) == 0
    p2.input(Path("video.mkv"), ss="00:01:00")
    assert len(p2._inputs) == 1
    assert p2._inputs[0][1] == {"ss": "00:01:00"}


def test_pipeline_chaining_basic() -> None:
    """Проверяет построение команды через цепочку вызовов."""
    pipeline = (
        MediaPipeline("input.mp4")
        .trim(start=5.0, duration=10.0)
        .scale(1280, 720)
        .fps(30)
        .video_codec("libx264", preset="faster", crf=23)
        .audio_codec("aac", bitrate="128k")
        .output("output.mp4")
    )

    cmd_args = pipeline.build()
    cmd_str = " ".join(cmd_args)

    # Проверяем ключевые аргументы
    assert "-ss 5.0" in cmd_str
    assert "-t 10.0" in cmd_str
    assert "-i input.mp4" in cmd_str
    assert "-vf" in cmd_str
    assert "scale=1280:720" in cmd_str
    assert "fps=30" in cmd_str
    assert "-c:v libx264" in cmd_str
    assert "-preset faster" in cmd_str
    assert "-crf 23" in cmd_str
    assert "-c:a aac" in cmd_str
    assert "-b:a 128k" in cmd_str
    assert cmd_args[-1] == "output.mp4"


def test_pipeline_fast_seek_vs_accurate_seek() -> None:
    """Проверяет позиционирование аргументов поиска (-ss) при fast_seek True vs False."""
    # Fast seek (по умолчанию): опции до -i
    p_fast = MediaPipeline("in.mp4").trim(start=10, end=20, fast_seek=True).output("out.mp4")
    args_fast = p_fast.build()
    i_index_fast = args_fast.index("-i")
    ss_index_fast = args_fast.index("-ss")
    assert ss_index_fast < i_index_fast

    # Accurate seek: опции после -i
    p_acc = MediaPipeline("in.mp4").trim(start=10, duration=5, fast_seek=False).output("out.mp4")
    args_acc = p_acc.build()
    i_index_acc = args_acc.index("-i")
    ss_index_acc = args_acc.index("-ss")
    assert ss_index_acc > i_index_acc


def test_pipeline_validation_missing_inputs_or_outputs() -> None:
    """Проверяет выброс исключений при отсутствии входов или выходов."""
    # Без входов
    p_no_in = MediaPipeline().output("out.mp4")
    with pytest.raises(CommandBuildError, match="входного файла"):
        p_no_in.validate()

    # Без выходов
    p_no_out = MediaPipeline("in.mp4")
    with pytest.raises(CommandBuildError, match="выходного файла"):
        p_no_out.validate()


def test_pipeline_validation_conflicts() -> None:
    """Проверяет проверку несовместимых комбинаций (stream copy + фильтры)."""
    # copy_video + scale
    with pytest.raises(CommandBuildError, match="copy_video"):
        (MediaPipeline("in.mp4").copy_video().scale(640, 480).output("out.mp4").validate())

    # copy_audio + volume
    with pytest.raises(CommandBuildError, match="copy_audio"):
        (MediaPipeline("in.mp4").copy_audio().volume(1.5).output("out.mp4").validate())

    # copy_all + video_filter
    with pytest.raises(CommandBuildError, match="copy_all"):
        (MediaPipeline("in.mp4").copy_all().fps(24).output("out.mp4").validate())

    # no_video + video_codec
    with pytest.raises(CommandBuildError, match="no_video"):
        (MediaPipeline("in.mp4").no_video().video_codec("libx264").output("out.mp4").validate())

    # no_audio + audio_codec
    with pytest.raises(CommandBuildError, match="no_audio"):
        (MediaPipeline("in.mp4").no_audio().audio_codec("aac").output("out.mp4").validate())


def test_pipeline_watermark_complex_filter() -> None:
    """Проверяет генерацию complex filtergraph при добавлении водяного знака."""
    pipeline = (
        MediaPipeline("movie.mp4")
        .scale(1920, 1080)
        .watermark("logo.png", position="top-right", margin=20, opacity=0.8)
        .video_codec("libx264")
        .audio_codec("copy")
        .output("result.mp4")
    )

    args = pipeline.build()
    cmd_str = " ".join(args)

    assert "-filter_complex" in cmd_str
    assert "-i movie.mp4" in cmd_str
    assert "-i logo.png" in cmd_str
    assert "main_w-overlay_w-20" in cmd_str
    assert "colorchannelmixer=aa=0.8" in cmd_str
    assert "-map [outv]" in cmd_str
    assert "-map 0:a?" in cmd_str


def test_pipeline_audio_filters_chaining() -> None:
    """Проверяет последовательную сборку цепочки аудиофильтров."""
    pipeline = (
        MediaPipeline("speech.wav")
        .volume(1.2)
        .normalize_audio(target_lufs=-16.0)
        .afade(type="in", start_time=0.0, duration=1.5)
        .atempo(1.25)
        .audio_codec("libopus")
        .output("speech.opus")
    )

    args = pipeline.build()
    cmd_str = " ".join(args)

    assert "-af" in cmd_str
    assert "volume=1.2" in cmd_str
    assert "loudnorm" in cmd_str
    assert "afade=t=in:st=0.0:d=1.5" in cmd_str
    assert "atempo=1.25" in cmd_str


def test_pipeline_build_and_preview() -> None:
    """Проверяет методы build() и preview()."""
    pipeline = MediaPipeline("in.mp4").rotate(1.57).vflip().hflip().output("out.mp4")
    args = pipeline.build()
    assert isinstance(args, list)
    assert len(args) > 4

    preview_str = pipeline.preview()
    assert isinstance(preview_str, str)
    assert "ffmpeg" in preview_str
    assert "in.mp4" in preview_str
    assert "out.mp4" in preview_str


def test_pipeline_client_integration() -> None:
    """Проверяет создание конвейера через FFmpegClient.pipeline()."""
    client = FFmpegClient(max_concurrent=2, default_timeout=45.0)
    pipe = client.pipeline("source.mp4")

    assert isinstance(pipe, MediaPipeline)
    assert pipe._client is client
    assert pipe._inputs[0][0] == "source.mp4"


@pytest.mark.asyncio
async def test_pipeline_real_execution_lavfi(tmp_path: Path) -> None:
    """Интеграционный тест: создание тестового видео через lavfi и применение конвейера."""
    output_file = tmp_path / "test_pipeline_lavfi.mp4"

    pipe = (
        MediaPipeline()
        .input("color=c=green:s=320x240:d=0.5", f="lavfi")
        .scale(160, 120)
        .fps(15)
        .video_codec("libx264", preset="ultrafast")
        .output(output_file)
    )

    result = await pipe.run()
    assert isinstance(result, ProcessResult)
    assert result.success
    assert output_file.exists()
    assert output_file.stat().st_size > 0

    # Проверяем параметры полученного файла через ffprobe
    client = FFmpegClient()
    info = await client.probe(output_file)
    assert info.primary_video is not None
    assert info.primary_video.width == 160
    assert info.primary_video.height == 120


@pytest.mark.asyncio
async def test_pipeline_real_execution_watermark(tmp_path: Path) -> None:
    """Интеграционный тест: создание видео с наложением водяного знака."""
    # 1. Генерируем маленький логотип PNG
    logo_file = tmp_path / "logo.png"
    client = FFmpegClient()
    cmd_logo = (
        client.create_command()
        .overwrite()
        .input("color=c=red:s=32x32:d=0.1", f="lavfi")
        .output(logo_file, vframes=1)
    )
    res_logo = await cmd_logo.execute()
    assert res_logo.success
    assert logo_file.exists()

    # 2. Накладываем логотип через конвейер
    output_file = tmp_path / "watermarked.mp4"
    pipeline = (
        MediaPipeline()
        .input("color=c=blue:s=320x240:d=0.5", f="lavfi")
        .watermark(logo_file, position="bottom-right", margin=10, opacity=0.8)
        .video_codec("libx264", preset="ultrafast")
        .output(output_file)
    )

    res = await pipeline.run()
    assert res.success
    assert output_file.exists()
    assert output_file.stat().st_size > 0


@pytest.mark.asyncio
async def test_pipeline_progress_tracking(tmp_path: Path) -> None:
    """Интеграционный тест: получение обновлений прогресса во время работы конвейера."""
    output_file = tmp_path / "test_progress.mp4"
    progress_updates: list[ProgressInfo] = []

    def on_prog(info: ProgressInfo) -> None:
        progress_updates.append(info)

    pipeline = (
        MediaPipeline()
        .input("color=c=yellow:s=320x240:d=1.0", f="lavfi")
        .trim(duration=1.0)
        .scale(160, 120)
        .video_codec("libx264", preset="ultrafast")
        .output(output_file)
    )

    result = await pipeline.run(on_progress=on_prog)
    assert result.success
    assert len(progress_updates) > 0
