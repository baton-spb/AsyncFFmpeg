"""Тесты для модуля структурированного логирования aio_ffmpeg._logging."""

import logging

import pytest

from aio_ffmpeg import get_logger, logger
from aio_ffmpeg._logging import LOGGER_NAME
from aio_ffmpeg.process import _invoke_callback


def test_logger_hierarchy() -> None:
    """Проверяет правильность иерархии имен регистраторов логирования."""
    root_log = get_logger()
    assert root_log.name == LOGGER_NAME
    assert root_log is logger

    process_log = get_logger("process")
    assert process_log.name == f"{LOGGER_NAME}.process"

    discovery_log = get_logger("discovery")
    assert discovery_log.name == f"{LOGGER_NAME}.discovery"

    client_log = get_logger("client")
    assert client_log.name == f"{LOGGER_NAME}.client"

    pipeline_log = get_logger("pipeline")
    assert pipeline_log.name == f"{LOGGER_NAME}.pipeline"

    hardware_log = get_logger("hardware")
    assert hardware_log.name == f"{LOGGER_NAME}.hardware"

    probe_log = get_logger("probe")
    assert probe_log.name == f"{LOGGER_NAME}.probe"


@pytest.mark.asyncio
async def test_invoke_callback_logs_exception(caplog: pytest.LogCaptureFixture) -> None:
    """Проверяет логирование исключений из пользовательских коллбэков."""

    def _failing_callback(msg: str) -> None:
        raise ValueError(f"Тестовая ошибка коллбэка: {msg}")

    with caplog.at_level(logging.ERROR, logger="aio_ffmpeg.process"):
        # Вызов не должен выбрасывать исключение наружу
        await _invoke_callback(_failing_callback, "тест")

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelname == "ERROR"
    assert "Необработанное исключение в пользовательском коллбэке" in record.message
    assert record.exc_info is not None


@pytest.mark.asyncio
async def test_async_invoke_callback_logs_exception(caplog: pytest.LogCaptureFixture) -> None:
    """Проверяет логирование исключений из асинхронных пользовательских коллбэков."""

    async def _async_failing_callback(msg: str) -> None:
        raise RuntimeError(f"Асинхронная ошибка: {msg}")

    with caplog.at_level(logging.ERROR, logger="aio_ffmpeg.process"):
        await _invoke_callback(_async_failing_callback, "async_тест")

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelname == "ERROR"
    assert "Необработанное исключение в пользовательском коллбэке" in record.message
