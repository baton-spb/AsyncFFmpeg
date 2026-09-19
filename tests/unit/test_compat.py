"""Unit-тесты для модуля кроссплатформенной совместимости _compat.py."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from aio_ffmpeg._compat import (
    IS_WINDOWS,
    escape_filter_path,
    get_subprocess_creation_kwargs,
    normalize_path_for_ffmpeg,
    terminate_process_gracefully,
)


def test_subprocess_creation_kwargs() -> None:
    kwargs = get_subprocess_creation_kwargs()
    if IS_WINDOWS:
        assert "creationflags" in kwargs
    else:
        assert kwargs.get("start_new_session") is True


def test_normalize_path_for_ffmpeg() -> None:
    raw_path = "C:\\videos\\sample file.mp4"
    normalized = normalize_path_for_ffmpeg(raw_path)
    if IS_WINDOWS:
        assert "\\" not in normalized
        assert "videos/sample file.mp4" in normalized


def test_escape_filter_path() -> None:
    raw_path = "C:\\media\\test.mp4"
    escaped = escape_filter_path(raw_path)
    if IS_WINDOWS:
        assert "C\\:" in escaped
        assert "\\" not in escaped.replace("C\\:", "")


@pytest.mark.asyncio
async def test_terminate_process_gracefully_already_done() -> None:
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    code = await terminate_process_gracefully(mock_proc)
    assert code == 0


@pytest.mark.asyncio
async def test_terminate_process_gracefully_via_stdin_q() -> None:
    mock_proc = MagicMock()
    mock_proc.returncode = None
    mock_stdin = MagicMock()
    mock_stdin.is_closing.return_value = False
    mock_stdin.drain = AsyncMock()
    mock_stdin.close = MagicMock()
    mock_proc.stdin = mock_stdin

    # wait() возвращает 0 после отправки q
    mock_proc.wait = AsyncMock(return_value=0)

    code = await terminate_process_gracefully(mock_proc, timeout=0.1)
    assert code == 0
    mock_stdin.write.assert_called_once_with(b"q\n")
