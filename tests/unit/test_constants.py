"""Unit-тесты для модуля констант async-ffmpeg."""

from aio_ffmpeg import _constants


def test_constants_definitions() -> None:
    assert _constants.__version__ == "0.1.2"
    assert _constants.DEFAULT_FFMPEG_EXECUTABLE == "ffmpeg"
    assert _constants.DEFAULT_FFPROBE_EXECUTABLE == "ffprobe"
    assert _constants.DEFAULT_MAX_CONCURRENT == 4
    assert _constants.DEFAULT_STATS_PERIOD == 0.5
    assert _constants.DEFAULT_LOGLEVEL == "error"
    assert _constants.GRACEFUL_SHUTDOWN_TIMEOUT == 5.0
    assert _constants.FORCE_KILL_TIMEOUT == 2.0
    assert _constants.DEFAULT_PROBE_TIMEOUT == 30.0
    assert _constants.DEFAULT_READ_BUFFER_SIZE == 64 * 1024
    assert _constants.DEFAULT_AUDIO_BITRATE == "128k"
    assert _constants.DEFAULT_VIDEO_CRF == 23
    assert _constants.DEFAULT_VIDEO_PRESET == "medium"
