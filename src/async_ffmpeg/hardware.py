"""Модуль обнаружения и настройки аппаратного ускорения (Hardware Acceleration) для FFmpeg.

Поддерживает:
- Парсинг и обнаружение поддерживаемых аппаратных ускорителей (-hwaccels):
  CUDA, NVENC/NVDEC, Intel QSV, AMD AMF, Apple VideoToolbox, VAAPI, D3D11VA, DXVA2, MediaFoundation.
- Парсинг и классификацию энкодеров и декодеров (-encoders, -decoders).
- Интеллектуальный выбор оптимального энкодера (best_encoder) с fallback на процессор.
- Проверку реальной работоспособности видеоэнкодера с текущими драйверами системы (test_encoder).
- Генерацию аргументов командной строки FFmpeg для аппаратного декодирования/фильтрации.
"""

import re
from dataclasses import dataclass
from typing import Literal

from async_ffmpeg._compat import IS_WINDOWS
from async_ffmpeg._discovery import find_ffmpeg
from async_ffmpeg._types import PathLike
from async_ffmpeg.process import ProcessRunner

type HWAccelType = Literal[
    "cuda",
    "nvenc",
    "qsv",
    "d3d11va",
    "d3d12va",
    "dxva2",
    "amf",
    "videotoolbox",
    "vaapi",
    "opencl",
    "vulkan",
    "mediafoundation",
    "none",
]

type CodecType = Literal["video", "audio", "subtitle"]
type HardwareVendor = Literal["nvidia", "intel", "amd", "apple", "microsoft", "generic"]


@dataclass(frozen=True, slots=True)
class EncoderInfo:
    """Информация о кодировщике (энкодере) FFmpeg."""

    name: str
    codec: str
    description: str
    media_type: CodecType
    is_hardware: bool
    vendor: HardwareVendor
    frame_threading: bool = False
    slice_threading: bool = False
    experimental: bool = False


@dataclass(frozen=True, slots=True)
class DecoderInfo:
    """Информация о декодировщике (декодере) FFmpeg."""

    name: str
    codec: str
    description: str
    media_type: CodecType
    is_hardware: bool
    vendor: HardwareVendor


@dataclass(frozen=True, slots=True)
class HWAccelConfig:
    """Конфигурация параметров аппаратного ускорения для команды FFmpeg."""

    name: str
    device: str | None = None
    output_format: str | None = None
    extra_options: tuple[tuple[str, str], ...] = ()

    def to_ffmpeg_args(self) -> list[str]:
        """Формирует список аргументов CLI FFmpeg для подключения аппаратного ускорения."""
        args: list[str] = ["-hwaccel", self.name]
        if self.device is not None:
            args.extend(["-hwaccel_device", self.device])
        if self.output_format is not None:
            args.extend(["-hwaccel_output_format", self.output_format])
        for k, v in self.extra_options:
            args.extend([f"-{k.lstrip('-')}", str(v)])
        return args


@dataclass(frozen=True, slots=True)
class HardwareCapability:
    """Снимок аппаратных возможностей текущей системы и сборки FFmpeg."""

    available_accels: tuple[str, ...]
    encoders: tuple[EncoderInfo, ...]
    decoders: tuple[DecoderInfo, ...]

    @property
    def has_cuda(self) -> bool:
        """Доступно ли ускорение NVIDIA CUDA."""
        return "cuda" in self.available_accels

    @property
    def has_nvenc(self) -> bool:
        """Доступен ли аппаратный кодировщик NVIDIA NVENC."""
        return any(e.vendor == "nvidia" and e.is_hardware for e in self.encoders)

    @property
    def has_qsv(self) -> bool:
        """Доступно ли аппаратное ускорение Intel Quick Sync Video (QSV)."""
        return "qsv" in self.available_accels or any(
            e.vendor == "intel" and e.is_hardware for e in self.encoders
        )

    @property
    def has_amf(self) -> bool:
        """Доступно ли аппаратное кодирование AMD AMF."""
        return "amf" in self.available_accels or any(
            e.vendor == "amd" and e.is_hardware for e in self.encoders
        )

    @property
    def has_d3d11va(self) -> bool:
        """Доступно ли аппаратное декодирование Direct3D 11 (Windows)."""
        return "d3d11va" in self.available_accels

    @property
    def has_dxva2(self) -> bool:
        """Доступно ли аппаратное декодирование DXVA2 (Windows)."""
        return "dxva2" in self.available_accels

    @property
    def has_videotoolbox(self) -> bool:
        """Доступно ли аппаратное ускорение Apple VideoToolbox (macOS)."""
        return "videotoolbox" in self.available_accels or any(
            e.vendor == "apple" and e.is_hardware for e in self.encoders
        )

    @property
    def has_vaapi(self) -> bool:
        """Доступно ли ускорение VAAPI (Linux)."""
        return "vaapi" in self.available_accels or any(
            e.vendor == "generic" and e.is_hardware and "vaapi" in e.name for e in self.encoders
        )

    @property
    def has_mediafoundation(self) -> bool:
        """Доступно ли ускорение Microsoft MediaFoundation (Windows)."""
        return any(e.vendor == "microsoft" and e.is_hardware for e in self.encoders)


def _detect_vendor_and_hw(name: str, desc: str) -> tuple[bool, HardwareVendor]:
    """Определяет, является ли кодек аппаратным, и выявляет вендора оборудования."""
    low_name = name.lower()
    low_desc = desc.lower()

    if "nvenc" in low_name or "cuvid" in low_name or "cuda" in low_desc:
        return True, "nvidia"
    if "qsv" in low_name or "quick sync" in low_desc:
        return True, "intel"
    if "amf" in low_name or "amd" in low_desc:
        return True, "amd"
    if "videotoolbox" in low_name or "videotoolbox" in low_desc:
        return True, "apple"
    if low_name.endswith("_mf") or "mediafoundation" in low_desc:
        return True, "microsoft"
    if "vaapi" in low_name or "d3d11va" in low_name or "dxva2" in low_name or "v4l2m2m" in low_name:
        return True, "generic"

    return False, "generic"


def parse_hwaccels_output(output: str) -> list[str]:
    """Парсит вывод команды `ffmpeg -hwaccels`.

    Извлекает список поддерживаемых методов аппаратного ускорения.
    """
    lines = output.splitlines()
    accels: list[str] = []
    header_found = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if "Hardware acceleration methods:" in stripped:
            header_found = True
            continue
        if header_found and " " not in stripped and not stripped.startswith("-"):
            # Методы перечисляются по одному на строку
            accels.append(stripped)

    return accels


def parse_encoders_output(output: str) -> list[EncoderInfo]:
    """Парсит вывод команды `ffmpeg -encoders`.

    Строка энкодера имеет вид:
    ` V....D libx264              libx264 H.264 / AVC / MPEG-4 AVC ... (codec h264)`
    """
    lines = output.splitlines()
    encoders: list[EncoderInfo] = []
    header_passed = False

    # Регулярное выражение для разбора строки энкодера FFmpeg
    # 6 флагов, пробелы, имя, пробелы, описание
    pattern = re.compile(r"^\s*([VAS])([F.])([S.])([X.])([B.])([D.])\s+([a-zA-Z0-9_\-]+)\s+(.*)$")
    codec_pattern = re.compile(r"\(codec\s+([a-zA-Z0-9_\-]+)\)")

    for line in lines:
        if not header_passed:
            if line.strip().startswith("------"):
                header_passed = True
            continue

        match = pattern.match(line)
        if not match:
            continue

        media_flag, f_flag, s_flag, x_flag, _, _, name, desc = match.groups()

        media_type: CodecType = "video"
        if media_flag == "A":
            media_type = "audio"
        elif media_flag == "S":
            media_type = "subtitle"

        codec_match = codec_pattern.search(desc)
        codec = codec_match.group(1) if codec_match else name

        is_hw, vendor = _detect_vendor_and_hw(name, desc)

        encoders.append(
            EncoderInfo(
                name=name,
                codec=codec,
                description=desc.strip(),
                media_type=media_type,
                is_hardware=is_hw,
                vendor=vendor,
                frame_threading=(f_flag == "F"),
                slice_threading=(s_flag == "S"),
                experimental=(x_flag == "X"),
            )
        )

    return encoders


def parse_decoders_output(output: str) -> list[DecoderInfo]:
    """Парсит вывод команды `ffmpeg -decoders`.

    Строка декодера имеет вид:
    ` V....D h264                 H.264 / AVC / MPEG-4 AVC ...`
    """
    lines = output.splitlines()
    decoders: list[DecoderInfo] = []
    header_passed = False

    pattern = re.compile(r"^\s*([VAS])([F.])([S.])([X.])([B.])([D.])\s+([a-zA-Z0-9_\-]+)\s+(.*)$")
    codec_pattern = re.compile(r"\(codec\s+([a-zA-Z0-9_\-]+)\)")

    for line in lines:
        if not header_passed:
            if line.strip().startswith("------"):
                header_passed = True
            continue

        match = pattern.match(line)
        if not match:
            continue

        media_flag, _, _, _, _, _, name, desc = match.groups()

        media_type: CodecType = "video"
        if media_flag == "A":
            media_type = "audio"
        elif media_flag == "S":
            media_type = "subtitle"

        codec_match = codec_pattern.search(desc)
        codec = codec_match.group(1) if codec_match else name

        is_hw, vendor = _detect_vendor_and_hw(name, desc)

        decoders.append(
            DecoderInfo(
                name=name,
                codec=codec,
                description=desc.strip(),
                media_type=media_type,
                is_hardware=is_hw,
                vendor=vendor,
            )
        )

    return decoders


def get_hwaccel_args(
    accel_type: str,
    device: str | None = None,
    output_format: str | None = None,
) -> list[str]:
    """Формирует список CLI аргументов для включения аппаратного ускорения в FFmpeg."""
    config = HWAccelConfig(name=accel_type, device=device, output_format=output_format)
    return config.to_ffmpeg_args()


# Таблица приоритета аппаратных и программных видеоэнкодеров для популярных форматов
_CODEC_PRIORITY_MAP: dict[str, tuple[tuple[str, ...], str]] = {
    # формат: (кортеж аппаратных энкодеров в порядке приоритета, программный fallback)
    "h264": (
        ("h264_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox", "h264_vaapi", "h264_mf"),
        "libx264",
    ),
    "avc": (
        ("h264_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox", "h264_vaapi", "h264_mf"),
        "libx264",
    ),
    "hevc": (
        ("hevc_nvenc", "hevc_qsv", "hevc_amf", "hevc_videotoolbox", "hevc_vaapi", "hevc_mf"),
        "libx265",
    ),
    "h265": (
        ("hevc_nvenc", "hevc_qsv", "hevc_amf", "hevc_videotoolbox", "hevc_vaapi", "hevc_mf"),
        "libx265",
    ),
    "av1": (
        ("av1_nvenc", "av1_qsv", "av1_amf", "av1_vaapi"),
        "libsvtav1",
    ),
    "vp9": (
        ("vp9_vaapi", "vp9_qsv"),
        "libvpx-vp9",
    ),
    "mjpeg": (
        ("mjpeg_qsv", "mjpeg_vaapi"),
        "mjpeg",
    ),
}


class HardwareAccel:
    """Менеджер аппаратного ускорения FFmpeg.

    Отвечает за опрос доступных ускорителей, энкодеров и декодеров,
    а также проверку фактической доступности GPU энкодеров в операционной системе.
    """

    def __init__(
        self,
        ffmpeg_path: PathLike | None = None,
        runner: ProcessRunner | None = None,
    ) -> None:
        """Инициализирует менеджер аппаратного ускорения FFmpeg.

        Args:
            ffmpeg_path: Пользовательский путь к бинарнику ffmpeg.
            runner: Экземпляр ProcessRunner для выполнения команд проверки.
        """
        self._ffmpeg_path = ffmpeg_path
        self._runner = runner or ProcessRunner()
        self._cached_accels: tuple[str, ...] | None = None
        self._cached_encoders: tuple[EncoderInfo, ...] | None = None
        self._cached_decoders: tuple[DecoderInfo, ...] | None = None
        self._verified_encoders: dict[str, bool] = {}

    def _resolve_ffmpeg(self) -> str:
        """Разрешает путь к бинарнику ffmpeg, используя заданный путь или автопоиск.

        Returns:
            Строковый абсолютный путь к бинарнику ffmpeg.
        """
        if self._ffmpeg_path:
            return str(self._ffmpeg_path)
        return str(find_ffmpeg())

    def clear_cache(self) -> None:
        """Очищает кэшированные результаты обнаружения."""
        self._cached_accels = None
        self._cached_encoders = None
        self._cached_decoders = None
        self._verified_encoders.clear()

    async def get_available_accels(self, *, force_refresh: bool = False) -> tuple[str, ...]:
        """Возвращает кортеж названий аппаратных ускорителей (-hwaccels)."""
        if self._cached_accels is not None and not force_refresh:
            return self._cached_accels

        ffmpeg_bin = self._resolve_ffmpeg()
        result = await self._runner.run([ffmpeg_bin, "-hwaccels"], check=False)
        output = result.stdout_text or result.stderr_text
        accels = tuple(parse_hwaccels_output(output))
        self._cached_accels = accels
        return accels

    async def get_available_encoders(
        self, *, force_refresh: bool = False
    ) -> tuple[EncoderInfo, ...]:
        """Возвращает кортеж информации о всех поддерживаемых энкодерах (-encoders)."""
        if self._cached_encoders is not None and not force_refresh:
            return self._cached_encoders

        ffmpeg_bin = self._resolve_ffmpeg()
        result = await self._runner.run([ffmpeg_bin, "-encoders"], check=False)
        output = result.stdout_text or result.stderr_text
        encoders = tuple(parse_encoders_output(output))
        self._cached_encoders = encoders
        return encoders

    async def get_available_decoders(
        self, *, force_refresh: bool = False
    ) -> tuple[DecoderInfo, ...]:
        """Возвращает кортеж информации о всех поддерживаемых декодерах (-decoders)."""
        if self._cached_decoders is not None and not force_refresh:
            return self._cached_decoders

        ffmpeg_bin = self._resolve_ffmpeg()
        result = await self._runner.run([ffmpeg_bin, "-decoders"], check=False)
        output = result.stdout_text or result.stderr_text
        decoders = tuple(parse_decoders_output(output))
        self._cached_decoders = decoders
        return decoders

    async def detect_hardware(self, *, force_refresh: bool = False) -> HardwareCapability:
        """Выполняет полное сканирование и возвращает снимок возможностей системы."""
        accels = await self.get_available_accels(force_refresh=force_refresh)
        encoders = await self.get_available_encoders(force_refresh=force_refresh)
        decoders = await self.get_available_decoders(force_refresh=force_refresh)
        return HardwareCapability(
            available_accels=accels,
            encoders=encoders,
            decoders=decoders,
        )

    async def test_encoder(self, encoder: str, *, timeout: float = 4.0) -> bool:
        """Проверяет фактическую работоспособность видеоэнкодера на текущем оборудовании.

        Выполняет пробное кодирование тестового кадра lavfi в null-устройство.
        Если видеокарта, драйвер или окружение не поддерживают энкодер, возвращает False.
        """
        if encoder in self._verified_encoders:
            return self._verified_encoders[encoder]

        ffmpeg_bin = self._resolve_ffmpeg()
        null_output = "NUL" if IS_WINDOWS else "/dev/null"

        test_cmd = [
            ffmpeg_bin,
            "-y",
            "-nostdin",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x64:d=0.04:r=25",
            "-c:v",
            encoder,
            "-f",
            "null",
            null_output,
        ]

        try:
            result = await self._runner.run(
                test_cmd,
                timeout=timeout,
                check=False,
            )
            is_working = result.success
        except Exception:
            is_working = False

        self._verified_encoders[encoder] = is_working
        return is_working

    async def best_encoder(
        self,
        codec: str = "h264",
        *,
        prefer_hw: bool = True,
        verify_working: bool = True,
    ) -> str:
        """Интеллектуально подбирает наиболее производительный кодировщик для заданного формата.

        Args:
            codec: Название кодека или формата ('h264', 'hevc', 'h265', 'av1', 'vp9', 'mjpeg').
            prefer_hw: Отдавать ли приоритет аппаратному кодированию (GPU).
            verify_working: Проверять ли энкодер тестовым кодированием кадра перед возвратом.

        Returns:
            Имя оптимального энкодера (например, 'h264_nvenc', 'h264_mf' или 'libx264').
        """
        clean_codec = codec.strip().lower()
        mapping = _CODEC_PRIORITY_MAP.get(clean_codec)

        if mapping is None:
            # Если формат неизвестен в таблице приоритетов, возвращаем исходное значение
            return codec

        hw_candidates, sw_fallback = mapping

        if not prefer_hw:
            return sw_fallback

        available_encoders = await self.get_available_encoders()
        available_names = {e.name for e in available_encoders}

        for candidate in hw_candidates:
            if candidate in available_names:
                if not verify_working:
                    return candidate
                # Проверяем реальную работоспособность с установленными драйверами
                if await self.test_encoder(candidate):
                    return candidate

        # Если ни один аппаратный кодек не подошел или не работает, возвращаем процессорный fallback
        return sw_fallback
