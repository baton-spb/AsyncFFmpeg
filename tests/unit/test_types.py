"""Unit-тесты для типов и протоколов async-ffmpeg."""

from pathlib import Path

from aio_ffmpeg._types import DownloadResultProtocol, MediaInputProtocol


class DummyDownloadResult:
    """Фиктивный класс, реализующий протокол DownloadResultProtocol."""

    def __init__(self, path: Path, title: str | None = None, duration: float | None = None) -> None:
        self._path = path
        self._title = title
        self._duration = duration

    @property
    def filepath(self) -> Path:
        return self._path

    @property
    def title(self) -> str | None:
        return self._title

    @property
    def duration(self) -> float | None:
        return self._duration


class DummyMediaInput:
    """Фиктивный класс, реализующий протокол MediaInputProtocol."""

    def __init__(self, url: str) -> None:
        self._url = url

    def to_ffmpeg_input(self) -> str:
        return self._url


def test_download_result_protocol() -> None:
    res = DummyDownloadResult(Path("/tmp/video.mp4"), title="Test", duration=12.5)
    assert isinstance(res, DownloadResultProtocol)
    assert res.filepath == Path("/tmp/video.mp4")
    assert res.title == "Test"
    assert res.duration == 12.5


def test_media_input_protocol() -> None:
    inp = DummyMediaInput("http://example.com/live.m3u8")
    assert isinstance(inp, MediaInputProtocol)
    assert inp.to_ffmpeg_input() == "http://example.com/live.m3u8"
