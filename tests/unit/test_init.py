"""Тест на целостность публичного API пакета async_ffmpeg."""

import async_ffmpeg


def test_public_api_exports() -> None:
    """Проверяет, что все символы из __all__ доступны в корневом модуле пакета."""
    assert hasattr(async_ffmpeg, "__all__")
    assert isinstance(async_ffmpeg.__all__, list)
    assert len(async_ffmpeg.__all__) > 50

    for name in async_ffmpeg.__all__:
        assert hasattr(async_ffmpeg, name), (
            f"Символ '{name}' объявлен в __all__, но не найден в async_ffmpeg"
        )


def test_version_defined() -> None:
    """Проверяет наличие корректной версии пакета."""
    assert hasattr(async_ffmpeg, "__version__")
    assert isinstance(async_ffmpeg.__version__, str)
    assert async_ffmpeg.__version__ == "0.1.0"
