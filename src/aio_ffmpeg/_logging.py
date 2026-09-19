"""Настройка и управление структурированным логированием для библиотеки async-ffmpeg."""

import logging

LOGGER_NAME = "aio_ffmpeg"

logger = logging.getLogger(LOGGER_NAME)


def get_logger(submodule: str | None = None) -> logging.Logger:
    """Возвращает экземпляр регистратора для заданного подмодуля библиотеки.

    Args:
        submodule: Имя подмодуля (например, 'process', 'discovery', 'client').
                   Если None, возвращается корневой логгер библиотеки.

    Returns:
        Экземпляр logging.Logger с иерархическим именем 'aio_ffmpeg.<submodule>'.
    """
    if submodule:
        return logging.getLogger(f"{LOGGER_NAME}.{submodule}")
    return logger
