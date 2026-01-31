from typing import Any, Dict, List, Optional


def parse_timestamp(value: str) -> int:
    parts = value.strip().split(":")
    if not parts or len(parts) > 3:
        raise ValueError(f"Invalid timestamp: {value}")
    parts = [int(p) for p in parts]
    if len(parts) == 2:
        minutes, seconds = parts
        hours = 0
    else:
        hours, minutes, seconds = parts
    total_seconds = hours * 3600 + minutes * 60 + seconds
    return int(total_seconds * 1000)


def extract_raw_clips(analysis: Any) -> List[Dict[str, Any]]:
    if isinstance(analysis, list):
        return analysis
    if isinstance(analysis, dict):
        if "clips" in analysis and isinstance(analysis["clips"], list):
            return analysis["clips"]
    return []


def _clamp(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(value, max_value))


def normalize_clips(
    raw_clips: List[Dict[str, Any]],
    duration_ms: Optional[int] = None,
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for clip in raw_clips:
        try:
            start_ms = parse_timestamp(str(clip.get("start", "")))
            peak_ms = parse_timestamp(str(clip.get("peak", "")))
            end_ms = parse_timestamp(str(clip.get("end", "")))
        except Exception:
            continue

        if duration_ms is not None:
            start_ms = _clamp(start_ms, 0, duration_ms)
            peak_ms = _clamp(peak_ms, 0, duration_ms)
            end_ms = _clamp(end_ms, 0, duration_ms)

        if not (start_ms < peak_ms < end_ms):
            continue

        normalized.append(
            {
                "start_ms": start_ms,
                "peak_ms": peak_ms,
                "end_ms": end_ms,
                "type": str(clip.get("type", "big_play")),
                "description": str(clip.get("description", "")),
                "players": clip.get("players") or [],
                "context": str(clip.get("context", "")),
                "announcer_energy": int(clip.get("announcer_energy", 5)),
                "crowd_energy": int(clip.get("crowd_energy", 5)),
            }
        )
    return normalized
