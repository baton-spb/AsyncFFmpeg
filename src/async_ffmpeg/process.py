"""Асинхронный запуск процессов FFmpeg и FFprobe с контролем потоков, таймаутов и отмены."""

import asyncio
import inspect
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from async_ffmpeg._compat import get_subprocess_creation_kwargs, terminate_process_gracefully
from async_ffmpeg._constants import (
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_READ_BUFFER_SIZE,
    GRACEFUL_SHUTDOWN_TIMEOUT,
)
from async_ffmpeg._types import PathLike, ProgressCallback, StderrCallback
from async_ffmpeg.exceptions import (
    FFmpegCancelledError,
    FFmpegProcessError,
    FFmpegTimeoutError,
)


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """Результат выполнения команды FFmpeg/FFprobe."""

    exit_code: int
    stdout: bytes
    stderr: bytes
    duration_seconds: float
    command: tuple[str, ...]

    @property
    def success(self) -> bool:
        """Успешно ли завершился процесс (код возврата равен 0)."""
        return self.exit_code == 0

    @property
    def stdout_text(self) -> str:
        """Вывод stdout, декодированный в текстовую строку UTF-8."""
        return self.stdout.decode(errors="replace")

    @property
    def stderr_text(self) -> str:
        """Вывод stderr, декодированный в текстовую строку UTF-8."""
        return self.stderr.decode(errors="replace")


async def _invoke_callback(callback: Callable[..., Any], *args: Any) -> None:
    """Вызывает пользовательский коллбэк, поддерживая как синхронные, так и асинхронные функции."""
    try:
        if inspect.iscoroutinefunction(callback):
            await callback(*args)
        else:
            res = callback(*args)
            if inspect.isawaitable(res):
                await res
    except Exception:
        # Исключения в пользовательских коллбэках не должны ронять чтение потоков
        pass


class ProcessRunner:
    """Управляет асинхронным жизненным циклом подпроцессов FFmpeg/FFprobe.

    Обеспечивает:
    - Неблокирующий запуск через `asyncio.create_subprocess_exec`.
    - Ограничение числа параллельных процессов через `asyncio.Semaphore`.
    - Параллельное потоковое чтение stdout и stderr без блокировок и deadlock'ов.
    - Поддержку пользовательских коллбэков на строки stdout/stderr.
    - Корректную обработку таймаутов и отмены через `terminate_process_gracefully`.
    """

    def __init__(
        self,
        *,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        semaphore: asyncio.Semaphore | None = None,
        default_timeout: float | None = None,
        graceful_timeout: float = GRACEFUL_SHUTDOWN_TIMEOUT,
    ) -> None:
        self._max_concurrent = max(1, max_concurrent)
        self._semaphore = semaphore or asyncio.Semaphore(self._max_concurrent)
        self._default_timeout = default_timeout
        self._graceful_timeout = graceful_timeout
        self._active_processes: set[asyncio.subprocess.Process] = set()

    @property
    def max_concurrent(self) -> int:
        """Максимальное число одновременно выполняемых процессов."""
        return self._max_concurrent

    @property
    def active_count(self) -> int:
        """Число выполняющихся в данный момент подпроцессов."""
        return len(self._active_processes)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.cancel_all()

    async def cancel_all(self, *, graceful_timeout: float | None = None) -> None:
        """Грациозно завершает все текущие активные процессы раннера."""
        if not self._active_processes:
            return
        g_timeout = graceful_timeout if graceful_timeout is not None else self._graceful_timeout
        procs = list(self._active_processes)
        tasks = [
            terminate_process_gracefully(p, timeout=g_timeout)
            for p in procs
            if p.returncode is None
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def run(
        self,
        command: Sequence[str | Path],
        *,
        timeout: float | None = None,
        graceful_timeout: float | None = None,
        on_stdout_line: Callable[[str], Any] | None = None,
        on_stderr_line: StderrCallback | None = None,
        on_progress: ProgressCallback | None = None,
        check: bool = False,
        cwd: PathLike | None = None,
        env: dict[str, str] | None = None,
        read_buffer_size: int = DEFAULT_READ_BUFFER_SIZE,
    ) -> ProcessResult:
        """Запускает процесс FFmpeg/FFprobe и ожидает его завершения.

        Args:
            command: Список аргументов командной строки.
            timeout: Максимальное время выполнения в секундах (или default_timeout).
            graceful_timeout: Таймаут для штатного завершения ('q').
            on_stdout_line: Коллбэк для каждой прочитанной строки stdout.
            on_stderr_line: Коллбэк для каждой прочитанной строки stderr.
            on_progress: Коллбэк для блоков прогресса (если передаётся объект прогресса).
            check: Если True, при ненулевом коде возврата выбрасывает FFmpegProcessError.
            cwd: Рабочая директория подпроцесса.
            env: Словарь переменных окружения подпроцесса.
            read_buffer_size: Размер буфера при чтении потоков.

        Returns:
            ProcessResult с кодом возврата, stdout, stderr и длительностью.

        Raises:
            FFmpegTimeoutError: при превышении таймаута.
            FFmpegCancelledError: при отмене корутины.
            FFmpegProcessError: при check=True и ненулевом коде завершения.
        """
        cmd_strs = tuple(str(arg) for arg in command)
        effective_timeout = timeout if timeout is not None else self._default_timeout
        effective_graceful_timeout = (
            graceful_timeout if graceful_timeout is not None else self._graceful_timeout
        )
        creation_kwargs = get_subprocess_creation_kwargs()

        async with self._semaphore:
            start_time = time.monotonic()
            process: asyncio.subprocess.Process | None = None

            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd_strs,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(cwd) if cwd is not None else None,
                    env=env,
                    limit=read_buffer_size,
                    **creation_kwargs,
                )
                self._active_processes.add(process)

                stdout_chunks: list[bytes] = []
                stderr_chunks: list[bytes] = []

                async def _read_stream(
                    reader: asyncio.StreamReader,
                    chunks: list[bytes],
                    line_callback: Callable[..., Any] | None,
                ) -> None:
                    while True:
                        line = await reader.readline()
                        if not line:
                            break
                        chunks.append(line)
                        if line_callback:
                            decoded = line.decode(errors="replace").rstrip("\r\n")
                            await _invoke_callback(line_callback, decoded)

                assert process.stdout is not None
                assert process.stderr is not None

                stdout_task = asyncio.create_task(
                    _read_stream(process.stdout, stdout_chunks, on_stdout_line)
                )
                stderr_task = asyncio.create_task(
                    _read_stream(process.stderr, stderr_chunks, on_stderr_line)
                )

                # Ожидание процесса с таймаутом
                try:
                    if effective_timeout is not None:
                        await asyncio.wait_for(
                            asyncio.gather(process.wait(), stdout_task, stderr_task),
                            timeout=effective_timeout,
                        )
                    else:
                        await asyncio.gather(process.wait(), stdout_task, stderr_task)
                except TimeoutError as err:
                    await terminate_process_gracefully(process, timeout=effective_graceful_timeout)
                    await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
                    raise FFmpegTimeoutError(
                        timeout_seconds=effective_timeout or 0.0,
                        command=cmd_strs,
                    ) from err
                except asyncio.CancelledError as err:
                    await terminate_process_gracefully(process, timeout=effective_graceful_timeout)
                    await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
                    raise FFmpegCancelledError(command=cmd_strs) from err

                exit_code = process.returncode if process.returncode is not None else -1
                duration = time.monotonic() - start_time
                stdout_bytes = b"".join(stdout_chunks)
                stderr_bytes = b"".join(stderr_chunks)

                result = ProcessResult(
                    exit_code=exit_code,
                    stdout=stdout_bytes,
                    stderr=stderr_bytes,
                    duration_seconds=duration,
                    command=cmd_strs,
                )

                if check and not result.success:
                    raise FFmpegProcessError(
                        exit_code=exit_code,
                        command=cmd_strs,
                        stderr=result.stderr_text,
                        stdout=result.stdout_text,
                    )

                return result

            finally:
                if process is not None:
                    self._active_processes.discard(process)
