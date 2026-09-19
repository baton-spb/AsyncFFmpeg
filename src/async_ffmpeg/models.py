"""Строго типизированные модели данных медиафайлов (ffprobe JSON).

Все модели являются неизменяемыми dataclass-классами (`frozen=True`, `slots=True`)
с автоматической конвертацией строковых числовых полей FFprobe в int/float.
"""

from dataclasses import dataclass, field


def _parse_fraction(value: str | None) -> float:
    """Вычисляет числовое значение частоты кадров из дроби вида '30/1' или '24000/1001'.

    Args:
        value: Строковое представление дроби (например, '25/1', '30000/1001') или десятичное число.

    Returns:
        Вычисленное вещественное число с плавающей точкой или 0.0 при некорректном формате.
    """
    if not value or value == "0/0":
        return 0.0
    if "/" in value:
        num_str, _, den_str = value.partition("/")
        try:
            num = float(num_str)
            den = float(den_str)
            return num / den if den != 0 else 0.0
        except ValueError:
            return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


@dataclass(frozen=True, slots=True)
class StreamDisposition:
    """Флаги расположения и назначения потока (disposition)."""

    default: bool = False
    dub: bool = False
    original: bool = False
    comment: bool = False
    lyrics: bool = False
    karaoke: bool = False
    forced: bool = False
    hearing_impaired: bool = False
    visual_impaired: bool = False
    clean_effects: bool = False
    attached_pic: bool = False
    timed_thumbnails: bool = False
    captions: bool = False
    descriptions: bool = False
    metadata: bool = False
    dependent: bool = False
    still_image: bool = False


@dataclass(frozen=True, slots=True)
class BaseStream:
    """Базовые свойства любого медиапотока."""

    index: int
    codec_name: str
    codec_long_name: str
    codec_type: str
    profile: str | None = None
    codec_tag_string: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
    disposition: StreamDisposition = field(default_factory=StreamDisposition)


@dataclass(frozen=True, slots=True)
class VideoStream(BaseStream):
    """Информация о видеопотоке."""

    width: int = 0
    height: int = 0
    pix_fmt: str = ""
    frame_rate: float = 0.0
    r_frame_rate: str = "0/0"
    avg_frame_rate: str = "0/0"
    duration: float | None = None
    bit_rate: int | None = None
    nb_frames: int | None = None
    coded_width: int | None = None
    coded_height: int | None = None
    sample_aspect_ratio: str | None = None
    display_aspect_ratio: str | None = None
    color_space: str | None = None
    color_range: str | None = None
    color_primaries: str | None = None
    color_transfer: str | None = None
    field_order: str | None = None
    is_avc: bool = False

    @property
    def resolution(self) -> tuple[int, int]:
        """Разрешение видео в виде кортежа (ширина, высота)."""
        return (self.width, self.height)

    @property
    def fps(self) -> float:
        """Частота кадров видеопотока (алиас для frame_rate)."""
        return self.frame_rate



@dataclass(frozen=True, slots=True)
class AudioStream(BaseStream):
    """Информация об аудиопотоке."""

    sample_rate: int = 0
    channels: int = 0
    channel_layout: str | None = None
    sample_fmt: str | None = None
    duration: float | None = None
    bit_rate: int | None = None
    nb_frames: int | None = None
    bits_per_sample: int | None = None


@dataclass(frozen=True, slots=True)
class SubtitleStream(BaseStream):
    """Информация о потоке субтитров."""

    language: str | None = None
    duration: float | None = None
    nb_frames: int | None = None


@dataclass(frozen=True, slots=True)
class Chapter:
    """Информация о главе медиафайла."""

    id: int
    time_base: str
    start: int
    start_time: float
    end: int
    end_time: float
    tags: dict[str, str] = field(default_factory=dict)

    @property
    def title(self) -> str | None:
        """Название главы из тегов."""
        return self.tags.get("title")

    @property
    def duration(self) -> float:
        """Длительность главы в секундах."""
        return max(0.0, self.end_time - self.start_time)


@dataclass(frozen=True, slots=True)
class MediaFormat:
    """Информация о контейнере и формате медиафайла."""

    filename: str
    nb_streams: int
    format_name: str
    format_long_name: str
    start_time: float | None = None
    duration: float | None = None
    size: int | None = None
    bit_rate: int | None = None
    probe_score: int | None = None
    tags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MediaInfo:
    """Полная структура метаданных медиафайла (ffprobe)."""

    format: MediaFormat
    streams: tuple[VideoStream | AudioStream | SubtitleStream, ...]
    video_streams: tuple[VideoStream, ...]
    audio_streams: tuple[AudioStream, ...]
    subtitle_streams: tuple[SubtitleStream, ...]
    chapters: tuple[Chapter, ...] = ()
    raw_data: dict[str, object] = field(default_factory=dict)

    @property
    def has_video(self) -> bool:
        """Присутствует ли хотя бы один видеопоток."""
        return len(self.video_streams) > 0

    @property
    def has_audio(self) -> bool:
        """Присутствует ли хотя бы один аудиопоток."""
        return len(self.audio_streams) > 0

    @property
    def has_subtitles(self) -> bool:
        """Присутствуют ли субтитры."""
        return len(self.subtitle_streams) > 0

    @property
    def primary_video(self) -> VideoStream | None:
        """Основной видеопоток (первый найденный)."""
        return self.video_streams[0] if self.video_streams else None

    @property
    def primary_audio(self) -> AudioStream | None:
        """Основной аудиопоток (первый найденный)."""
        return self.audio_streams[0] if self.audio_streams else None

    @property
    def duration(self) -> float | None:
        """Общая длительность медиа в секундах (из контейнера или первичного потока)."""
        if self.format.duration is not None:
            return self.format.duration
        if self.primary_video and self.primary_video.duration is not None:
            return self.primary_video.duration
        if self.primary_audio and self.primary_audio.duration is not None:
            return self.primary_audio.duration
        return None

    @property
    def size(self) -> int | None:
        """Размер файла в байтах."""
        return self.format.size

    @property
    def bit_rate(self) -> int | None:
        """Общий битрейт в бит/с."""
        return self.format.bit_rate

    @property
    def resolution(self) -> tuple[int, int] | None:
        """Разрешение основного видеопотока (ширина, высота) или None."""
        return self.primary_video.resolution if self.primary_video else None

    @property
    def fps(self) -> float | None:
        """Частота кадров основного видеопотока или None."""
        return self.primary_video.frame_rate if self.primary_video else None

    @property
    def format_name(self) -> str:
        """Название формата/контейнера медиафайла."""
        return self.format.format_name


@dataclass(frozen=True, slots=True)
class SilenceInterval:
    """Интервал тишины, обнаруженный фильтром silencedetect.

    Attributes:
        start: Время начала тишины в секундах.
        end: Время окончания тишины в секундах.
        duration: Длительность интервала тишины в секундах.
    """

    start: float
    end: float
    duration: float

