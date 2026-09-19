"""Нагрузочные тесты параллелизма и контроля ресурсов (Phase 13)."""

import asyncio
from pathlib import Path

import pytest

from async_ffmpeg import FFmpegCancelledError, FFmpegClient


@pytest.mark.asyncio
async def test_concurrent_execution_limit(tmp_path: Path) -> None:
    """Проверяет, что max_concurrent строго ограничивает число одновременно работающих процессов."""
    max_concurrent = 2
    total_tasks = 5
    client = FFmpegClient(max_concurrent=max_concurrent)

    observed_active: list[int] = []

    async def run_single_task(idx: int) -> None:
        out_file = tmp_path / f"task_{idx}.mp4"
        # Сохраняем мгновенное число активных процессов
        observed_active.append(client.active_processes)

        pipeline = (
            client.pipeline()
            .input("color=c=black:s=160x120:d=0.6", f="lavfi")
            .video_codec("libx264", preset="ultrafast")
            .output(out_file)
        )
        await pipeline.run()
        observed_active.append(client.active_processes)

    # Запускаем параллельно 5 задач
    await asyncio.gather(*(run_single_task(i) for i in range(total_tasks)))

    # Убеждаемся, что счетчик ни разу не превысил лимит
    assert max(observed_active) <= max_concurrent
    # После завершения всех задач активных процессов должно быть 0
    assert client.active_processes == 0


@pytest.mark.asyncio
async def test_concurrent_cancellation_stress(tmp_path: Path) -> None:
    """Проверяет корректное прерывание нескольких параллельных процессов без зависаний."""
    client = FFmpegClient(max_concurrent=4)

    async def run_long_job(idx: int) -> None:
        out_file = tmp_path / f"long_{idx}.mp4"
        cmd = (
            client.create_command()
            .overwrite()
            .input("color=c=red:s=320x240:d=60.0", f="lavfi")
            .video_codec("libx264")
            .preset("ultrafast")
            .output(out_file)
        )
        await cmd.execute(process_runner=client.runner)

    tasks = [asyncio.create_task(run_long_job(i)) for i in range(4)]

    # Даем процессам запуститься
    await asyncio.sleep(0.05)

    # Отменяем все задачи
    for t in tasks:
        t.cancel()

    # Ожидаем завершения с перехватом исключений
    results = await asyncio.gather(*tasks, return_exceptions=True)

    cancelled_count = sum(
        1 for res in results if isinstance(res, (asyncio.CancelledError, FFmpegCancelledError))
    )
    assert cancelled_count > 0

    # Убеждаемся, что семафор освобожден и активных процессов нет
    assert client.active_processes == 0
