"""Unit-тесты для модуля обнаружения исполняемых файлов _discovery.py."""

from pathlib import Path
from unittest.mock import patch

import pytest

from aio_ffmpeg._discovery import (
    BinaryInfo,
    _parse_version_components,
    clear_discovery_cache,
    find_binary,
    find_ffmpeg,
    find_ffprobe,
    get_ffmpeg_info,
)
from aio_ffmpeg.exceptions import FFmpegNotFoundError


def test_parse_version_components() -> None:
    ver_str, major, minor, patch_ver = _parse_version_components(
        "ffmpeg version 9.0.1-full_build-www.gyan.dev Copyright (c) 2000-2026"
    )
    assert "9.0.1" in ver_str
    assert major == 9
    assert minor == 0
    assert patch_ver == 1

    _ver_str2, major2, minor2, patch2 = _parse_version_components(
        "ffprobe version 7.1 Copyright (c) 2007-2024"
    )
    assert major2 == 7
    assert minor2 == 1
    assert patch2 is None


def test_binary_info() -> None:
    info = BinaryInfo(
        name="ffmpeg",
        path=Path("dummy"),
        version_str="9.0.1",
        major=9,
        minor=0,
        patch=1,
    )
    assert info.name == "ffmpeg"
    assert info.major == 9
    assert not info.is_available


def test_find_binary_with_custom_file(tmp_path: Path) -> None:
    fake_ffmpeg = tmp_path / "custom_ffmpeg.exe"
    fake_ffmpeg.touch()

    clear_discovery_cache()
    found = find_binary("ffmpeg", custom_path=fake_ffmpeg)
    assert found == fake_ffmpeg.resolve()


def test_find_binary_with_custom_dir(tmp_path: Path) -> None:
    fake_bin = tmp_path / "ffmpeg.exe"
    fake_bin.touch()

    clear_discovery_cache()
    found = find_binary("ffmpeg", custom_path=tmp_path)
    assert found == fake_bin.resolve()


def test_find_binary_not_found() -> None:
    clear_discovery_cache()
    with (
        patch("shutil.which", return_value=None),
        patch("os.environ.get", return_value=None),
        pytest.raises(FFmpegNotFoundError) as exc_info,
    ):
        find_binary("nonexistent_binary_xyz_123")

    assert "nonexistent_binary_xyz_123" in str(exc_info.value)


def test_find_ffmpeg_and_ffprobe_in_system() -> None:
    """Проверка нахождения реальных ffmpeg и ffprobe в текущей системе."""
    clear_discovery_cache()
    ffmpeg_path = find_ffmpeg()
    assert ffmpeg_path.is_file()
    assert "ffmpeg" in ffmpeg_path.name.lower()

    ffprobe_path = find_ffprobe()
    assert ffprobe_path.is_file()
    assert "ffprobe" in ffprobe_path.name.lower()


@pytest.mark.asyncio
async def test_get_ffmpeg_info_real() -> None:
    clear_discovery_cache()
    info = await get_ffmpeg_info()
    assert info.name == "ffmpeg"
    assert info.is_available
    assert info.major is not None
    assert info.major >= 4
