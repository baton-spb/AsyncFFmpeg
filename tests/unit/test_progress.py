"""Unit-тесты для модуля парсинга прогресса FFmpeg (progress.py)."""

import asyncio

import pytest

from aio_ffmpeg.progress import ProgressInfo, ProgressParser, parse_progress_stream

SAMPLE_VIDEO_BLOCK = """
frame=16
fps=24.5
stream_0_0_q=29.0
bitrate=   0.8kbits/s
total_size=48
out_time_us=466667
out_time_ms=466
out_time=00:00:00.466667
dup_frames=0
drop_frames=0
speed=2.32x
progress=continue
"""

SAMPLE_END_BLOCK = """
frame=150
fps=30.0
stream_0_0_q=-1.0
bitrate=93.6kbits/s
total_size=35089
out_time_us=5000000
out_time_ms=5000
out_time=00:00:05.000000
dup_frames=0
drop_frames=0
speed= 15.0x
progress=end
"""

SAMPLE_AUDIO_ONLY_BLOCK = """
bitrate=N/A
total_size=N/A
out_time_us=3000000
out_time_ms=3000
out_time=00:00:03.000000
dup_frames=0
drop_frames=0
speed=39.9x
progress=end
"""


def test_progress_info_calculations() -> None:
    info = ProgressInfo(
        frame=50,
        fps=25.0,
        bitrate_kbits=128.0,
        bitrate_raw="128kbits/s",
        total_size=10240,
        out_time_us=2_000_000,
        out_time_ms=2000,
        out_time="00:00:02.000000",
        dup_frames=0,
        drop_frames=0,
        speed=2.0,
        speed_raw="2.0x",
        is_finished=False,
        stream_q={"stream_0_0_q": 28.0},
        total_duration=10.0,
    )

    assert info.out_time_seconds == 2.0
    assert info.percent == pytest.approx(20.0)
    # remaining: 10.0 - 2.0 = 8.0s. Speed = 2.0x -> ETA = 4.0s
    assert info.eta_seconds == pytest.approx(4.0)


def test_progress_info_finished() -> None:
    info = ProgressInfo(
        frame=100,
        fps=30.0,
        bitrate_kbits=None,
        bitrate_raw="N/A",
        total_size=None,
        out_time_us=5_000_000,
        out_time_ms=5000,
        out_time="00:00:05.000000",
        dup_frames=0,
        drop_frames=0,
        speed=1.0,
        speed_raw="1.0x",
        is_finished=True,
        stream_q={},
        total_duration=5.0,
    )

    assert info.percent == 100.0
    assert info.eta_seconds == 0.0


def test_progress_parser_video_block() -> None:
    parser = ProgressParser(total_duration=10.0)
    completed: list[ProgressInfo] = []

    for line in SAMPLE_VIDEO_BLOCK.strip().splitlines():
        res = parser.feed_line(line)
        if res is not None:
            completed.append(res)

    assert len(completed) == 1
    info = completed[0]
    assert info.frame == 16
    assert info.fps == 24.5
    assert info.bitrate_kbits == pytest.approx(0.8)
    assert info.total_size == 48
    assert info.out_time_us == 466667
    assert info.out_time == "00:00:00.466667"
    assert info.speed == pytest.approx(2.32)
    assert info.is_finished is False
    assert info.stream_q.get("stream_0_0_q") == 29.0
    assert info.percent is not None
    assert info.percent > 0


def test_progress_parser_audio_only() -> None:
    parser = ProgressParser()
    completed: list[ProgressInfo] = []

    for line in SAMPLE_AUDIO_ONLY_BLOCK.strip().splitlines():
        res = parser.feed_line(line)
        if res is not None:
            completed.append(res)

    assert len(completed) == 1
    info = completed[0]
    assert info.frame is None
    assert info.bitrate_kbits is None
    assert info.total_size is None
    assert info.out_time_us == 3000000
    assert info.speed == pytest.approx(39.9)
    assert info.is_finished is True


def test_progress_parser_feed_chunk_multiple_blocks() -> None:
    parser = ProgressParser(total_duration=5.0)
    chunk = (SAMPLE_VIDEO_BLOCK + "\n" + SAMPLE_END_BLOCK).encode("utf-8")

    # Передаём часть за частью
    part1 = chunk[: len(chunk) // 2]
    part2 = chunk[len(chunk) // 2 :]

    results1 = parser.feed_chunk(part1)
    results2 = parser.feed_chunk(part2)

    total_results = results1 + results2
    assert len(total_results) == 2
    assert total_results[0].is_finished is False
    assert total_results[1].is_finished is True
    assert total_results[1].percent == 100.0


@pytest.mark.asyncio
async def test_parse_progress_stream_async() -> None:
    reader = asyncio.StreamReader()
    full_text = (SAMPLE_VIDEO_BLOCK + "\n" + SAMPLE_END_BLOCK).strip() + "\n"
    reader.feed_data(full_text.encode("utf-8"))
    reader.feed_eof()

    collected: list[ProgressInfo] = []
    async for item in parse_progress_stream(reader, total_duration=5.0):
        collected.append(item)

    assert len(collected) == 2
    assert collected[0].frame == 16
    assert collected[1].frame == 150
    assert collected[1].is_finished is True
