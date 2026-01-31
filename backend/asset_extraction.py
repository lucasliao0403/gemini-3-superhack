import logging
import subprocess
from pathlib import Path
from typing import Dict

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
    logger.info("ffprobe_duration_ms duration=%s", int(duration * 1000))
    return int(duration * 1000)


def extract_assets(input_path: Path, clip: Dict[str, int], output_dir: Path) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    start_s = clip["start_ms"] / 1000.0
    peak_s = clip["peak_ms"] / 1000.0
    end_s = clip["end_ms"] / 1000.0
    clip_id = clip.get("clip_id", "unknown")

    logger.info(
        "ffmpeg_extract_start clip_id=%s start=%s peak=%s end=%s",
        clip_id,
        start_s,
        peak_s,
        end_s,
    )

    frame_path = output_dir / "frame.png"
    clip_path = output_dir / "clip.mp4"
    audio_path = output_dir / "audio.wav"

    _run_ffmpeg(
        [
            config.FFMPEG_PATH,
            "-y",
            "-ss",
            f"{peak_s}",
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

    logger.info("ffmpeg_extract_done clip_id=%s", clip_id)
    return {"frame_path": frame_path, "clip_path": clip_path, "audio_path": audio_path}
