import json
import logging
import subprocess
import time
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config
import job_store
import httpx

try:
    import fal_client
except ImportError:  # pragma: no cover - optional until deps installed
    fal_client = None

logger = logging.getLogger("whos-clip-is-it")
DEBUG_LOG_PATH = "/Users/lucasliao/Documents/GitHub/gemini-3-superhack/.cursor/debug.log"
MAX_FAL_RETRIES = 5

DEFAULT_PROMPT = (
    "Photorealistic broadcast-style football highlight still frame. "
    "{description}. {context} Vertical 9:16."
)
DEFAULT_I2I_PREFIX = (
    "You are editing a composite reference image that contains two panels.\n"
    "Use the LEFT panel for character/style continuity and the RIGHT panel for\n"
    "scene composition. Output a single unified image (no split panels)."
)


def _render_prompt(template: str, clip: Dict[str, Any]) -> str:
    players = ", ".join(clip.get("players", []) or [])
    return (
        template.format(
            description=str(clip.get("description", "")).strip(),
            context=str(clip.get("context", "")).strip(),
            players=players,
        )
        .replace("  ", " ")
        .strip()
    )


def _download_image(url: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    def _download() -> None:
        with httpx.stream("GET", url, timeout=120) as response:
            response.raise_for_status()
            with output_path.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)

    _with_retries(_download, label="fal_ref_download")


def _run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("ffmpeg_ref_error stderr=%s", result.stderr.strip())
        raise RuntimeError(result.stderr.strip() or "ffmpeg failed")


def _build_composite(
    left_path: Path,
    right_path: Path,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(
        [
            config.FFMPEG_PATH,
            "-y",
            "-i",
            str(left_path),
            "-i",
            str(right_path),
            "-filter_complex",
            (
                "[0:v]scale=540:960:force_original_aspect_ratio=decrease,"
                "pad=540:960:(ow-iw)/2:(oh-ih)/2[left];"
                "[1:v]scale=540:960:force_original_aspect_ratio=decrease,"
                "pad=540:960:(ow-iw)/2:(oh-ih)/2[right];"
                "[left][right]hstack=inputs=2"
            ),
            "-frames:v",
            "1",
            str(output_path),
        ]
    )


def _debug_log(
    *,
    hypothesis_id: str,
    location: str,
    message: str,
    data: Dict[str, Any],
    run_id: str = "run3",
) -> None:
    payload = {
        "sessionId": "debug-session",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
    except Exception:
        pass


def _with_retries(action, *, label: str) -> Any:
    last_exc = None
    for attempt in range(1, MAX_FAL_RETRIES + 1):
        try:
            return action()
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "fal_retry_failed label=%s attempt=%s error=%s",
                label,
                attempt,
                repr(exc),
            )
            if attempt < MAX_FAL_RETRIES:
                time.sleep(min(2 ** (attempt - 1), 8))
    raise last_exc  # type: ignore[misc]


def generate_reference_frame(
    job_id: str, clip: Dict[str, Any], formats_by_id: Dict[int, Dict[str, Any]]
) -> Optional[Path]:
    generated = generate_keyframes(job_id, clip, formats_by_id)
    return generated[0] if generated else None


def generate_keyframes(
    job_id: str, clip: Dict[str, Any], formats_by_id: Dict[int, Dict[str, Any]]
) -> List[Path]:
    if config.DEMO_MODE or not config.FAL_KEY:
        return []
    if fal_client is None:
        raise RuntimeError("fal-client is not installed")

    clip_id = clip.get("clip_id")
    if not clip_id:
        return []

    format_id = int(clip.get("format_id", 0) or 0)
    format_data = formats_by_id.get(format_id, {})
    # region agent log
    _debug_log(
        hypothesis_id="H1",
        location="backend/reference_frame.py:generate_keyframes:entry",
        message="keyframes_entry",
        data={
            "job_id": job_id,
            "clip_id": clip_id,
            "format_id": format_id,
            "thread_id": threading.get_ident(),
        },
    )
    # endregion agent log

    clip_prompts = clip.get("prompts") or {}
    frame_prompts = clip_prompts.get("frame_prompts")
    if not isinstance(frame_prompts, list) or len(frame_prompts) != 6:
        prompt_template = format_data.get("ref_frame_prompt") or DEFAULT_PROMPT
        base_prompt = _render_prompt(prompt_template, clip)
        frame_prompts = [base_prompt for _ in range(6)]
    frame_prompts = [str(item).strip() for item in frame_prompts]

    i2i_prefix = str(clip_prompts.get("i2i_prompt_prefix") or DEFAULT_I2I_PREFIX).strip()

    assets = clip.get("assets") or {}
    frame_paths: List[Path] = []
    if isinstance(assets.get("frame_paths"), list):
        frame_paths = [Path(path) for path in assets.get("frame_paths") if path]
    if not frame_paths and assets.get("frame_path"):
        frame_paths = [Path(assets["frame_path"])]

    output_dir = job_store.job_dir(job_id) / "assets" / clip_id
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_paths: List[Path] = []

    client = fal_client.SyncClient(key=config.FAL_KEY)
    try:
        for idx, prompt in enumerate(frame_prompts):
            output_path = output_dir / f"gen_frame_{idx + 1:02d}.png"
            if idx == 0:
                model = config.FAL_GROK_IMAGE_MODEL
                arguments = {
                    "prompt": prompt,
                    "num_images": 1,
                    "aspect_ratio": config.FAL_ASPECT_RATIO,
                    "output_format": "png",
                }
            else:
                if frame_paths:
                    reference_frame = frame_paths[min(idx, len(frame_paths) - 1)]
                else:
                    reference_frame = generated_paths[-1]
                composite_path = output_dir / f"composite_{idx + 1:02d}.png"
                _build_composite(generated_paths[-1], reference_frame, composite_path)
                upload_url = _with_retries(
                    lambda: client.upload_file(composite_path),
                    label="fal_keyframe_upload_file",
                )
                model = config.FAL_GROK_IMAGE_EDIT_MODEL
                arguments = {
                    "prompt": f"{i2i_prefix}\n{prompt}",
                    "image_url": upload_url,
                    "num_images": 1,
                    "output_format": "png",
                }

            # region agent log
            _debug_log(
                hypothesis_id="H3",
                location="backend/reference_frame.py:generate_keyframes:pre_generate",
                message="keyframe_pre_generate",
                data={
                    "prompt_len": len(prompt),
                    "model": model,
                    "frame_index": idx + 1,
                },
            )
            # endregion agent log
            response = _with_retries(
                lambda: client.run(model, arguments=arguments),
                label="fal_keyframe_run",
            )
            images = response.get("images") if isinstance(response, dict) else None
            image_url = images[0].get("url") if images else None
            if not image_url:
                raise RuntimeError("Grok image response missing images[0].url")
            _download_image(image_url, output_path)
            generated_paths.append(output_path)
        return generated_paths
    except Exception as exc:
        # region agent log
        _debug_log(
            hypothesis_id="H4",
            location="backend/reference_frame.py:generate_keyframes:exception",
            message="keyframes_exception",
            data={
                "job_id": job_id,
                "clip_id": clip_id,
                "format_id": format_id,
                "error": repr(exc),
            },
        )
        # endregion agent log
        logger.exception(
            "keyframes_failed job_id=%s clip_id=%s format_id=%s",
            job_id,
            clip_id,
            format_id,
        )
        return []
    finally:
        try:
            client.close()
        except Exception:
            pass
