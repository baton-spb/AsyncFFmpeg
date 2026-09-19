"""Unit-тесты для модуля построения фильтров FFmpeg (filters.py)."""

from pathlib import Path

import pytest

from async_ffmpeg.command import FFmpegCommand
from async_ffmpeg.exceptions import FilterError
from async_ffmpeg.filters import (
    ComplexFilterGraph,
    Filter,
    FilterChain,
    FilterGraph,
    afade,
    amix,
    anull,
    aresample,
    asetpts,
    asplit,
    atempo,
    atrim,
    concat,
    crop,
    drawtext,
    escape_filter_param,
    fps,
    hflip,
    loudnorm,
    overlay,
    pad,
    pan,
    rotate,
    scale,
    setpts,
    split,
    transpose,
    vflip,
    video_format,
    volume,
    vtrim,
)


def test_filter_basic_serialization() -> None:
    """Проверка базовой сериализации фильтров с позиционными и именованными аргументами."""
    f1 = Filter("vflip")
    assert str(f1) == "vflip"
    assert f1.name == "vflip"
    assert f1.args == ()
    assert f1.kwargs == {}

    f2 = Filter("scale", 1280, 720)
    assert str(f2) == "scale=1280:720"
    assert f2.args == ("1280", "720")

    f3 = Filter("scale", w=1920, h=1080)
    assert str(f3) == "scale=w=1920:h=1080"

    f4 = Filter("scale", 1280, 720, force_original_aspect_ratio="decrease")
    assert str(f4) == "scale=1280:720:force_original_aspect_ratio=decrease"

    f_ext = f1.with_options(x=10)
    assert str(f_ext) == "vflip=x=10"


def test_filter_empty_name_raises() -> None:
    """Проверка выброса FilterError при пустом названии фильтра."""
    with pytest.raises(FilterError, match="Имя фильтра не может быть пустым"):
        Filter("   ")


def test_escape_filter_param() -> None:
    """Проверка экранирования спецсимволов в параметрах фильтра."""
    assert escape_filter_param(True) == "1"
    assert escape_filter_param(False) == "0"
    assert escape_filter_param("plain_text") == "plain_text"
    assert escape_filter_param("'already_quoted'") == "'already_quoted'"

    escaped = escape_filter_param("C:\\path:sub,part")
    assert escaped.startswith("'")
    assert escaped.endswith("'")
    assert "\\:" in escaped
    assert "\\," in escaped


def test_filter_chain_serialization() -> None:
    """Проверка цепочки фильтров с входными и выходными метками."""
    chain = FilterChain(scale(1280, 720), fps(30))
    assert str(chain) == "scale=1280:720,fps=30"

    chain_labeled = FilterChain(
        scale(1280, 720),
        fps(30),
        inputs=["0:v"],
        outputs=["scaled"],
    )
    assert str(chain_labeled) == "[0:v]scale=1280:720,fps=30[scaled]"

    # Проверка с множественными входами и добавлением
    overlay_chain = FilterChain(inputs=["bg", "fg"]).add(overlay(10, 10)).with_outputs("out")
    assert str(overlay_chain) == "[bg][fg]overlay=10:10:eof_action=repeat[out]"

    # Добавление строкового фильтра
    str_chain = FilterChain().add("vflip").chain("hflip")
    assert str(str_chain) == "vflip,hflip"


def test_filter_chain_empty_raises() -> None:
    """Проверка выброса FilterError при сериализации пустой цепочки."""
    chain = FilterChain()
    with pytest.raises(FilterError, match="не может быть пустой"):
        str(chain)


def test_filter_graph_simple() -> None:
    """Проверка создания и сериализации простого FilterGraph."""
    fg = FilterGraph.simple(scale(1280, 720), fps(30))
    assert str(fg) == "scale=1280:720,fps=30"

    empty_fg = FilterGraph()
    assert str(empty_fg) == ""


def test_complex_filter_graph_fluent() -> None:
    """Проверка сложного графа фильтров (ComplexFilterGraph) с ветвлением."""
    cfg = (
        FilterGraph.complex()
        .chain("0:v", scale(1280, 720), "bg")
        .chain("1:v", scale(200, 200), "fg")
        .chain(["bg", "fg"], overlay(10, 10), "out")
    )
    expected = (
        "[0:v]scale=1280:720[bg];"
        "[1:v]scale=200:200[fg];"
        "[bg][fg]overlay=10:10:eof_action=repeat[out]"
    )
    assert isinstance(cfg, ComplexFilterGraph)
    assert str(cfg) == expected


def test_video_filter_factories() -> None:
    """Проверка фабричных функций для видео-фильтров."""
    assert str(scale(1920, 1080)) == "scale=1920:1080"
    assert str(scale(1280, -2, force_original_aspect_ratio="decrease")) == (
        "scale=1280:-2:force_original_aspect_ratio=decrease"
    )
    assert str(fps(24)) == "fps=24"
    assert str(crop(100, 100, 10, 20)) == "crop=100:100:10:20"
    assert str(pad(1920, 1080, color="red")) == "pad=1920:1080:0:0:red"
    assert str(rotate("PI/4")) == "rotate=PI/4:fillcolor=black"
    assert str(vflip()) == "vflip"
    assert str(hflip()) == "hflip"
    assert str(transpose(1)) == "transpose=1"
    assert str(video_format("yuv420p")) == "format=yuv420p"
    assert str(setpts("PTS-STARTPTS")) == "setpts=PTS-STARTPTS"
    assert str(vtrim(start=1.5, duration=5.0)) == "trim=start=1.5:duration=5.0"
    assert str(overlay(10, 20, shortest=True)) == "overlay=10:20:eof_action=repeat:shortest=1"
    assert str(drawtext("Hello", fontsize=24)) == "drawtext=text='Hello':x=10:y=10:fontsize=24"


def test_audio_filter_factories() -> None:
    """Проверка фабричных функций для аудио-фильтров."""
    assert str(volume(1.5)) == "volume=1.5"
    assert str(volume("6dB")) == "volume=6dB"
    assert str(atempo(1.25)) == "atempo=1.25"
    assert str(afade("in", start_time=0.0, duration=3.0)) == "afade=t=in:st=0.0:d=3.0"
    assert str(loudnorm(i=-16.0)) == "loudnorm=I=-16.0:LRA=7.0:tp=-1.0:dual_mono=false"
    assert str(anull()) == "anull"
    assert str(amix(inputs=3)) == "amix=inputs=3:duration=longest:dropout_transition=2.0"
    assert str(atrim(start=2.0)) == "atrim=start=2.0"
    assert str(asetpts("PTS-STARTPTS")) == "asetpts=PTS-STARTPTS"
    assert str(aresample(48000)) == "aresample=48000"
    assert str(pan("stereo", "c0=c0", "c1=c1")) == "pan=stereo:c0=c0:c1=c1"


def test_utility_filter_factories() -> None:
    """Проверка фабричных функций для утилитных фильтров."""
    assert str(concat(n=3, v=1, a=1)) == "concat=n=3:v=1:a=1"
    assert str(split(3)) == "split=3"
    assert str(asplit(2)) == "asplit=2"


def test_command_filter_integration() -> None:
    """Проверка интеграции объектов Filter/FilterGraph с FFmpegCommand."""
    simple_fg = FilterGraph.simple(scale(640, 480), fps(30))
    cmd = (
        FFmpegCommand()
        .input("input.mp4")
        .video_filter(simple_fg)
        .audio_filter(volume("3dB"))
        .output("output.mp4")
    )
    built = cmd.build()
    assert "-vf" in built
    assert "scale=640:480,fps=30" in built
    assert "-af" in built
    assert "volume=3dB" in built


@pytest.mark.asyncio
async def test_complex_filter_real_execution(tmp_path: Path) -> None:
    """Интеграционный тест: создание видео с наложением через FilterGraph и реальный FFmpeg."""
    out_file = tmp_path / "overlay_output.mp4"

    # Граф фильтров:
    # 1. 0:v масштабируем в 320x240 с меткой [bg]
    # 2. 1:v масштабируем в 80x60 с меткой [fg]
    # 3. Накладываем [fg] на [bg] в координаты 20:20 -> метка [out]
    cfg = (
        FilterGraph.complex()
        .chain("0:v", scale(320, 240), "bg")
        .chain("1:v", scale(80, 60), "fg")
        .chain(["bg", "fg"], overlay(20, 20), "out")
    )

    cmd = (
        FFmpegCommand()
        .overwrite()
        .input("color=c=red:s=640x480:d=0.5", f="lavfi")
        .input("color=c=blue:s=160x120:d=0.5", f="lavfi")
        .complex_filter(cfg)
        .map_stream("[out]")
        .video_codec("libx264")
        .output(out_file, preset="ultrafast")
    )

    result = await cmd.execute()
    assert result.success
    assert out_file.exists()
    assert out_file.stat().st_size > 0
