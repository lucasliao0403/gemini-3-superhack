import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import config
import job_store


def _run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg failed")


def _copy_generated(generated_path: Path, final_path: Path) -> None:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(generated_path, final_path)


def postprocess_reels(
    job_id: str,
    clips: List[Dict[str, Any]],
    formats_by_id: Dict[int, Dict[str, Any]],
    generated_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    clips_by_id = {clip["clip_id"]: clip for clip in clips}
    outputs: List[Dict[str, Any]] = []

    for item in generated_items:
        clip_id = item["clip_id"]
        format_id = item["format_id"]
        generated_path = Path(item["generated_path"])
        final_path = generated_path.parent / "final.mp4"

        if config.DEMO_MODE:
            _copy_generated(generated_path, final_path)
        else:
            try:
                _run_ffmpeg(
                    [
                        config.FFMPEG_PATH,
                        "-y",
                        "-i",
                        str(generated_path),
                        "-vf",
                        "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
                        "-c:a",
                        "aac",
                        str(final_path),
                    ]
                )
            except Exception:
                _copy_generated(generated_path, final_path)

        clip = clips_by_id.get(clip_id, {})
        format_data = formats_by_id.get(format_id, {})
        duration_s = int(format_data.get("length_s", 0)) or int(
            max(1, (clip.get("end_ms", 0) - clip.get("start_ms", 0)) / 1000)
        )

        poster_path = None
        assets = clip.get("assets") or {}
        if "frame_path" in assets:
            poster_path = Path(assets["frame_path"])

        outputs.append(
            {
                "id": f"{clip_id}_{format_id}",
                "clip_id": clip_id,
                "format_id": format_id,
                "final_path": final_path,
                "poster_path": poster_path,
                "duration_s": duration_s,
            }
        )

    return outputs
