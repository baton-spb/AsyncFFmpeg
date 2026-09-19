"""Пример консольного прогресс-бара для FFmpeg."""

import asyncio
import sys
from pathlib import Path

from async_ffmpeg import FFmpegClient, ProgressInfo


def render_bar(percentage: float | None, width: int = 30) -> str:
    """Отрисовывает текстовый прогресс-бар."""
    if percentage is None:
        return "[⏳ Подготовка...]"
    filled = int(width * (percentage / 100.0))
    bar = "=" * filled + (">" if filled < width else "")
    return f"[{bar:<{width}}] {percentage:>5.1f}%"


async def main() -> None:
    if len(sys.argv) < 3:
        print("Использование: python progress_cli.py <входной_файл> <выходной_файл>")
        return

    in_file = Path(sys.argv[1])
    out_file = Path(sys.argv[2])

    client = FFmpegClient()

    def on_progress(p: ProgressInfo) -> None:
        bar = render_bar(p.percentage, width=25)
        spd = f"{p.speed}x" if p.speed is not None else "?x"
        fps = f"{p.fps:.0f}"
        eta = f"{p.eta_seconds:.0f}s" if p.eta_seconds is not None else "?s"
        sys.stdout.write(f"\r{bar} | FPS: {fps:>3} | Скорость: {spd:>5} | ETA: {eta:>4} ")
        sys.stdout.flush()

    await client.scale(
        input=in_file,
        output=out_file,
        width=1280,
        height=720,
        on_progress=on_progress,
    )
    print("\nГотово!")


if __name__ == "__main__":
    asyncio.run(main())
