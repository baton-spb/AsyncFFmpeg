"""Иерархия исключений для библиотеки async-ffmpeg."""

from collections.abc import Sequence


class AsyncFFmpegError(Exception):
    """Базовое исключение для всех ошибок библиотеки async-ffmpeg."""

    def __init__(self, message: str) -> None:
        """Инициализирует базовое исключение с текстовым сообщением.

        Args:
            message: Подробное описание ошибки.
        """
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        """Возвращает строковое представление сообщения об ошибке."""
        return self.message


class FFmpegNotFoundError(AsyncFFmpegError):
    """Исключение, выбрасываемое когда исполняемый файл ffmpeg или ffprobe не найден."""

    def __init__(self, binary_name: str, searched_paths: Sequence[str] | None = None) -> None:
        """Инициализирует исключение отсутствия исполняемого файла в системе.

        Args:
            binary_name: Имя исполняемого файла (ffmpeg или ffprobe).
            searched_paths: Список директорий, в которых производился поиск.
        """
        self.binary_name = binary_name
        self.searched_paths = tuple(searched_paths) if searched_paths else ()
        msg = f"Исполняемый файл '{binary_name}' не найден в системе."
        if self.searched_paths:
            msg += f" Проверенные пути: {', '.join(self.searched_paths)}"
        super().__init__(msg)


class FFmpegProcessError(AsyncFFmpegError):
    """Исключение, выбрасываемое при завершении процесса FFmpeg с ненулевым кодом ошибки."""

    def __init__(
        self,
        exit_code: int,
        command: Sequence[str],
        stderr: str,
        stdout: str = "",
    ) -> None:
        """Инициализирует ошибку выполнения процесса FFmpeg.

        Args:
            exit_code: Ненулевой код возврата процесса (returncode).
            command: Список аргументов запущенной команды.
            stderr: Полный вывод стандартного потока ошибок stderr.
            stdout: Текстовый вывод потока stdout (если доступен).
        """
        self.exit_code = exit_code
        self.command = tuple(command)
        self.stderr = stderr
        self.stdout = stdout

        cmd_str = " ".join(self.command)
        # Извлекаем последние строки stderr для краткого и понятного сообщения
        stderr_lines = [line.strip() for line in stderr.strip().splitlines() if line.strip()]
        last_error = stderr_lines[-1] if stderr_lines else "Неизвестная ошибка FFmpeg"

        msg = (
            f"Процесс FFmpeg завершился с кодом ошибки {exit_code}.\n"
            f"Причина: {last_error}\n"
            f"Команда: {cmd_str}"
        )
        super().__init__(msg)


class FFmpegTimeoutError(AsyncFFmpegError):
    """Исключение, выбрасываемое при превышении таймаута выполнения процесса FFmpeg."""

    def __init__(self, timeout_seconds: float, command: Sequence[str]) -> None:
        """Инициализирует ошибку превышения времени выполнения команды.

        Args:
            timeout_seconds: Превышенный лимит времени в секундах.
            command: Список аргументов команды FFmpeg.
        """
        self.timeout_seconds = timeout_seconds
        self.command = tuple(command)
        cmd_str = " ".join(self.command)
        msg = (
            f"Выполнение команды FFmpeg превысило таймаут {timeout_seconds} сек.\n"
            f"Команда: {cmd_str}"
        )
        super().__init__(msg)


class FFmpegCancelledError(AsyncFFmpegError):
    """Исключение, выбрасываемое при отмене операции выполнения FFmpeg."""

    def __init__(self, command: Sequence[str]) -> None:
        """Инициализирует исключение отмены операции исполнения FFmpeg.

        Args:
            command: Список аргументов отмененной команды FFmpeg.
        """
        self.command = tuple(command)
        cmd_str = " ".join(self.command)
        super().__init__(f"Операция FFmpeg была отменена. Команда: {cmd_str}")


class FFprobeError(AsyncFFmpegError):
    """Исключение, выбрасываемое при ошибке выполнения или парсинга вывода FFprobe."""

    def __init__(
        self,
        message: str,
        command: Sequence[str] | None = None,
        stderr: str = "",
    ) -> None:
        """Инициализирует ошибку работы анализатора FFprobe.

        Args:
            message: Описание причины сбоя или некорректных данных.
            command: Список аргументов выполненной команды ffprobe.
            stderr: Вывод потока stderr при выполнении анализа.
        """
        self.command = tuple(command) if command else ()
        self.stderr = stderr
        msg = f"Ошибка FFprobe: {message}"
        if command:
            msg += f"\nКоманда: {' '.join(self.command)}"
        if stderr.strip():
            msg += f"\nДетали stderr: {stderr.strip()}"
        super().__init__(msg)


class InvalidInputError(AsyncFFmpegError):
    """Исключение, выбрасываемое при указании некорректного, несуществующего или нечитаемого входа."""

    def __init__(
        self, path: str, reason: str = "Файл не существует или недоступен для чтения"
    ) -> None:
        """Инициализирует ошибку невалидного входного медиаисточника.

        Args:
            path: Путь к некорректному или недоступному входному файлу.
            reason: Пояснение причины невалидности.
        """
        self.path = path
        self.reason = reason
        super().__init__(f"Некорректный входной файл '{path}': {reason}")


class CodecNotFoundError(AsyncFFmpegError):
    """Исключение, выбрасываемое когда запрошенный видео- или аудиокодек не поддерживается текущей сборкой FFmpeg."""

    def __init__(self, codec_name: str, mode: str = "encoder") -> None:
        """Инициализирует ошибку отсутствия требуемого кодека в установленной сборке FFmpeg.

        Args:
            codec_name: Название кодека (например, 'libx264', 'hevc_nvenc').
            mode: Режим использования кодека ('encoder' или 'decoder').
        """
        self.codec_name = codec_name
        self.mode = mode
        super().__init__(
            f"Кодек '{codec_name}' ({mode}) не найден или не поддерживается установленной сборкой FFmpeg."
        )


class FilterError(AsyncFFmpegError):
    """Исключение, выбрасываемое при ошибках построения или выполнения filtergraph."""

    def __init__(self, filter_name: str, reason: str) -> None:
        """Инициализирует ошибку конфигурации фильтра FFmpeg.

        Args:
            filter_name: Название проблемного фильтра (например, 'scale', 'overlay').
            reason: Описание обнаруженной ошибки в параметрах или цепочке фильтра.
        """
        self.filter_name = filter_name
        self.reason = reason
        super().__init__(f"Ошибка фильтра '{filter_name}': {reason}")


class CommandBuildError(AsyncFFmpegError):
    """Исключение, выбрасываемое при нарушении правил построения командной строки FFmpeg."""

    def __init__(self, reason: str) -> None:
        """Инициализирует ошибку формирования аргументов командной строки.

        Args:
            reason: Описание причины невозможности сборки команды.
        """
        self.reason = reason
        super().__init__(f"Невозможно собрать команду FFmpeg: {reason}")
