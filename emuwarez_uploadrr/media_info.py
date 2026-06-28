"""MediaInfo parsing and technical metadata helpers."""
from .legacy import (
    run_mediainfo_json, media_tracks, first_track, map_resolution,
    detect_video_codec, detect_hdr, audio_codec, audio_channels,
    map_audio_language, map_subtitle_language, subtitle_format, subtitle_forced,
    read_media_info, audio_name,
)
