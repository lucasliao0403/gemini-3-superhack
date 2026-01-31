import asyncio
import inspect
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config
import job_store

logger = logging.getLogger("whos-clip-is-it")
DEBUG_LOG_PATH = "/Users/lucasliao/Documents/GitHub/gemini-3-superhack/.cursor/debug.log"


def _debug_log(
    *,
    hypothesis_id: str,
    location: str,
    message: str,
    data: Dict[str, Any],
    run_id: str = "run1",
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


def _serialize_veo_payload(value: Any, depth: int = 0, max_depth: int = 4) -> Any:
    if depth >= max_depth:
        return repr(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {
            str(key): _serialize_veo_payload(item, depth + 1, max_depth)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_serialize_veo_payload(item, depth + 1, max_depth) for item in value]
    for method_name in ("model_dump", "to_dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            try:
                return _serialize_veo_payload(method(), depth + 1, max_depth)
            except Exception:
                break
    if hasattr(value, "__dict__"):
        try:
            return _serialize_veo_payload(value.__dict__, depth + 1, max_depth)
        except Exception:
            pass
    return repr(value)

try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover - optional until deps installed
    genai = None
    types = None

def _render_prompt(template: str, clip: Dict[str, Any]) -> str:
    return (
        template.replace("{{description}}", str(clip.get("description", "")))
        .replace("{{context}}", str(clip.get("context", "")))
        .replace("{{players}}", ", ".join(clip.get("players", []) or []))
        .strip()
    )


def _map_duration_seconds(length_s: Optional[float]) -> int:
    allowed = [4, 6, 8]
    if not length_s:
        return 6
    return sorted(allowed, key=lambda value: (abs(length_s - value), -value))[0]


def _select_input_mode(
    requested_mode: str,
    frame_path: Optional[Path],
) -> Tuple[str, Optional[Path], Optional[str]]:
    if requested_mode == "image_plus_prompt":
        if frame_path and frame_path.exists():
            return "image_to_video", frame_path, None
        return "text_to_video", None, "missing_frame_for_image_plus_prompt"
    if requested_mode == "prompt_only":
        return "text_to_video", None, None
    if requested_mode in {"audio_plus_prompt", "video_plus_prompt"}:
        if frame_path and frame_path.exists():
            return "image_to_video", frame_path, f"fallback_from_{requested_mode}"
        return "text_to_video", None, f"fallback_from_{requested_mode}"
    return "text_to_video", None, f"fallback_from_{requested_mode or 'unknown'}"


def _generate_with_veo_sync(
    job_id: str,
    clip_id: str,
    format_id: int,
    prompt: str,
    mode: str,
    duration_s: int,
    output_path: Path,
    frame_path: Optional[Path],
) -> Tuple[Path, Dict[str, Any]]:
    if genai is None or types is None:
        raise RuntimeError("google-genai is not installed")

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # region agent log
        _debug_log(
            hypothesis_id="H1",
            location="backend/generation.py:_generate_with_veo_sync:entry",
            message="enter_generate_with_veo",
            data={
                "job_id": job_id,
                "clip_id": clip_id,
                "format_id": format_id,
                "mode": mode,
                "duration_s": duration_s,
                "frame_path": str(frame_path) if frame_path else None,
                "frame_exists": bool(frame_path and frame_path.exists()),
                "genai_version": getattr(genai, "__version__", None),
            },
        )
        # endregion agent log
        veo_config = types.GenerateVideosConfig(
            aspect_ratio=config.VEO_ASPECT_RATIO,
            resolution=config.VEO_RESOLUTION,
            duration_seconds=duration_s,
        )
        # region agent log
        _debug_log(
            hypothesis_id="H3",
            location="backend/generation.py:_generate_with_veo_sync:config",
            message="veo_config_ready",
            data={
                "aspect_ratio": config.VEO_ASPECT_RATIO,
                "resolution": config.VEO_RESOLUTION,
                "duration_s": duration_s,
            },
        )
        # endregion agent log
        image_input = None
        if mode == "image_to_video" and frame_path:
            print(
                "veo_generation_image_input "
                f"job_id={job_id} clip_id={clip_id} format_id={format_id} path={frame_path}"
            )
            # region agent log
            try:
                from_file_sig = str(inspect.signature(types.Image.from_file))
            except Exception as exc:
                from_file_sig = f"signature_error:{repr(exc)}"
            # endregion agent log
            # region agent log
            _debug_log(
                hypothesis_id="H2",
                location="backend/generation.py:_generate_with_veo_sync:image_signature",
                message="image_factory_signatures",
                data={
                    "from_file_sig": from_file_sig,
                    "has_from_bytes": hasattr(types.Image, "from_bytes"),
                    "has_from_uri": hasattr(types.Image, "from_uri"),
                },
            )
            # endregion agent log
            # region agent log
            _debug_log(
                hypothesis_id="H1",
                location="backend/generation.py:_generate_with_veo_sync:image_before",
                message="about_to_load_image",
                data={
                    "frame_path": str(frame_path),
                    "from_file_repr": repr(getattr(types.Image, "from_file", None)),
                    "from_file_signature": getattr(
                        getattr(types.Image, "from_file", None), "__text_signature__", None
                    ),
                },
            )
            # endregion agent log
            try:
                image_input = types.Image.from_file(location=str(frame_path))
            except Exception as exc:
                # region agent log
                _debug_log(
                    hypothesis_id="H1",
                    location="backend/generation.py:_generate_with_veo_sync:image_error",
                    message="image_load_failed",
                    data={
                        "error": repr(exc),
                        "frame_path": str(frame_path),
                    },
                )
                # endregion agent log
                raise
            # region agent log
            _debug_log(
                hypothesis_id="H1",
                location="backend/generation.py:_generate_with_veo_sync:image_after",
                message="image_loaded",
                data={"image_input_type": str(type(image_input))},
            )
            # endregion agent log

        print(
            "veo_generation_start "
            f"job_id={job_id} clip_id={clip_id} format_id={format_id} "
            f"mode={mode} duration_s={duration_s}"
        )
        operation = client.models.generate_videos(
            model=config.VEO_MODEL,
            prompt=prompt,
            image=image_input,
            config=veo_config,
        )
        # region agent log
        _debug_log(
            hypothesis_id="H4",
            location="backend/generation.py:_generate_with_veo_sync:operation_start",
            message="operation_created",
            data={
                "operation_name": getattr(operation, "name", None),
                "operation_done": getattr(operation, "done", None),
                "mode": mode,
            },
        )
        # endregion agent log
        while not operation.done:
            print(
                "veo_generation_poll "
                f"operation={getattr(operation, 'name', 'unknown')} done=false"
            )
            time.sleep(10)
            operation = client.operations.get(operation)

        response = getattr(operation, "response", None)
        generated_videos = getattr(response, "generated_videos", None) if response else None
        response_dump_keys = None
        response_dump = None
        if response is not None and hasattr(response, "model_dump"):
            try:
                response_dump = response.model_dump()
                response_dump_keys = list(response_dump.keys())
            except Exception:
                response_dump_keys = ["model_dump_failed"]
        veo_debug = {
            "operation": _serialize_veo_payload(operation),
            "response": _serialize_veo_payload(response_dump if response_dump is not None else response),
            "generated_videos": _serialize_veo_payload(generated_videos),
        }
        # region agent log
        _debug_log(
            hypothesis_id="H7",
            location="backend/generation.py:_generate_with_veo_sync:operation_done_state",
            message="operation_done_state",
            data={
                "operation_done": getattr(operation, "done", None),
                "has_response": bool(response),
                "response_type": str(type(response)),
                "response_attrs": [
                    attr
                    for attr in ("generated_videos", "error", "status", "name")
                    if response and hasattr(response, attr)
                ],
                "generated_videos_len": len(generated_videos) if generated_videos is not None else None,
                "operation_error": repr(getattr(operation, "error", None)),
                "response_dump_keys": response_dump_keys,
                "rai_media_filtered_count": response_dump.get("rai_media_filtered_count")
                if isinstance(response_dump, dict)
                else None,
                "rai_media_filtered_reasons": response_dump.get("rai_media_filtered_reasons")
                if isinstance(response_dump, dict)
                else None,
            },
        )
        # endregion agent log
        if response is None:
            raise RuntimeError("Veo operation completed without response")
        if not generated_videos:
            if isinstance(response_dump, dict) and response_dump.get("rai_media_filtered_count"):
                raise RuntimeError(
                    "Veo generation blocked by safety filters "
                    f"reasons={response_dump.get('rai_media_filtered_reasons')}"
                )
            raise RuntimeError("Veo operation has no generated_videos")

        generated_video = generated_videos[0]
        client.files.download(file=generated_video.video)
        generated_video.video.save(str(output_path))
        print(f"veo_generation_done saved_path={output_path}")
        # region agent log
        _debug_log(
            hypothesis_id="H4",
            location="backend/generation.py:_generate_with_veo_sync:operation_done",
            message="operation_completed",
            data={
                "operation_done": getattr(operation, "done", None),
                "has_response": bool(getattr(operation, "response", None)),
                "output_path": str(output_path),
            },
        )
        # endregion agent log
        return output_path, veo_debug
    finally:
        client.close()


async def generate_reels(
    job_id: str,
    clips: List[Dict[str, Any]],
    formats_by_id: Dict[int, Dict[str, Any]],
    concurrency: int = config.VEO_MAX_CONCURRENCY,
) -> List[Dict[str, Any]]:
    concurrency = max(1, concurrency)
    semaphore = asyncio.Semaphore(concurrency)
    results: List[Dict[str, Any]] = []

    async def _run_one(clip: Dict[str, Any]) -> None:
        async with semaphore:
            format_id = int(clip.get("format_id", 1))
            output_dir = job_store.job_dir(job_id) / "reels" / clip["clip_id"] / str(format_id)
            print(
                "generation_start "
                f"job_id={job_id} clip_id={clip.get('clip_id')} format_id={format_id}"
            )

            try:
                if config.DEMO_MODE or not config.GEMINI_API_KEY:
                    logger.warning(
                        "veo_generation_skipped job_id=%s clip_id=%s reason=missing_api_key_or_demo",
                        job_id,
                        clip.get("clip_id"),
                    )
                    raise RuntimeError("Veo generation skipped (missing GEMINI_API_KEY)")

                format_data = formats_by_id.get(format_id, {})
                prompt = _render_prompt(format_data.get("prompt_template", ""), clip)
                duration_s = _map_duration_seconds(format_data.get("length_s"))
                assets = clip.get("assets") or {}
                frame_path = Path(assets["frame_path"]) if assets.get("frame_path") else None
                mode, image_frame, fallback = _select_input_mode(
                    str(format_data.get("input_mode", "")).strip(),
                    frame_path,
                )
                if fallback:
                    print(
                        "veo_generation_fallback "
                        f"job_id={job_id} clip_id={clip.get('clip_id')} "
                        f"format_id={format_id} reason={fallback}"
                    )
                generated_path, veo_debug = await asyncio.to_thread(
                    _generate_with_veo_sync,
                    job_id,
                    clip.get("clip_id"),
                    format_id,
                    prompt,
                    mode,
                    duration_s,
                    output_dir / "generated.mp4",
                    image_frame,
                )
            except Exception:
                logger.exception(
                    "veo_generation_failed job_id=%s clip_id=%s format_id=%s",
                    job_id,
                    clip.get("clip_id"),
                    format_id,
                )
                raise

            print(
                "generation_done "
                f"job_id={job_id} clip_id={clip.get('clip_id')} output={generated_path}"
            )
            results.append(
                {
                    "clip_id": clip["clip_id"],
                    "format_id": format_id,
                    "generated_path": generated_path,
                    "veo_debug": veo_debug,
                }
            )

    await asyncio.gather(*[_run_one(clip) for clip in clips])
    return results
