"""Input discovery and upload plan construction."""
from .legacy import (
    collect_video_files, infer_media_type, build_uploadrr_command, build_plan,
    nearest_existing_parent, hardlink_device_issues,
)
