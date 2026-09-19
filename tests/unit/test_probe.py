"""Unit-тесты для клиента FFprobe и парсера JSON (probe.py)."""

import json
import subprocess
from pathlib import Path

import pytest

from aio_ffmpeg._discovery import find_ffmpeg
from aio_ffmpeg.exceptions import FFprobeError, InvalidInputError
from aio_ffmpeg.probe import FFprobe, parse_probe_json

MOCK_PROBE_JSON = {
    "streams": [
        {
            "index": 0,
            "codec_name": "h264",
            "codec_long_name": "H.264 / AVC",
            "profile": "High",
            "codec_type": "video",
            "codec_tag_string": "avc1",
            "width": 1280,
            "height": 720,
            "coded_width": 1280,
            "coded_height": 720,
            "pix_fmt": "yuv420p",
            "r_frame_rate": "30/1",
            "avg_frame_rate": "30/1",
            "duration": "5.000000",
            "bit_rate": "1500000",
            "nb_frames": "150",
            "is_avc": "true",
            "disposition": {"default": 1, "forced": 0},
            "tags": {"language": "und", "title": "Main Video"},
        },
        {
            "index": 1,
            "codec_name": "aac",
            "codec_long_name": "AAC (Advanced Audio Coding)",
            "profile": "LC",
            "codec_type": "audio",
            "sample_rate": "44100",
            "channels": 2,
            "channel_layout": "stereo",
            "duration": "5.000000",
            "bit_rate": "128000",
            "disposition": {"default": 1},
            "tags": {"language": "rus"},
        },
        {
            "index": 2,
            "codec_name": "subrip",
            "codec_long_name": "SubRip Subtitle",
            "codec_type": "subtitle",
            "disposition": {"forced": 1},
            "tags": {"language": "eng"},
        },
    ],
    "format": {
        "filename": "sample_video.mp4",
        "nb_streams": 3,
        "format_name": "mov,mp4,m4a",
        "format_long_name": "QuickTime / MOV",
        "duration": "5.000000",
        "size": "1000000",
        "bit_rate": "1600000",
        "probe_score": 100,
        "tags": {"major_brand": "isom", "title": "Test Movie"},
    },
    "chapters": [
        {
            "id": 1,
            "time_base": "1/1000",
            "start": 0,
            "start_time": "0.000000",
            "end": 2500,
            "end_time": "2.500000",
            "tags": {"title": "Part 1"},
        }
    ],
}


def test_parse_probe_json_valid() -> None:
    json_bytes = json.dumps(MOCK_PROBE_JSON).encode("utf-8")
    info = parse_probe_json(json_bytes)

    assert info.format.filename == "sample_video.mp4"
    assert info.format.duration == 5.0
    assert info.format.size == 1000000
    assert info.format.bit_rate == 1600000

    assert len(info.streams) == 3
    assert len(info.video_streams) == 1
    assert len(info.audio_streams) == 1
    assert len(info.subtitle_streams) == 1

    v = info.primary_video
    assert v is not None
    assert v.codec_name == "h264"
    assert v.width == 1280
    assert v.height == 720
    assert v.resolution == (1280, 720)
    assert v.frame_rate == 30.0
    assert v.is_avc is True
    assert v.disposition.default is True
    assert v.tags.get("title") == "Main Video"

    a = info.primary_audio
    assert a is not None
    assert a.codec_name == "aac"
    assert a.sample_rate == 44100
    assert a.channels == 2
    assert a.channel_layout == "stereo"

    assert len(info.chapters) == 1
    ch = info.chapters[0]
    assert ch.id == 1
    assert ch.title == "Part 1"
    assert ch.duration == 2.5


def test_parse_probe_json_corrupted() -> None:
    with pytest.raises(FFprobeError) as exc_info:
        parse_probe_json(b"{ invalid json string")
    assert "Невалидный JSON" in str(exc_info.value)


@pytest.mark.asyncio
async def test_ffprobe_missing_file_raises() -> None:
    probe = FFprobe()
    with pytest.raises(InvalidInputError) as exc_info:
        await probe.probe("nonexistent_file_abc_123.mp4")
    assert "не существует" in str(exc_info.value)


@pytest.mark.asyncio
async def test_ffprobe_real_execution(tmp_path: Path) -> None:
    """Создает мини-файл через ffmpeg и тестирует реальный вызов FFprobe."""
    ffmpeg_bin = find_ffmpeg()
    out_file = tmp_path / "probe_test.mp4"

    # Генерируем 0.5с синтетическое видео с синусоидальным звуком
    cmd = [
        str(ffmpeg_bin),
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=320x240:d=0.5:r=25",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=1000:duration=0.5",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-c:a",
        "aac",
        str(out_file),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    assert out_file.is_file()

    probe = FFprobe()
    info = await probe.probe(out_file)

    assert info.has_video is True
    assert info.has_audio is True
    assert info.resolution == (320, 240)
    assert info.duration is not None
    assert info.duration >= 0.4

    # Проверка вспомогательных методов
    dur = await probe.get_duration(out_file)
    assert dur is not None
    assert dur >= 0.4

    res = await probe.get_resolution(out_file)
    assert res == (320, 240)

    codecs = await probe.get_codecs(out_file)
    assert codecs.get("video") == "h264"
    assert codecs.get("audio") == "aac"

    assert await probe.has_video(out_file) is True
    assert await probe.has_audio(out_file) is True

    # Синхронный вызов
    info_sync = probe.probe_sync(out_file)
    assert info_sync.resolution == (320, 240)
