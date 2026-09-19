"""Кроссплатформенная совместимость для управления подпроцессами и путями FFmpeg.

Обеспечивает корректное создание групп процессов, отправку сигналов завершения
и нормализацию путей для синтаксиса фильтров FFmpeg на Windows, Linux и macOS.
"""

import asyncio
import os
import signal
import subprocess
import sys
from contextlib import suppress

from async_ffmpeg._constants import FORCE_KILL_TIMEOUT, GRACEFUL_SHUTDOWN_TIMEOUT
from async_ffmpeg._types import PathLike

IS_WINDOWS: bool = sys.platform == "win32"
IS_MACOS: bool = sys.platform == "darwin"
IS_LINUX: bool = sys.platform.startswith("linux")


def get_subprocess_creation_kwargs() -> dict[str, int | bool]:
    """Возвращает платформо-зависимые аргументы для `asyncio.create_subprocess_exec`.

    - На Windows: предотвращает всплытие консольного окна и создаёт новую группу процессов.
    - На Unix: создаёт новую сессию (`start_new_session=True`), изолируя процесс от родителя.

    Returns:
        Словарь платформенных аргументов для создания подпроцесса.
    """
    kwargs: dict[str, int | bool] = {}
    if IS_WINDOWS:
        flags = 0
        # Предотвращение создания окна консоли в фоновом режиме
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            flags |= subprocess.CREATE_NO_WINDOW
        if flags:
            kwargs["creationflags"] = flags
    else:
        # Изоляция группы процессов на Unix
        kwargs["start_new_session"] = True
    return kwargs


async def terminate_process_gracefully(
    process: asyncio.subprocess.Process,
    *,
    timeout: float = GRACEFUL_SHUTDOWN_TIMEOUT,
    force_timeout: float = FORCE_KILL_TIMEOUT,
) -> int:
    """Грациозно завершает процесс FFmpeg.

    Порядок попыток:
    1. Отправка символа 'q' в stdin (штатный механизм FFmpeg для финализации контейнеров).
    2. Ожидание завершения до `timeout` секунд.
    3. Если процесс не завершился: SIGINT (Unix) или `process.terminate()`.
    4. Ожидание до `force_timeout` секунд.
    5. Принудительное уничтожение через `process.kill()`.

    Returns:
        Код возврата процесса (returncode).
    """
    if process.returncode is not None:
        return process.returncode

    # Шаг 1: попытка отправки команды 'q' в stdin
    if process.stdin and not process.stdin.is_closing():
        try:
            process.stdin.write(b"q\n")
            await process.stdin.drain()
            with suppress(Exception):
                process.stdin.close()
        except BrokenPipeError, ConnectionResetError, OSError:
            pass

    # Ожидаем завершения после команды 'q'
    try:
        return await asyncio.wait_for(process.wait(), timeout=timeout)
    except TimeoutError:
        pass

    killpg_fn = getattr(os, "killpg", None)
    getpgid_fn = getattr(os, "getpgid", None)

    # Шаг 2: отправка сигнала прерывания
    if process.returncode is None:
        try:
            if not IS_WINDOWS and callable(killpg_fn) and callable(getpgid_fn):
                # Посылаем сигнал всей группе процессов на Unix
                try:
                    killpg_fn(getpgid_fn(process.pid), signal.SIGINT)
                except ProcessLookupError, PermissionError:
                    process.send_signal(signal.SIGINT)
            else:
                process.terminate()
        except ProcessLookupError, OSError:
            pass

    # Ожидаем после прерывания
    try:
        return await asyncio.wait_for(process.wait(), timeout=force_timeout)
    except TimeoutError:
        pass

    # Шаг 3: принудительный kill
    if process.returncode is None:
        try:
            if not IS_WINDOWS and callable(killpg_fn) and callable(getpgid_fn):
                sigkill = getattr(signal, "SIGKILL", signal.SIGTERM)
                try:
                    killpg_fn(getpgid_fn(process.pid), sigkill)
                except ProcessLookupError, PermissionError:
                    process.kill()
            else:
                process.kill()
        except ProcessLookupError, OSError:
            pass

    return await process.wait()


def normalize_path_for_ffmpeg(path: PathLike) -> str:
    """Преобразует путь к файлу в формат, совместимый с FFmpeg.

    На Windows заменяет обратные слэши `\\` на прямые `/`, чтобы избежать
    ошибочной интерпретации экранирующих последовательностей в CLI и фильтрах.
    Сохраняет относительные пути, сетевые URL и специальные выражения (lavfi, pipe).

    Args:
        path: Исходный путь к файлу или URL.

    Returns:
        Нормализованная строка пути с прямыми слэшами.
    """
    str_path = str(path)
    if IS_WINDOWS:
        str_path = str_path.replace("\\", "/")
    return str_path


def escape_filter_path(path: PathLike) -> str:
    """Экранирует путь для использования внутри выражений filtergraph FFmpeg.

    В filtergraph двоеточие (`:`) и обратный слэш (`\\`) являются спецсимволами.
    Например: `C:/path/video.mp4` -> `C\\:/path/video.mp4`.

    Args:
        path: Исходный путь к файлу.

    Returns:
        Экранированная строка пути, безопасная для подстановки в filtergraph.
    """
    normalized = normalize_path_for_ffmpeg(path)
    # Экранируем двоеточия (букву диска на Windows, e.g. C:)
    return normalized.replace(":", "\\:")


def get_null_device() -> str:
    """Возвращает платформенное псевдоустройство отбрасывания данных (NUL на Windows, /dev/null на Unix)."""
    return "NUL" if IS_WINDOWS else "/dev/null"

