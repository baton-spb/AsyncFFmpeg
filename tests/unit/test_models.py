"""Unit-тесты для моделей данных медиафайлов (models.py)."""

from async_ffmpeg.models import (
    AudioStream,
    Chapter,
    MediaFormat,
    MediaInfo,
    StreamDisposition,
    SubtitleStream,
    VideoStream,
    _parse_fraction,
)


def test_parse_fraction() -> None:
    assert _parse_fraction("30/1") == 30.0
    assert _parse_fraction("24000/1001") == 24000.0 / 1001.0
    assert _parse_fraction("0/0") == 0.0
    assert _parse_fraction("25") == 25.0
    assert _parse_fraction(None) == 0.0
    assert _parse_fraction("invalid") == 0.0


def test_media_info_properties() -> None:
    fmt = MediaFormat(
        filename="test.mp4",
        nb_streams=2,
        format_name="mp4",
        format_long_name="MP4 (MPEG-4 Part 14)",
        duration=10.5,
        size=1048576,
        bit_rate=800000,
        tags={"title": "Test Title"},
    )
    video = VideoStream(
        index=0,
        codec_name="h264",
        codec_long_name="H.264",
        codec_type="video",
        width=1920,
        height=1080,
        pix_fmt="yuv420p",
        frame_rate=30.0,
        duration=10.5,
    )
    audio = AudioStream(
        index=1,
        codec_name="aac",
        codec_long_name="AAC",
        codec_type="audio",
        sample_rate=48000,
        channels=2,
        duration=10.5,
    )
    sub = SubtitleStream(
        index=2,
        codec_name="subrip",
        codec_long_name="SubRip",
        codec_type="subtitle",
        language="eng",
    )
    chapter = Chapter(
        id=0,
        time_base="1/1000",
        start=0,
        start_time=0.0,
        end=5000,
        end_time=5.0,
        tags={"title": "Intro"},
    )

    info = MediaInfo(
        format=fmt,
        streams=(video, audio, sub),
        video_streams=(video,),
        audio_streams=(audio,),
        subtitle_streams=(sub,),
        chapters=(chapter,),
    )

    assert info.has_video is True
    assert info.has_audio is True
    assert info.has_subtitles is True
    assert info.primary_video == video
    assert info.primary_audio == audio
    assert info.duration == 10.5
    assert info.size == 1048576
    assert info.bit_rate == 800000
    assert info.resolution == (1920, 1080)
    assert info.fps == 30.0
    assert chapter.title == "Intro"
    assert chapter.duration == 5.0


def test_media_info_empty() -> None:
    fmt = MediaFormat(
        filename="empty.dat",
        nb_streams=0,
        format_name="raw",
        format_long_name="Raw Data",
    )
    info = MediaInfo(
        format=fmt,
        streams=(),
        video_streams=(),
        audio_streams=(),
        subtitle_streams=(),
    )
    assert info.has_video is False
    assert info.has_audio is False
    assert info.has_subtitles is False
    assert info.primary_video is None
    assert info.primary_audio is None
    assert info.duration is None
    assert info.resolution is None
    assert info.fps is None


def test_stream_disposition() -> None:
    disp = StreamDisposition(default=True, attached_pic=False)
    assert disp.default is True
    assert disp.attached_pic is False
    assert disp.comment is False
