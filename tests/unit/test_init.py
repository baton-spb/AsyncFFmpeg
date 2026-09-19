"""Тест на целостность публичного API пакета aio_ffmpeg."""

import pytest

import aio_ffmpeg


def test_public_api_exports() -> None:
    """Проверяет, что все символы из __all__ доступны в корневом модуле пакета."""
    assert hasattr(aio_ffmpeg, "__all__")
    assert isinstance(aio_ffmpeg.__all__, list)
    assert len(aio_ffmpeg.__all__) > 50

    for name in aio_ffmpeg.__all__:
        assert hasattr(aio_ffmpeg, name), (
            f"Символ '{name}' объявлен в __all__, но не найден в aio_ffmpeg"
        )


def test_version_defined() -> None:
    """Проверяет наличие корректной версии пакета."""
    assert hasattr(aio_ffmpeg, "__version__")
    assert isinstance(aio_ffmpeg.__version__, str)
    assert aio_ffmpeg.__version__ == "0.1.1"


def test_async_ffmpeg_backward_compatibility() -> None:
    """Проверяет работоспособность обратной совместимости через async_ffmpeg."""
    with pytest.deprecated_call():
        import async_ffmpeg

    assert hasattr(async_ffmpeg, "FFmpegClient")
    assert async_ffmpeg.__version__ == aio_ffmpeg.__version__
