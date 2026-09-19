"""Unit и интеграционные тесты для FFmpegCommand builder (command.py)."""

from pathlib import Path

import pytest

from aio_ffmpeg._discovery import find_ffmpeg
from aio_ffmpeg.command import FFmpegCommand
from aio_ffmpeg.exceptions import CommandBuildError
from aio_ffmpeg.progress import ProgressInfo


def test_command_validation_empty_inputs() -> None:
    cmd = FFmpegCommand().output("out.mp4")
    with pytest.raises(CommandBuildError) as exc:
        cmd.build()
    assert "хотя бы один входной файл" in str(exc.value)


def test_command_validation_empty_outputs() -> None:
    cmd = FFmpegCommand().input("in.mp4")
    with pytest.raises(CommandBuildError) as exc:
        cmd.build()
    assert "хотя бы один выходной файл" in str(exc.value)


def test_command_strict_ordering() -> None:
    cmd = (
        FFmpegCommand()
        .overwrite(True)
        .no_stdin(True)
        .hide_banner(True)
        .loglevel("warning")
        .progress("pipe:1", stats_period=0.25)
        .input("input.mp4", ss="00:00:10", t="5")
        .video_filter("scale=1280:720")
        .video_codec("libx264")
        .audio_codec("aac")
        .preset("fast")
        .crf(22)
        .output("output.mp4")
    )

    args = cmd.build()
    ffmpeg_exe = args[0]
    assert "ffmpeg" in ffmpeg_exe.lower()

    # 1. Глобальные опции
    assert "-y" in args
    assert "-nostdin" in args
    assert "-hide_banner" in args
    assert args[args.index("-loglevel") + 1] == "warning"
    assert args[args.index("-progress") + 1] == "pipe:1"
    assert args[args.index("-stats_period") + 1] == "0.25"

    # 2. Входные опции ДО -i
    ss_idx = args.index("-ss")
    i_idx = args.index("-i")
    assert ss_idx < i_idx
    assert args[ss_idx + 1] == "00:00:10"
    assert args[i_idx + 1] == "input.mp4"

    # 3. Фильтр ПОСЛЕ -i
    vf_idx = args.index("-vf")
    assert vf_idx > i_idx
    assert args[vf_idx + 1] == "scale=1280:720"

    # 4. Выходные опции ПОСЛЕ фильтра и ДО output.mp4
    c_v_idx = args.index("-c:v")
    out_idx = args.index("output.mp4")
    assert vf_idx < c_v_idx < out_idx
    assert args[c_v_idx + 1] == "libx264"
    assert args[args.index("-preset") + 1] == "fast"
    assert args[args.index("-crf") + 1] == "22"


def test_command_multiple_inputs_and_complex_filter() -> None:
    cmd = (
        FFmpegCommand()
        .overwrite()
        .input("bg.mp4")
        .input("overlay.png")
        .complex_filter("[0:v][1:v]overlay=10:10[out]")
        .map("[out]")
        .map("0:a")
        .video_codec("libx264")
        .output("composite.mp4")
    )

    args = cmd.build()
    i_indices = [idx for idx, arg in enumerate(args) if arg == "-i"]
    assert len(i_indices) == 2
    assert args[i_indices[0] + 1] == "bg.mp4"
    assert args[i_indices[1] + 1] == "overlay.png"

    assert "-filter_complex" in args
    fc_idx = args.index("-filter_complex")
    assert args[fc_idx + 1] == "[0:v][1:v]overlay=10:10[out]"
    assert args[args.index("-map") + 1] == "[out]"


def test_command_pretty_format() -> None:
    cmd = FFmpegCommand().input("in.mp4").output("out.mp4")
    pretty = cmd.build_pretty()
    assert "-i in.mp4" in pretty
    assert "out.mp4" in pretty


@pytest.mark.asyncio
async def test_command_execute_real(tmp_path: Path) -> None:
    """Генерирует реальный тестовый видеофайл через FFmpegCommand с отслеживанием прогресса."""
    ffmpeg_bin = find_ffmpeg()
    out_file = tmp_path / "command_test.mp4"

    progress_reports: list[ProgressInfo] = []

    def on_prog(info: ProgressInfo) -> None:
        progress_reports.append(info)

    cmd = (
        FFmpegCommand()
        .overwrite()
        .input("color=c=blue:s=320x240:d=1.0:r=25", f="lavfi")
        .input("sine=frequency=880:duration=1.0", f="lavfi")
        .video_codec("libx264")
        .preset("ultrafast")
        .audio_codec("aac")
        .output(out_file)
    )

    result = await cmd.execute(
        ffmpeg_path=ffmpeg_bin,
        total_duration=1.0,
        on_progress=on_prog,
    )

    assert result.success is True
    assert out_file.is_file()
    assert out_file.stat().st_size > 0
    assert len(progress_reports) >= 1
    # Финальный репорт должен иметь is_finished=True и percent=100.0
    last_report = progress_reports[-1]
    assert last_report.is_finished is True
    assert last_report.percent == 100.0
