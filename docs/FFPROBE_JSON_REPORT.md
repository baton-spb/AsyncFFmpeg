# FFprobe JSON Output Technical Research Report

## 1. Step 1: Create Test Sample Video
**Command:**
```powershell
ffmpeg -y -f lavfi -i color=c=blue:s=640x480:d=2:r=30 -f lavfi -i sine=frequency=440:duration=2 -c:v libx264 -preset ultrafast -c:a aac -metadata title="Test Video" -metadata artist="Test" -metadata comment="Test Comment" c:\Projects\AsyncFFmpeg\test_sample.mp4
```

**Raw Output:**
```
Input #0, lavfi, from 'color=c=blue:s=640x480:d=2:r=30':
  Duration: N/A, start: 0.000000, bitrate: N/A
  Stream #0:0: Video: wrapped_avframe, yuv420p, 640x480 [SAR 1:1 DAR 4:3], 30 fps, 30 tbr, 30 tbn
Input #1, lavfi, from 'sine=frequency=440:duration=2':
  Duration: N/A, start: 0.000000, bitrate: 705 kb/s
  Stream #1:0: Audio: pcm_s16le, 44100 Hz, mono, s16, 705 kb/s
Stream mapping:
  Stream #0:0 -> #0:0 (wrapped_avframe (native) -> h264 (libx264))
  Stream #1:0 -> #0:1 (pcm_s16le (native) -> aac (native))
Output #0, mp4, to 'c:\Projects\AsyncFFmpeg\test_sample.mp4':
  Metadata:
    title           : Test Video
    artist          : Test
    comment         : Test Comment
    encoder         : Lavf61.9.107
  Stream #0:0: Video: h264 (avc1 / 0x31637661), yuv420p(tv, progressive), 640x480 [SAR 1:1 DAR 4:3], q=2-31, 30 fps, 15360 tbn
  Stream #0:1: Audio: aac (LC) (mp4a / 0x6134706D), 44100 Hz, mono, fltp, 69 kb/s
frame=   60 fps=0.0 q=-1.0 Lsize=      22KiB time=00:00:02.00 bitrate=  92.1kbits/s speed=34.5x
```

---

## 2. Step 2: Full JSON Output (`-show_format -show_streams`)
**Command:**
```powershell
ffprobe -v quiet -print_format json -show_format -show_streams c:\Projects\AsyncFFmpeg\test_sample.mp4
```

**Raw Output:**
```json
{
    "streams": [
        {
            "index": 0,
            "codec_name": "h264",
            "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
            "profile": "Constrained Baseline",
            "codec_type": "video",
            "codec_tag_string": "avc1",
            "codec_tag": "0x31637661",
            "width": 640,
            "height": 480,
            "coded_width": 640,
            "coded_height": 480,
            "has_b_frames": 0,
            "sample_aspect_ratio": "1:1",
            "display_aspect_ratio": "4:3",
            "pix_fmt": "yuv420p",
            "level": 30,
            "chroma_location": "left",
            "field_order": "progressive",
            "refs": 1,
            "is_avc": "true",
            "nal_length_size": "4",
            "id": "0x1",
            "r_frame_rate": "30/1",
            "avg_frame_rate": "30/1",
            "time_base": "1/15360",
            "start_pts": 0,
            "start_time": "0.000000",
            "duration_ts": 30720,
            "duration": "2.000000",
            "bit_rate": "8724",
            "bits_per_raw_sample": "8",
            "nb_frames": "60",
            "extradata_size": 39,
            "disposition": {
                "default": 1,
                "dub": 0,
                "original": 0,
                "comment": 0,
                "lyrics": 0,
                "karaoke": 0,
                "forced": 0,
                "hearing_impaired": 0,
                "visual_impaired": 0,
                "clean_effects": 0,
                "attached_pic": 0,
                "timed_thumbnails": 0,
                "non_diegetic": 0,
                "captions": 0,
                "descriptions": 0,
                "metadata": 0,
                "dependent": 0,
                "still_image": 0,
                "multilayer": 0
            },
            "tags": {
                "language": "und",
                "handler_name": "VideoHandler",
                "vendor_id": "[0][0][0][0]",
                "encoder": "Lavc61.33.102 libx264"
            }
        },
        {
            "index": 1,
            "codec_name": "aac",
            "codec_long_name": "AAC (Advanced Audio Coding)",
            "profile": "LC",
            "codec_type": "audio",
            "codec_tag_string": "mp4a",
            "codec_tag": "0x6134706d",
            "sample_fmt": "fltp",
            "sample_rate": "44100",
            "channels": 1,
            "channel_layout": "mono",
            "bits_per_sample": 0,
            "initial_padding": 0,
            "id": "0x2",
            "r_frame_rate": "0/0",
            "avg_frame_rate": "0/0",
            "time_base": "1/44100",
            "start_pts": 0,
            "start_time": "0.000000",
            "duration_ts": 88200,
            "duration": "2.000000",
            "bit_rate": "69698",
            "nb_frames": "88",
            "extradata_size": 5,
            "disposition": {
                "default": 1,
                "dub": 0,
                "original": 0,
                "comment": 0,
                "lyrics": 0,
                "karaoke": 0,
                "forced": 0,
                "hearing_impaired": 0,
                "visual_impaired": 0,
                "clean_effects": 0,
                "attached_pic": 0,
                "timed_thumbnails": 0,
                "non_diegetic": 0,
                "captions": 0,
                "descriptions": 0,
                "metadata": 0,
                "dependent": 0,
                "still_image": 0,
                "multilayer": 0
            },
            "tags": {
                "language": "und",
                "handler_name": "SoundHandler",
                "vendor_id": "[0][0][0][0]"
            }
        }
    ],
    "format": {
        "filename": "c:\\Projects\\AsyncFFmpeg\\test_sample.mp4",
        "nb_streams": 2,
        "nb_programs": 0,
        "nb_stream_groups": 0,
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "format_long_name": "QuickTime / MOV",
        "start_time": "0.000000",
        "duration": "2.000000",
        "size": "23030",
        "bit_rate": "92120",
        "probe_score": 100,
        "tags": {
            "major_brand": "isom",
            "minor_version": "512",
            "compatible_brands": "isomiso2avc1mp41",
            "title": "Test Video",
            "artist": "Test",
            "encoder": "Lavf61.9.107",
            "comment": "Test Comment"
        }
    }
}
```

---

## 3. Step 3: Full JSON Output with Chapters (`-show_format -show_streams -show_chapters`)
**Command:**
```powershell
ffprobe -v quiet -print_format json -show_format -show_streams -show_chapters c:\Projects\AsyncFFmpeg\test_sample.mp4
```

**Raw Output:**
```json
{
    "streams": [
        {
            "index": 0,
            "codec_name": "h264",
            "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
            "profile": "Constrained Baseline",
            "codec_type": "video",
            "codec_tag_string": "avc1",
            "codec_tag": "0x31637661",
            "width": 640,
            "height": 480,
            "coded_width": 640,
            "coded_height": 480,
            "has_b_frames": 0,
            "sample_aspect_ratio": "1:1",
            "display_aspect_ratio": "4:3",
            "pix_fmt": "yuv420p",
            "level": 30,
            "chroma_location": "left",
            "field_order": "progressive",
            "refs": 1,
            "is_avc": "true",
            "nal_length_size": "4",
            "id": "0x1",
            "r_frame_rate": "30/1",
            "avg_frame_rate": "30/1",
            "time_base": "1/15360",
            "start_pts": 0,
            "start_time": "0.000000",
            "duration_ts": 30720,
            "duration": "2.000000",
            "bit_rate": "8724",
            "bits_per_raw_sample": "8",
            "nb_frames": "60",
            "extradata_size": 39,
            "disposition": {
                "default": 1,
                "dub": 0,
                "original": 0,
                "comment": 0,
                "lyrics": 0,
                "karaoke": 0,
                "forced": 0,
                "hearing_impaired": 0,
                "visual_impaired": 0,
                "clean_effects": 0,
                "attached_pic": 0,
                "timed_thumbnails": 0,
                "non_diegetic": 0,
                "captions": 0,
                "descriptions": 0,
                "metadata": 0,
                "dependent": 0,
                "still_image": 0,
                "multilayer": 0
            },
            "tags": {
                "language": "und",
                "handler_name": "VideoHandler",
                "vendor_id": "[0][0][0][0]",
                "encoder": "Lavc61.33.102 libx264"
            }
        },
        {
            "index": 1,
            "codec_name": "aac",
            "codec_long_name": "AAC (Advanced Audio Coding)",
            "profile": "LC",
            "codec_type": "audio",
            "codec_tag_string": "mp4a",
            "codec_tag": "0x6134706d",
            "sample_fmt": "fltp",
            "sample_rate": "44100",
            "channels": 1,
            "channel_layout": "mono",
            "bits_per_sample": 0,
            "initial_padding": 0,
            "id": "0x2",
            "r_frame_rate": "0/0",
            "avg_frame_rate": "0/0",
            "time_base": "1/44100",
            "start_pts": 0,
            "start_time": "0.000000",
            "duration_ts": 88200,
            "duration": "2.000000",
            "bit_rate": "69698",
            "nb_frames": "88",
            "extradata_size": 5,
            "disposition": {
                "default": 1,
                "dub": 0,
                "original": 0,
                "comment": 0,
                "lyrics": 0,
                "karaoke": 0,
                "forced": 0,
                "hearing_impaired": 0,
                "visual_impaired": 0,
                "clean_effects": 0,
                "attached_pic": 0,
                "timed_thumbnails": 0,
                "non_diegetic": 0,
                "captions": 0,
                "descriptions": 0,
                "metadata": 0,
                "dependent": 0,
                "still_image": 0,
                "multilayer": 0
            },
            "tags": {
                "language": "und",
                "handler_name": "SoundHandler",
                "vendor_id": "[0][0][0][0]"
            }
        }
    ],
    "chapters": [

    ],
    "format": {
        "filename": "c:\\Projects\\AsyncFFmpeg\\test_sample.mp4",
        "nb_streams": 2,
        "nb_programs": 0,
        "nb_stream_groups": 0,
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "format_long_name": "QuickTime / MOV",
        "start_time": "0.000000",
        "duration": "2.000000",
        "size": "23030",
        "bit_rate": "92120",
        "probe_score": 100,
        "tags": {
            "major_brand": "isom",
            "minor_version": "512",
            "compatible_brands": "isomiso2avc1mp41",
            "title": "Test Video",
            "artist": "Test",
            "encoder": "Lavf61.9.107",
            "comment": "Test Comment"
        }
    }
}
```

---

## 4. Step 4: Video Streams Only (`-select_streams v`)
**Command:**
```powershell
ffprobe -v quiet -print_format json -show_format -show_streams -select_streams v c:\Projects\AsyncFFmpeg\test_sample.mp4
```

**Raw Output:**
```json
{
    "streams": [
        {
            "index": 0,
            "codec_name": "h264",
            "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
            "profile": "Constrained Baseline",
            "codec_type": "video",
            "codec_tag_string": "avc1",
            "codec_tag": "0x31637661",
            "width": 640,
            "height": 480,
            "coded_width": 640,
            "coded_height": 480,
            "has_b_frames": 0,
            "sample_aspect_ratio": "1:1",
            "display_aspect_ratio": "4:3",
            "pix_fmt": "yuv420p",
            "level": 30,
            "chroma_location": "left",
            "field_order": "progressive",
            "refs": 1,
            "is_avc": "true",
            "nal_length_size": "4",
            "id": "0x1",
            "r_frame_rate": "30/1",
            "avg_frame_rate": "30/1",
            "time_base": "1/15360",
            "start_pts": 0,
            "start_time": "0.000000",
            "duration_ts": 30720,
            "duration": "2.000000",
            "bit_rate": "8724",
            "bits_per_raw_sample": "8",
            "nb_frames": "60",
            "extradata_size": 39,
            "disposition": {
                "default": 1,
                "dub": 0,
                "original": 0,
                "comment": 0,
                "lyrics": 0,
                "karaoke": 0,
                "forced": 0,
                "hearing_impaired": 0,
                "visual_impaired": 0,
                "clean_effects": 0,
                "attached_pic": 0,
                "timed_thumbnails": 0,
                "non_diegetic": 0,
                "captions": 0,
                "descriptions": 0,
                "metadata": 0,
                "dependent": 0,
                "still_image": 0,
                "multilayer": 0
            },
            "tags": {
                "language": "und",
                "handler_name": "VideoHandler",
                "vendor_id": "[0][0][0][0]",
                "encoder": "Lavc61.33.102 libx264"
            }
        }
    ],
    "format": {
        "filename": "c:\\Projects\\AsyncFFmpeg\\test_sample.mp4",
        "nb_streams": 2,
        "nb_programs": 0,
        "nb_stream_groups": 0,
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "format_long_name": "QuickTime / MOV",
        "start_time": "0.000000",
        "duration": "2.000000",
        "size": "23030",
        "bit_rate": "92120",
        "probe_score": 100,
        "tags": {
            "major_brand": "isom",
            "minor_version": "512",
            "compatible_brands": "isomiso2avc1mp41",
            "title": "Test Video",
            "artist": "Test",
            "encoder": "Lavf61.9.107",
            "comment": "Test Comment"
        }
    }
}
```

---

## 5. Step 5: Audio Streams Only (`-select_streams a`)
**Command:**
```powershell
ffprobe -v quiet -print_format json -show_format -show_streams -select_streams a c:\Projects\AsyncFFmpeg\test_sample.mp4
```

**Raw Output:**
```json
{
    "streams": [
        {
            "index": 1,
            "codec_name": "aac",
            "codec_long_name": "AAC (Advanced Audio Coding)",
            "profile": "LC",
            "codec_type": "audio",
            "codec_tag_string": "mp4a",
            "codec_tag": "0x6134706d",
            "sample_fmt": "fltp",
            "sample_rate": "44100",
            "channels": 1,
            "channel_layout": "mono",
            "bits_per_sample": 0,
            "initial_padding": 0,
            "id": "0x2",
            "r_frame_rate": "0/0",
            "avg_frame_rate": "0/0",
            "time_base": "1/44100",
            "start_pts": 0,
            "start_time": "0.000000",
            "duration_ts": 88200,
            "duration": "2.000000",
            "bit_rate": "69698",
            "nb_frames": "88",
            "extradata_size": 5,
            "disposition": {
                "default": 1,
                "dub": 0,
                "original": 0,
                "comment": 0,
                "lyrics": 0,
                "karaoke": 0,
                "forced": 0,
                "hearing_impaired": 0,
                "visual_impaired": 0,
                "clean_effects": 0,
                "attached_pic": 0,
                "timed_thumbnails": 0,
                "non_diegetic": 0,
                "captions": 0,
                "descriptions": 0,
                "metadata": 0,
                "dependent": 0,
                "still_image": 0,
                "multilayer": 0
            },
            "tags": {
                "language": "und",
                "handler_name": "SoundHandler",
                "vendor_id": "[0][0][0][0]"
            }
        }
    ],
    "format": {
        "filename": "c:\\Projects\\AsyncFFmpeg\\test_sample.mp4",
        "nb_streams": 2,
        "nb_programs": 0,
        "nb_stream_groups": 0,
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "format_long_name": "QuickTime / MOV",
        "start_time": "0.000000",
        "duration": "2.000000",
        "size": "23030",
        "bit_rate": "92120",
        "probe_score": 100,
        "tags": {
            "major_brand": "isom",
            "minor_version": "512",
            "compatible_brands": "isomiso2avc1mp41",
            "title": "Test Video",
            "artist": "Test",
            "encoder": "Lavf61.9.107",
            "comment": "Test Comment"
        }
    }
}
```

---

## 6. Step 6: Create Multi-stream MKV Test File
**Command:**
```powershell
ffmpeg -y -f lavfi -i color=c=green:s=320x240:d=2 -f lavfi -i sine=frequency=880:duration=2 -c:v libx264 -preset ultrafast -c:a aac c:\Projects\AsyncFFmpeg\test_multi.mkv
```

**Raw Output:**
```
Input #0, lavfi, from 'color=c=green:s=320x240:d=2':
  Duration: N/A, start: 0.000000, bitrate: N/A
  Stream #0:0: Video: wrapped_avframe, yuv420p, 320x240 [SAR 1:1 DAR 4:3], 25 fps, 25 tbr, 25 tbn
Input #1, lavfi, from 'sine=frequency=880:duration=2':
  Duration: N/A, start: 0.000000, bitrate: 705 kb/s
  Stream #1:0: Audio: pcm_s16le, 44100 Hz, mono, s16, 705 kb/s
Output #0, matroska, to 'c:\Projects\AsyncFFmpeg\test_multi.mkv':
  Stream #0:0: Video: h264 (H264 / 0x34363248), yuv420p(tv, progressive), 320x240 [SAR 1:1 DAR 4:3], q=2-31, 25 fps, 1k tbn
  Stream #0:1: Audio: aac (LC) ([255][0][0][0] / 0x00FF), 44100 Hz, mono, fltp, 69 kb/s
frame=   50 fps=0.0 q=-1.0 Lsize=      20KiB time=00:00:02.00 bitrate=  81.7kbits/s speed=33.8x
```

---

## 7. Step 7: Probe `test_multi.mkv`
**Command:**
```powershell
ffprobe -v quiet -print_format json -show_format -show_streams c:\Projects\AsyncFFmpeg\test_multi.mkv
```

**Raw Output:**
```json
{
    "streams": [
        {
            "index": 0,
            "codec_name": "h264",
            "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
            "profile": "Constrained Baseline",
            "codec_type": "video",
            "codec_tag_string": "[0][0][0][0]",
            "codec_tag": "0x0000",
            "width": 320,
            "height": 240,
            "coded_width": 320,
            "coded_height": 240,
            "has_b_frames": 0,
            "sample_aspect_ratio": "1:1",
            "display_aspect_ratio": "4:3",
            "pix_fmt": "yuv420p",
            "level": 13,
            "color_range": "tv",
            "chroma_location": "left",
            "field_order": "progressive",
            "refs": 1,
            "is_avc": "true",
            "nal_length_size": "4",
            "r_frame_rate": "25/1",
            "avg_frame_rate": "25/1",
            "time_base": "1/1000",
            "start_pts": 0,
            "start_time": "0.000000",
            "bits_per_raw_sample": "8",
            "extradata_size": 37,
            "disposition": {
                "default": 0,
                "dub": 0,
                "original": 0,
                "comment": 0,
                "lyrics": 0,
                "karaoke": 0,
                "forced": 0,
                "hearing_impaired": 0,
                "visual_impaired": 0,
                "clean_effects": 0,
                "attached_pic": 0,
                "timed_thumbnails": 0,
                "non_diegetic": 0,
                "captions": 0,
                "descriptions": 0,
                "metadata": 0,
                "dependent": 0,
                "still_image": 0,
                "multilayer": 0
            },
            "tags": {
                "ENCODER": "Lavc61.33.102 libx264",
                "DURATION": "00:00:02.000000000"
            }
        },
        {
            "index": 1,
            "codec_name": "aac",
            "codec_long_name": "AAC (Advanced Audio Coding)",
            "profile": "LC",
            "codec_type": "audio",
            "codec_tag_string": "[0][0][0][0]",
            "codec_tag": "0x0000",
            "sample_fmt": "fltp",
            "sample_rate": "44100",
            "channels": 1,
            "channel_layout": "mono",
            "bits_per_sample": 0,
            "initial_padding": 1024,
            "r_frame_rate": "0/0",
            "avg_frame_rate": "0/0",
            "time_base": "1/1000",
            "start_pts": -23,
            "start_time": "-0.023000",
            "extradata_size": 5,
            "disposition": {
                "default": 0,
                "dub": 0,
                "original": 0,
                "comment": 0,
                "lyrics": 0,
                "karaoke": 0,
                "forced": 0,
                "hearing_impaired": 0,
                "visual_impaired": 0,
                "clean_effects": 0,
                "attached_pic": 0,
                "timed_thumbnails": 0,
                "non_diegetic": 0,
                "captions": 0,
                "descriptions": 0,
                "metadata": 0,
                "dependent": 0,
                "still_image": 0,
                "multilayer": 0
            },
            "tags": {
                "ENCODER": "Lavc61.33.102 aac",
                "DURATION": "00:00:02.023000000"
            }
        }
    ],
    "format": {
        "filename": "c:\\Projects\\AsyncFFmpeg\\test_multi.mkv",
        "nb_streams": 2,
        "nb_programs": 0,
        "nb_stream_groups": 0,
        "format_name": "matroska,webm",
        "format_long_name": "Matroska / WebM",
        "start_time": "-0.023000",
        "duration": "2.023000",
        "size": "20429",
        "bit_rate": "80786",
        "probe_score": 100,
        "tags": {
            "ENCODER": "Lavf61.9.107"
        }
    }
}
```

---

## 8. Step 8: Filter Specific Stream Entries (`-show_entries stream=...`)
**Command:**
```powershell
ffprobe -v error -show_entries stream=codec_name,codec_type,width,height,sample_rate,channels,bit_rate,duration -of json c:\Projects\AsyncFFmpeg\test_sample.mp4
```

**Raw Output:**
```json
{
    "programs": [

    ],
    "stream_groups": [

    ],
    "streams": [
        {
            "codec_name": "h264",
            "codec_type": "video",
            "width": 640,
            "height": 480,
            "duration": "2.000000",
            "bit_rate": "8724"
        },
        {
            "codec_name": "aac",
            "codec_type": "audio",
            "sample_rate": "44100",
            "channels": 1,
            "duration": "2.000000",
            "bit_rate": "69698"
        }
    ]
}
```

---

## 9. Step 9: FFprobe Help First 80 Lines
**Command:**
```powershell
ffprobe -h 2>&1 | Select-Object -First 80
```

**Raw Output:**
```
Simple multimedia streams analyzer
usage: ffprobe [OPTIONS] INPUT_FILE

Main options:
-L                  show license
-h <topic>          show help
-? <topic>          show help
-help <topic>       show help
--help <topic>      show help
-version            show version
-buildconf          show build configuration
-formats            show available formats
-muxers             show available muxers
-demuxers           show available demuxers
-devices            show available devices
-codecs             show available codecs
-decoders           show available decoders
-encoders           show available encoders
-bsfs               show available bit stream filters
-protocols          show available protocols
-filters            show available filters
-pix_fmts           show available pixel formats
-layouts            show standard channel layouts
-sample_fmts        show available audio sample formats
-dispositions       show available stream dispositions
-colors             show available color names
-loglevel <loglevel>  set logging level
-v <loglevel>       set logging level
-report             generate a report
-max_alloc <bytes>  set maximum size of a single allocated block
-cpuflags <flags>   force specific cpu flags
-cpucount <count>   force specific cpu count
-hide_banner <hide_banner>  do not show program banner
-sources <device>   list sources of the input device
-sinks <device>     list sinks of the output device
-f <format>         force format
-unit               show unit of the displayed values
-prefix             use SI prefixes for the displayed values
-byte_binary_prefix  use binary prefixes for byte units
-sexagesimal        use sexagesimal format HOURS:MM:SS.MICROSECONDS for time units
-pretty             prettify the format of displayed values, make it more human readable
-output_format <format>  set the output printing format (available formats are: default, compact, csv, flat, ini, json, xml)
-print_format       alias for -output_format (deprecated)
-of <format>        alias for -output_format
-select_streams <stream_specifier>  select the specified streams
-sections           print sections structure and section information, and exit
-show_data          show packets data
-show_data_hash     show packets data hash
-show_error         show probing error
-show_format        show format/container info
-show_frames        show frames info
-show_entries <entry_list>  show a set of specified entries
-show_log           show log
-show_packets       show packets info
-show_programs      show programs info
-show_stream_groups  show stream groups info
-show_streams       show streams info
-show_chapters      show chapters info
-count_frames       count the number of frames per stream
-count_packets      count the number of packets per stream
-show_program_version  show ffprobe version
-show_library_versions  show library versions
-show_versions      show program and library versions
-show_pixel_formats  show pixel format descriptions
-show_optional_fields  show optional fields
-show_private_data  show private data
-private            same as show_private_data
-analyze_frames     analyze frames to provide additional stream-level information
-bitexact           force bitexact output
-read_intervals <read_intervals>  set read intervals
-i <input_file>     read specified file
-o <output_file>    write to specified output
-print_filename <print_file>  override the printed input filename
-find_stream_info   read and decode the streams to fill missing information with heuristics


AVFormatContext AVOptions:
  -avioflags         <flags>      ED......... (default 0)
     direct                       ED......... reduce buffering
  -probesize         <int64>      .D......... set probing size (from 32 to I64_MAX) (default 5000000)
```

---

## 10. Supplemental Findings: Subtitle Stream & Chapter JSON Schema

### Subtitle Stream Probe:
```json
{
    "index": 2,
    "codec_name": "subrip",
    "codec_long_name": "SubRip subtitle",
    "codec_type": "subtitle",
    "codec_tag_string": "[0][0][0][0]",
    "codec_tag": "0x0000",
    "r_frame_rate": "0/0",
    "avg_frame_rate": "0/0",
    "time_base": "1/1000",
    "start_pts": 0,
    "start_time": "0.000000",
    "disposition": {
        "default": 0,
        "forced": 0
    },
    "tags": {
        "language": "eng",
        "title": "English Subs",
        "DURATION": "00:00:02.000000000"
    }
}
```

### Chapter Probe:
```json
"chapters": [
    {
        "id": 0,
        "time_base": "1/1000",
        "start": 0,
        "start_time": "0.000000",
        "end": 1000,
        "end_time": "1.000000",
        "tags": {
            "title": "Chapter 1"
        }
    }
]
```
