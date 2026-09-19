"""Unit-тесты для ProcessRunner и ProcessResult (process.py)."""

import asyncio
import sys

import pytest

from async_ffmpeg.exceptions import (
    FFmpegCancelledError,
    FFmpegProcessError,
    FFmpegTimeoutError,
)
from async_ffmpeg.process import ProcessResult, ProcessRunner


def test_process_result_properties() -> None:
    res = ProcessResult(
        exit_code=0,
        stdout=b"output data\n",
        stderr=b"some log\n",
        duration_seconds=1.25,
        command=("ffmpeg", "-version"),
    )
    assert res.success is True
    assert res.stdout_text == "output data\n"
    assert res.stderr_text == "some log\n"
    assert res.duration_seconds == 1.25
    assert res.command == ("ffmpeg", "-version")

    res_fail = ProcessResult(
        exit_code=1,
        stdout=b"",
        stderr=b"error",
        duration_seconds=0.1,
        command=("ffmpeg",),
    )
    assert res_fail.success is False


@pytest.mark.asyncio
async def test_process_runner_run_simple_success() -> None:
    runner = ProcessRunner()
    cmd = [sys.executable, "-c", "print('stdout line 1'); print('stdout line 2')"]
    result = await runner.run(cmd, check=True)

    assert result.success is True
    assert result.exit_code == 0
    assert "stdout line 1" in result.stdout_text
    assert "stdout line 2" in result.stdout_text
    assert result.duration_seconds >= 0


@pytest.mark.asyncio
async def test_process_runner_streaming_callbacks() -> None:
    runner = ProcessRunner()
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    def on_out(line: str) -> None:
        stdout_lines.append(line)

    async def on_err(line: str) -> None:
        stderr_lines.append(line)

    script = (
        "import sys; "
        "sys.stdout.write('out1\\nout2\\n'); sys.stdout.flush(); "
        "sys.stderr.write('err1\\n'); sys.stderr.flush(); "
    )
    cmd = [sys.executable, "-c", script]

    result = await runner.run(
        cmd,
        on_stdout_line=on_out,
        on_stderr_line=on_err,
    )

    assert result.success is True
    assert stdout_lines == ["out1", "out2"]
    assert stderr_lines == ["err1"]


@pytest.mark.asyncio
async def test_process_runner_check_failure_raises() -> None:
    runner = ProcessRunner()
    cmd = [sys.executable, "-c", "import sys; sys.stderr.write('critical error\\n'); sys.exit(2)"]

    with pytest.raises(FFmpegProcessError) as exc_info:
        await runner.run(cmd, check=True)

    err = exc_info.value
    assert err.exit_code == 2
    assert "critical error" in err.stderr


@pytest.mark.asyncio
async def test_process_runner_timeout_raises() -> None:
    runner = ProcessRunner(graceful_timeout=0.1)
    cmd = [sys.executable, "-c", "import time; time.sleep(5)"]

    with pytest.raises(FFmpegTimeoutError) as exc_info:
        await runner.run(cmd, timeout=0.1)

    err = exc_info.value
    assert err.timeout_seconds == 0.1


@pytest.mark.asyncio
async def test_process_runner_cancellation() -> None:
    runner = ProcessRunner(graceful_timeout=0.1)
    cmd = [sys.executable, "-c", "import time; time.sleep(10)"]

    task = asyncio.create_task(runner.run(cmd))
    await asyncio.sleep(0.1)
    task.cancel()

    with pytest.raises(FFmpegCancelledError):
        await task


@pytest.mark.asyncio
async def test_process_runner_concurrency_semaphore() -> None:
    max_concurrency = 2
    runner = ProcessRunner(max_concurrent=max_concurrency)
    max_observed_concurrent = 0

    async def on_line(_: str) -> None:
        nonlocal max_observed_concurrent
        max_observed_concurrent = max(max_observed_concurrent, runner.active_count)

    async def worker() -> None:
        await runner.run(
            [sys.executable, "-c", "import time; print('running'); time.sleep(0.05)"],
            on_stdout_line=on_line,
        )

    await asyncio.gather(*(worker() for _ in range(5)))
    assert max_observed_concurrent <= max_concurrency
    assert max_observed_concurrent >= 1


@pytest.mark.asyncio
async def test_process_runner_context_manager() -> None:
    async with ProcessRunner() as runner:
        res = await runner.run([sys.executable, "-c", "print('inside cm')"])
        assert res.success is True
        assert "inside cm" in res.stdout_text
