import json
from pathlib import Path
from typing import Any, Dict, List

import config
import random


def load_formats() -> List[Dict[str, Any]]:
    formats_path = config.PROMPTS_DIR / "formats.json"
    if not formats_path.exists():
        return []
    return json.loads(formats_path.read_text())


def select_format_id(formats_by_id: Dict[int, Dict[str, Any]]) -> int:
    """
    Pick a random format from those available in prompts/formats.json.

    Note: The pipeline is intentionally "one reel" (Gemini clip schema currently
    returns 1 clip), but we still randomize the style/format of that reel.
    """
    if not formats_by_id:
        return 1
    return random.choice(list(formats_by_id.keys()))


def assign_format_ids(
    clips: List[Dict[str, Any]], formats_by_id: Dict[int, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    updated = []
    for clip in clips:
        format_id = select_format_id(formats_by_id)
        clip = dict(clip)
        clip["format_id"] = format_id
        updated.append(clip)
    return updated
