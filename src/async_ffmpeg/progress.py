"""Парсер машиночитаемого прогресса FFmpeg (-progress pipe:1).

FFmpeg выводит прогресс блоками key=value, завершающимися строкой progress=continue или progress=end.
Модуль транслирует сырые строки в строго типизированные объекты `ProgressInfo` с автоматическим
расчётом процента выполнения (percent) и примерного времени завершения (ETA).
"""

import re
from collections.abc import AsyncIterator, Awaitable
from dataclasses import dataclass
from typing import Any

from async_ffmpeg._types import ProgressCallback

_BITRATE_REGEX = re.compile(r"([\d.]+)\s*kbits?/s", re.IGNORECASE)
_SPEED_REGEX = re.compile(r"([\d.]+)x?", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ProgressInfo:
    """Структура одного блока прогресса FFmpeg."""

    frame: int | None
    fps: float
    bitrate_kbits: float | None
    bitrate_raw: str
    total_size: int | None
    out_time_us: int
    out_time_ms: int
    out_time: str
    dup_frames: int
    drop_frames: int
    speed: float | None
    speed_raw: str
    is_finished: bool
    stream_q: dict[str, float]
    total_duration: float | None = None

    @property
    def out_time_seconds(self) -> float:
        """Текущее обработанное время видео/аудио в секундах."""
        return self.out_time_us / 1_000_000.0

    @property
    def percent(self) -> float | None:
        """Процент завершения от 0.0 до 100.0 (если известна общая длительность)."""
        if self.is_finished:
            return 100.0
        if self.total_duration is not None and self.total_duration > 0:
            pct = (self.out_time_seconds / self.total_duration) * 100.0
            return min(100.0, max(0.0, pct))
        return None

    @property
    def eta_seconds(self) -> float | None:
        """Примерное оставшееся время в секундах (если известны общая длительность и скорость)."""
        if self.is_finished:
            return 0.0
        if (
            self.total_duration is not None
            and self.total_duration > 0
            and self.speed is not None
            and self.speed > 0
        ):
            remaining = max(0.0, self.total_duration - self.out_time_seconds)
            return remaining / self.speed
        return None


def _parse_int_or_none(value: str) -> int | None:
    """Парсит целое число, возвращая None при 'N/A' или ошибке."""
    val = value.strip()
    if val.upper() == "N/A" or not val:
        return None
    try:
        return int(val)
    except ValueError:
        return None


def _parse_float_or_zero(value: str) -> float:
    """Парсит вещественное число, возвращая 0.0 при 'N/A' или ошибке."""
    val = value.strip()
    if val.upper() == "N/A" or not val:
        return 0.0
    try:
        return float(val)
    except ValueError:
        return 0.0


def _parse_bitrate(raw_bitrate: str) -> float | None:
    """Парсит значение битрейта (например '93.6kbits/s') в число килобит/с."""
    clean = raw_bitrate.strip()
    if clean.upper() == "N/A" or not clean:
        return None
    match = _BITRATE_REGEX.search(clean)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    try:
        return float(clean)
    except ValueError:
        return None


def _parse_speed(raw_speed: str) -> float | None:
    """Парсит значение скорости (например ' 2.32x' или '15x') в множитель."""
    clean = raw_speed.strip()
    if clean.upper() == "N/A" or not clean:
        return None
    match = _SPEED_REGEX.search(clean)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


class ProgressParser:
    """Построчный парсер потока `-progress pipe:1` от процесса FFmpeg.

    Накапливает строки key=value и при получении ключа `progress` формирует `ProgressInfo`.
    """

    def __init__(
        self,
        *,
        total_duration: float | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self.total_duration = total_duration
        self._on_progress = on_progress
        self._current_block: dict[str, str] = {}
        self._buffer = ""

    def feed_line(self, line: str) -> ProgressInfo | None:
        """Обрабатывает одну строку stdout от FFmpeg.

        Returns:
            Сформированный `ProgressInfo`, если строка была 'progress=continue|end', иначе None.
        """
        stripped = line.strip()
        if not stripped or "=" not in stripped:
            return None

        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()

        if key != "progress":
            self._current_block[key] = value
            return None

        # Ключ 'progress' сигнализирует о завершении текущего блока
        is_finished = value.lower() == "end"
        block = self._current_block
        self._current_block = {}

        stream_q: dict[str, float] = {}
        for k, v in block.items():
            if k.startswith("stream_") and k.endswith("_q"):
                with_val = _parse_float_or_zero(v)
                stream_q[k] = with_val

        out_time_us = _parse_int_or_none(block.get("out_time_us", "0")) or 0
        out_time_ms = _parse_int_or_none(block.get("out_time_ms", "0")) or (out_time_us // 1000)
        raw_bitrate = block.get("bitrate", "N/A")
        raw_speed = block.get("speed", "N/A")

        return ProgressInfo(
            frame=_parse_int_or_none(block.get("frame", "")),
            fps=_parse_float_or_zero(block.get("fps", "0")),
            bitrate_kbits=_parse_bitrate(raw_bitrate),
            bitrate_raw=raw_bitrate,
            total_size=_parse_int_or_none(block.get("total_size", "")),
            out_time_us=out_time_us,
            out_time_ms=out_time_ms,
            out_time=block.get("out_time", "00:00:00.000000"),
            dup_frames=_parse_int_or_none(block.get("dup_frames", "0")) or 0,
            drop_frames=_parse_int_or_none(block.get("drop_frames", "0")) or 0,
            speed=_parse_speed(raw_speed),
            speed_raw=raw_speed,
            is_finished=is_finished,
            stream_q=stream_q,
            total_duration=self.total_duration,
        )

    def feed_chunk(self, chunk: str | bytes) -> list[ProgressInfo]:
        """Обрабатывает произвольный фрагмент текста или байт, разбивая на строки."""
        text = chunk.decode(errors="replace") if isinstance(chunk, bytes) else chunk
        self._buffer += text
        lines = self._buffer.split("\n")
        self._buffer = lines.pop()  # остаток неполной строки

        results: list[ProgressInfo] = []
        for line in lines:
            info = self.feed_line(line)
            if info is not None:
                results.append(info)
        return results


async def parse_progress_stream(
    stream: Any,
    *,
    total_duration: float | None = None,
    on_progress: ProgressCallback | None = None,
) -> AsyncIterator[ProgressInfo]:
    """Асинхронный генератор, читающий поток строк и отдающий объекты ProgressInfo."""
    parser = ProgressParser(total_duration=total_duration, on_progress=on_progress)
    while True:
        line_bytes = await stream.readline()
        if not line_bytes:
            break
        line_str = line_bytes.decode(errors="replace")
        info = parser.feed_line(line_str)
        if info is not None:
            if on_progress:
                res = on_progress(info)
                if isinstance(res, Awaitable):
                    await res
            yield info
