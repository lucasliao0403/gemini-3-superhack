import logging
import subprocess
from pathlib import Path
from typing import List

import config

logger = logging.getLogger("whos-clip-is-it")


def _run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("ffmpeg_storyboard_error stderr=%s", result.stderr.strip())
        raise RuntimeError(result.stderr.strip() or "ffmpeg failed")


def build_vertical_storyboard(
    frames: List[Path],
    output_path: Path,
    *,
    target_width: int = 720,
) -> None:
    if not frames:
        raise ValueError("No frames provided for storyboard")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    input_args: list[str] = []
    filter_parts: list[str] = []
    for idx, frame in enumerate(frames):
        input_args.extend(["-i", str(frame)])
        filter_parts.append(
            f"[{idx}:v]scale={target_width}:-1:"
            "force_original_aspect_ratio=decrease,"
            f"pad={target_width}:ih:(ow-iw)/2:(oh-ih)/2,"
            f"setsar=1[v{idx}]"
        )

    if len(frames) == 1:
        filter_complex = filter_parts[0]
    else:
        inputs = "".join([f"[v{idx}]" for idx in range(len(frames))])
        filter_complex = (
            ";".join(filter_parts)
            + f";{inputs}vstack=inputs={len(frames)}"
        )

    _run_ffmpeg(
        [
            config.FFMPEG_PATH,
            "-y",
            *input_args,
            "-filter_complex",
            filter_complex,
            "-frames:v",
            "1",
            str(output_path),
        ]
    )
