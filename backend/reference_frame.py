import json
import logging
import time
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import config
import job_store
import httpx

try:
    import fal_client
except ImportError:  # pragma: no cover - optional until deps installed
    fal_client = None

logger = logging.getLogger("whos-clip-is-it")
DEBUG_LOG_PATH = "/Users/lucasliao/Documents/GitHub/gemini-3-superhack/.cursor/debug.log"

DEFAULT_PROMPT = (
    "Photorealistic broadcast-style football highlight still frame. "
    "{description}. {context} Vertical 9:16."
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
    with httpx.stream("GET", url, timeout=120) as response:
        response.raise_for_status()
        with output_path.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)


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


def generate_reference_frame(
    job_id: str, clip: Dict[str, Any], formats_by_id: Dict[int, Dict[str, Any]]
) -> Optional[Path]:
    if config.DEMO_MODE or not config.FAL_KEY:
        return None
    if fal_client is None:
        raise RuntimeError("fal-client is not installed")

    clip_id = clip.get("clip_id")
    if not clip_id:
        return None

    format_id = int(clip.get("format_id", 0) or 0)
    format_data = formats_by_id.get(format_id, {})
    # region agent log
    _debug_log(
        hypothesis_id="H1",
        location="backend/reference_frame.py:generate_reference_frame:entry",
        message="ref_frame_entry",
        data={
            "job_id": job_id,
            "clip_id": clip_id,
            "format_id": format_id,
            "thread_id": threading.get_ident(),
        },
    )
    # endregion agent log
    clip_prompts = clip.get("prompts") or {}
    prompt = clip_prompts.get("image_prompt")
    if not prompt:
        prompt_template = format_data.get("ref_frame_prompt") or DEFAULT_PROMPT
        prompt = _render_prompt(prompt_template, clip)

    assets = clip.get("assets") or {}
    frame_path = Path(assets["frame_path"]) if assets.get("frame_path") else None
    # region agent log
    _debug_log(
        hypothesis_id="H2",
        location="backend/reference_frame.py:generate_reference_frame:image_input",
        message="ref_frame_image_input",
        data={
            "frame_path": str(frame_path) if frame_path else None,
            "frame_exists": bool(frame_path and frame_path.exists()),
        },
    )
    # endregion agent log

    output_path = job_store.job_dir(job_id) / "assets" / clip_id / "ref_frame.png"

    client = fal_client.SyncClient(key=config.FAL_KEY)
    try:
        use_edit = bool(frame_path and frame_path.exists())
        if use_edit:
            upload_url = client.upload_file(frame_path)
            model = config.FAL_NANO_BANANA_EDIT_MODEL
            arguments = {
                "prompt": prompt,
                "image_urls": [upload_url],
                "num_images": 1,
                "aspect_ratio": config.FAL_NANO_BANANA_ASPECT_RATIO,
            }
        else:
            model = config.FAL_NANO_BANANA_MODEL
            arguments = {
                "prompt": prompt,
                "num_images": 1,
                "aspect_ratio": config.FAL_NANO_BANANA_ASPECT_RATIO,
            }
        # region agent log
        _debug_log(
            hypothesis_id="H3",
            location="backend/reference_frame.py:generate_reference_frame:pre_generate",
            message="ref_frame_pre_generate",
            data={
                "prompt_len": len(prompt),
                "model": model,
                "using_edit": use_edit,
            },
        )
        # endregion agent log
        response = client.run(model, arguments=arguments)
        images = response.get("images") if isinstance(response, dict) else None
        image_url = images[0].get("url") if images else None
        if not image_url:
            logger.warning(
                "nanobanana_no_image job_id=%s clip_id=%s format_id=%s",
                job_id,
                clip_id,
                format_id,
            )
            return None
        _download_image(image_url, output_path)
        logger.info(
            "nanobanana_saved job_id=%s clip_id=%s format_id=%s path=%s",
            job_id,
            clip_id,
            format_id,
            output_path,
        )
        return output_path
    except Exception as exc:
        # region agent log
        _debug_log(
            hypothesis_id="H4",
            location="backend/reference_frame.py:generate_reference_frame:exception",
            message="ref_frame_exception",
            data={
                "job_id": job_id,
                "clip_id": clip_id,
                "format_id": format_id,
                "frame_path": str(frame_path) if frame_path else None,
                "frame_exists": bool(frame_path and frame_path.exists()),
                "error": repr(exc),
            },
        )
        # endregion agent log
        logger.exception(
            "nanobanana_failed job_id=%s clip_id=%s format_id=%s",
            job_id,
            clip_id,
            format_id,
        )
        return None
    finally:
        try:
            client.close()
        except Exception:
            pass
