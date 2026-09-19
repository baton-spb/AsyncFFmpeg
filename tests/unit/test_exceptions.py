"""Unit-тесты для иерархии исключений async-ffmpeg."""

from aio_ffmpeg.exceptions import (
    AsyncFFmpegError,
    CodecNotFoundError,
    CommandBuildError,
    FFmpegCancelledError,
    FFmpegNotFoundError,
    FFmpegProcessError,
    FFmpegTimeoutError,
    FFprobeError,
    FilterError,
    InvalidInputError,
)


def test_base_exception() -> None:
    err = AsyncFFmpegError("Базовая ошибка")
    assert str(err) == "Базовая ошибка"
    assert isinstance(err, Exception)


def test_ffmpeg_not_found_error() -> None:
    err = FFmpegNotFoundError("ffmpeg", ["/usr/bin", "/opt/homebrew/bin"])
    assert err.binary_name == "ffmpeg"
    assert err.searched_paths == ("/usr/bin", "/opt/homebrew/bin")
    assert "не найден в системе" in str(err)
    assert "/usr/bin" in str(err)

    err_no_paths = FFmpegNotFoundError("ffprobe")
    assert err_no_paths.searched_paths == ()
    assert "ffprobe" in str(err_no_paths)


def test_ffmpeg_process_error() -> None:
    stderr = (
        "[libx264 @ 0x123] invalid parameter\n"
        "Error initializing output stream 0:0\n"
        "Conversion failed!"
    )
    cmd = ["ffmpeg", "-i", "input.mp4", "out.mp4"]
    err = FFmpegProcessError(exit_code=1, command=cmd, stderr=stderr, stdout="some output")

    assert err.exit_code == 1
    assert err.command == tuple(cmd)
    assert err.stderr == stderr
    assert err.stdout == "some output"
    assert "кодом ошибки 1" in str(err)
    assert "Conversion failed!" in str(err)


def test_ffmpeg_timeout_error() -> None:
    cmd = ["ffmpeg", "-i", "input.mp4"]
    err = FFmpegTimeoutError(timeout_seconds=45.5, command=cmd)
    assert err.timeout_seconds == 45.5
    assert err.command == tuple(cmd)
    assert "45.5 сек" in str(err)


def test_ffmpeg_cancelled_error() -> None:
    cmd = ["ffmpeg", "-i", "input.mp4"]
    err = FFmpegCancelledError(command=cmd)
    assert err.command == tuple(cmd)
    assert "отменена" in str(err)


def test_ffprobe_error() -> None:
    err = FFprobeError("Invalid JSON", ["ffprobe", "in.mp4"], stderr="Parser fault")
    assert "Invalid JSON" in str(err)
    assert "ffprobe in.mp4" in str(err)
    assert "Parser fault" in str(err)


def test_invalid_input_error() -> None:
    err = InvalidInputError("missing.mp4", "Файл не найден")
    assert err.path == "missing.mp4"
    assert err.reason == "Файл не найден"
    assert "missing.mp4" in str(err)


def test_codec_not_found_error() -> None:
    err = CodecNotFoundError("libx266", "encoder")
    assert err.codec_name == "libx266"
    assert err.mode == "encoder"
    assert "libx266" in str(err)


def test_filter_error() -> None:
    err = FilterError("scale", "Неверные размеры 0x0")
    assert err.filter_name == "scale"
    assert err.reason == "Неверные размеры 0x0"
    assert "scale" in str(err)


def test_command_build_error() -> None:
    err = CommandBuildError("Не указан выходной файл")
    assert err.reason == "Не указан выходной файл"
    assert "Не указан выходной файл" in str(err)
