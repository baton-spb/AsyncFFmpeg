"""Обнаружение исполняемых файлов FFmpeg и FFprobe в системе и извлечение информации о версиях."""

import asyncio
import functools
import os
import re
import shutil
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from async_ffmpeg._compat import IS_WINDOWS, get_subprocess_creation_kwargs
from async_ffmpeg._constants import (
    DEFAULT_FFMPEG_EXECUTABLE,
    DEFAULT_FFPROBE_EXECUTABLE,
    ENV_FFMPEG_PATH,
    ENV_FFPROBE_PATH,
)
from async_ffmpeg._types import PathLike
from async_ffmpeg.exceptions import FFmpegNotFoundError

_VERSION_REGEX = re.compile(
    r"(?:ffmpeg|ffprobe)\s+version\s+([a-zA-Z0-9.\-_:]+)",
    re.IGNORECASE,
)
_SEMVER_REGEX = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?")


@dataclass(frozen=True, slots=True)
class BinaryInfo:
    """Информация о найденном исполняемом файле FFmpeg/FFprobe."""

    name: str
    path: Path
    version_str: str
    major: int | None = None
    minor: int | None = None
    patch: int | None = None

    @property
    def is_available(self) -> bool:
        """Доступен ли исполняемый файл для запуска."""
        return self.path.is_file()


def _get_platform_candidate_dirs() -> tuple[Path, ...]:
    """Возвращает список типовых директорий поиска бинарников для текущей платформы."""
    dirs: list[Path] = []

    if IS_WINDOWS:
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        user_profile = os.environ.get("USERPROFILE", "")
        prog_data = os.environ.get("PROGRAMDATA", "")
        prog_files = os.environ.get("PROGRAMFILES", "C:\\Program Files")

        if local_app_data:
            dirs.append(Path(local_app_data) / "Microsoft" / "WinGet" / "Links")
        if user_profile:
            dirs.append(Path(user_profile) / "scoop" / "shims")
        if prog_data:
            dirs.append(Path(prog_data) / "chocolatey" / "bin")
        if prog_files:
            dirs.append(Path(prog_files) / "ffmpeg" / "bin")
            dirs.append(Path(prog_files) / "nodejs")
        dirs.append(Path("C:\\ffmpeg\\bin"))
    else:
        dirs.extend(
            [
                Path("/opt/homebrew/bin"),
                Path("/usr/local/bin"),
                Path("/usr/bin"),
                Path("/snap/bin"),
                Path("/opt/local/bin"),
            ]
        )

    return tuple(d for d in dirs if d.is_dir())


def _parse_version_components(version_text: str) -> tuple[str, int | None, int | None, int | None]:
    """Парсит первую строку вывода `-version` и извлекает semver компоненты."""
    raw_str = version_text.strip()
    match = _VERSION_REGEX.search(raw_str)
    ver_str = (
        match.group(1) if match else raw_str.split()[2] if len(raw_str.split()) > 2 else raw_str
    )

    major, minor, patch = None, None, None
    semver_match = _SEMVER_REGEX.match(ver_str)
    if semver_match:
        with suppress(ValueError, TypeError):
            if semver_match.group(1):
                major = int(semver_match.group(1))
            if semver_match.group(2):
                minor = int(semver_match.group(2))
            if semver_match.group(3):
                patch = int(semver_match.group(3))

    return ver_str, major, minor, patch


@functools.lru_cache(maxsize=32)
def _find_binary_cached(binary_name: str, custom_path_str: str | None = None) -> Path:
    """Внутренний кэшированный поиск бинарника."""
    searched: list[str] = []
    binary_variants = (f"{binary_name}.exe", binary_name) if IS_WINDOWS else (binary_name,)

    # 1. Проверка явно указанного пути
    if custom_path_str is not None:
        p = Path(custom_path_str).expanduser()
        searched.append(str(p))
        if p.is_file():
            return p.resolve()
        if p.is_dir():
            for variant in binary_variants:
                candidate = p / variant
                searched.append(str(candidate))
                if candidate.is_file():
                    return candidate.resolve()

    # 2. Проверка переменной окружения
    env_var_name = ENV_FFMPEG_PATH if "ffmpeg" in binary_name.lower() else ENV_FFPROBE_PATH
    env_val = os.environ.get(env_var_name)
    if env_val:
        p_env = Path(env_val).expanduser()
        searched.append(f"{env_var_name}={env_val}")
        if p_env.is_file():
            return p_env.resolve()
        if p_env.is_dir():
            for variant in binary_variants:
                candidate = p_env / variant
                searched.append(str(candidate))
                if candidate.is_file():
                    return candidate.resolve()

    # 3. Системный PATH
    found = shutil.which(binary_name)
    if found:
        return Path(found).resolve()
    searched.append(f"PATH (via which '{binary_name}')")

    # 4. Типовые директории установки платформы
    for candidate_dir in _get_platform_candidate_dirs():
        for variant in binary_variants:
            candidate = candidate_dir / variant
            searched.append(str(candidate))
            if candidate.is_file():
                return candidate.resolve()

    raise FFmpegNotFoundError(binary_name=binary_name, searched_paths=searched)


def find_binary(binary_name: str, custom_path: PathLike | None = None) -> Path:
    """Выполняет поиск исполняемого файла утилиты.

    Порядок поиска:
    1. Явно переданный `custom_path` (файл или директория).
    2. Переменная окружения (`FFMPEG_PATH` для ffmpeg, `FFPROBE_PATH` для ffprobe).
    3. Системный `PATH` через `shutil.which`.
    4. Стандартные пути установки менеджеров пакетов (WinGet, Scoop, Choco, Homebrew).

    Raises:
        FFmpegNotFoundError: если бинарник не найден ни в одном из мест.
    """
    path_str = str(Path(custom_path).expanduser()) if custom_path is not None else None
    return _find_binary_cached(binary_name, path_str)


def find_ffmpeg(custom_path: PathLike | None = None) -> Path:
    """Находит исполняемый файл `ffmpeg`."""
    return find_binary(DEFAULT_FFMPEG_EXECUTABLE, custom_path=custom_path)


def find_ffprobe(custom_path: PathLike | None = None) -> Path:
    """Находит исполняемый файл `ffprobe`."""
    return find_binary(DEFAULT_FFPROBE_EXECUTABLE, custom_path=custom_path)


def get_binary_version_sync(binary_path: PathLike) -> str:
    """Синхронно получает строку версии бинарника через вызов `-version`."""
    path = Path(binary_path)
    try:
        proc = subprocess.run(
            [str(path), "-version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0,
        )
        if proc.returncode == 0 and proc.stdout:
            lines = proc.stdout.splitlines()
            if lines:
                return lines[0].strip()
    except (subprocess.SubprocessError, OSError) as exc:
        raise FFmpegNotFoundError(
            binary_name=path.name,
            searched_paths=[f"Ошибка запуска: {exc}"],
        ) from exc
    return "unknown"


async def get_binary_version(binary_path: PathLike) -> str:
    """Асинхронно получает строку версии бинарника через вызов `-version`."""
    path = Path(binary_path)
    creation_kwargs = get_subprocess_creation_kwargs()

    try:
        proc = await asyncio.create_subprocess_exec(
            str(path),
            "-version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **creation_kwargs,
        )
        stdout_data, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode == 0 and stdout_data:
            lines = stdout_data.decode(errors="replace").splitlines()
            if lines:
                return lines[0].strip()
    except (TimeoutError, OSError) as exc:
        raise FFmpegNotFoundError(
            binary_name=path.name,
            searched_paths=[f"Ошибка выполнения: {exc}"],
        ) from exc
    return "unknown"


async def get_ffmpeg_info(custom_path: PathLike | None = None) -> BinaryInfo:
    """Получает полную структуру информации о доступном FFmpeg."""
    path = find_ffmpeg(custom_path=custom_path)
    raw_version = await get_binary_version(path)
    ver_str, major, minor, patch = _parse_version_components(raw_version)
    return BinaryInfo(
        name="ffmpeg",
        path=path,
        version_str=ver_str,
        major=major,
        minor=minor,
        patch=patch,
    )


async def get_ffprobe_info(custom_path: PathLike | None = None) -> BinaryInfo:
    """Получает полную структуру информации о доступном FFprobe."""
    path = find_ffprobe(custom_path=custom_path)
    raw_version = await get_binary_version(path)
    ver_str, major, minor, patch = _parse_version_components(raw_version)
    return BinaryInfo(
        name="ffprobe",
        path=path,
        version_str=ver_str,
        major=major,
        minor=minor,
        patch=patch,
    )


def clear_discovery_cache() -> None:
    """Сбрасывает кэш поиска исполняемых файлов."""
    _find_binary_cached.cache_clear()
