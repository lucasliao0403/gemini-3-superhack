import logging
import subprocess
from pathlib import Path
from typing import Any, Dict

import config

logger = logging.getLogger("whos-clip-is-it")


def _run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("ffmpeg_error stderr=%s", result.stderr.strip())
        raise RuntimeError(result.stderr.strip() or "ffmpeg failed")


def probe_duration_ms(input_path: Path) -> int:
    args = [
        config.FFPROBE_PATH,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(input_path),
    ]
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffprobe failed")
    duration = float(result.stdout.strip())
    print(f"ffprobe_duration_ms duration={int(duration * 1000)}")
    return int(duration * 1000)


def _peak_weighted_timestamps(
    *, start_s: float, peak_s: float, end_s: float, count: int = 6
) -> list[float]:
    total = max(end_s - start_s, 0.001)
    pre = max(peak_s - start_s, 0.0)
    post = max(end_s - peak_s, 0.0)
    near_offset = min(total * 0.05, pre * 0.5, post * 0.5)

    times = [
        start_s + pre * 0.25 if pre > 0 else start_s,
        start_s + pre * 0.75 if pre > 0 else start_s,
        peak_s - near_offset,
        peak_s + near_offset,
        peak_s + post * 0.25 if post > 0 else end_s,
        peak_s + post * 0.75 if post > 0 else end_s,
    ]
    times = [max(start_s, min(end_s, value)) for value in times]
    min_step = max(total / max(count * 10, 1), 0.02)
    stabilized = []
    for value in times:
        if stabilized and value <= stabilized[-1] + min_step:
            value = min(end_s, stabilized[-1] + min_step)
        stabilized.append(value)
    return stabilized[:count]


def extract_assets(input_path: Path, clip: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    beat_timestamps_ms = clip.get("beat_timestamps_ms")
    timestamps: list[float]
    if isinstance(beat_timestamps_ms, list) and len(beat_timestamps_ms) >= 6:
        timestamps = [value / 1000.0 for value in beat_timestamps_ms[:6]]
        start_s = timestamps[0]
        end_s = timestamps[-1]
        peak_s = timestamps[3] if len(timestamps) >= 4 else timestamps[0]
    else:
        start_s = clip["start_ms"] / 1000.0
        peak_s = clip["peak_ms"] / 1000.0
        end_s = clip["end_ms"] / 1000.0
        timestamps = _peak_weighted_timestamps(
            start_s=start_s,
            peak_s=peak_s,
            end_s=end_s,
            count=6,
        )
    clip_id = clip.get("clip_id", "unknown")

    print(
        "ffmpeg_extract_start "
        f"clip_id={clip_id} start={start_s} peak={peak_s} end={end_s}"
    )

    frame_paths = [
        output_dir / f"frame_{idx:02d}.png"
        for idx in range(1, 7)
    ]
    clip_path = output_dir / "clip.mp4"
    audio_path = output_dir / "audio.wav"

    for frame_path, timestamp in zip(frame_paths, timestamps):
        _run_ffmpeg(
            [
                config.FFMPEG_PATH,
                "-y",
                "-ss",
                f"{timestamp}",
                "-i",
                str(input_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(frame_path),
            ]
        )

    _run_ffmpeg(
        [
            config.FFMPEG_PATH,
            "-y",
            "-ss",
            f"{start_s}",
            "-to",
            f"{end_s}",
            "-i",
            str(input_path),
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(clip_path),
        ]
    )

    _run_ffmpeg(
        [
            config.FFMPEG_PATH,
            "-y",
            "-ss",
            f"{start_s}",
            "-to",
            f"{end_s}",
            "-i",
            str(input_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "44100",
            str(audio_path),
        ]
    )

    print(f"ffmpeg_extract_done clip_id={clip_id}")
    return {
        "frame_path": frame_paths[2] if len(frame_paths) >= 3 else frame_paths[0],
        "frame_paths": frame_paths,
        "clip_path": clip_path,
        "audio_path": audio_path,
    }
