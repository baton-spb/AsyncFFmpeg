"""Общие фикстуры и настройки для набора тестов async-ffmpeg."""

import pytest


@pytest.fixture
def sample_ffmpeg_command() -> list[str]:
    """Пример валидной команды FFmpeg для тестов."""
    return ["ffmpeg", "-y", "-i", "input.mp4", "-c:v", "libx264", "output.mp4"]
