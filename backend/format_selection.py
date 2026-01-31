import json
from pathlib import Path
from typing import Any, Dict, List

import config


def load_formats() -> List[Dict[str, Any]]:
    formats_path = config.PROMPTS_DIR / "formats.json"
    if not formats_path.exists():
        return []
    return json.loads(formats_path.read_text())


def select_format_id(clip: Dict[str, Any]) -> int:
    clip_type = clip.get("type", "big_play")
    energy = int(clip.get("announcer_energy", 5))

    mapping = {
        "big_play": 10 if energy >= 8 else 3,
        "fail": 8,
        "reaction": 5,
        "controversial": 6,
        "clutch": 13,
        "funny": 7,
    }
    return mapping.get(clip_type, 1)


def assign_format_ids(
    clips: List[Dict[str, Any]], formats_by_id: Dict[int, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    updated = []
    for clip in clips:
        format_id = select_format_id(clip)
        if format_id not in formats_by_id and formats_by_id:
            format_id = next(iter(formats_by_id.keys()))
        clip = dict(clip)
        clip["format_id"] = format_id
        updated.append(clip)
    return updated
