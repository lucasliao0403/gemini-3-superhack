import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config
import job_store
import httpx

logger = logging.getLogger("whos-clip-is-it")
DEBUG_LOG_PATH = "/Users/lucasliao/Documents/GitHub/gemini-3-superhack/.cursor/debug.log"
MAX_FAL_RETRIES = 5


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


def _serialize_payload(value: Any, depth: int = 0, max_depth: int = 4) -> Any:
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
            str(key): _serialize_payload(item, depth + 1, max_depth)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_serialize_payload(item, depth + 1, max_depth) for item in value]
    for method_name in ("model_dump", "to_dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            try:
                return _serialize_payload(method(), depth + 1, max_depth)
            except Exception:
                break
    if hasattr(value, "__dict__"):
        try:
            return _serialize_payload(value.__dict__, depth + 1, max_depth)
        except Exception:
            pass
    return repr(value)

try:
    import fal_client
except ImportError:  # pragma: no cover - optional until deps installed
    fal_client = None

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


def _map_num_frames(duration_s: int, fps: int) -> int:
    fps = max(4, min(60, fps))
    estimated = int(duration_s * fps) + 1
    return max(17, min(161, estimated))


def _select_video_input(
    requested_mode: str,
    clip_path: Optional[Path],
) -> Tuple[str, Optional[Path], Optional[str]]:
    if requested_mode == "video_plus_prompt":
        if clip_path and clip_path.exists():
            return "video_to_video", clip_path, None
        return "video_to_video", None, "missing_clip_for_video_plus_prompt"
    if requested_mode in {"image_plus_prompt", "audio_plus_prompt", "prompt_only"}:
        if clip_path and clip_path.exists():
            return "video_to_video", clip_path, f"fallback_from_{requested_mode}"
        return "video_to_video", None, f"missing_clip_for_{requested_mode}"
    if clip_path and clip_path.exists():
        return "video_to_video", clip_path, f"fallback_from_{requested_mode or 'unknown'}"
    return "video_to_video", None, f"missing_clip_for_{requested_mode or 'unknown'}"


def _download_to_path(url: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    def _download() -> None:
        with httpx.stream("GET", url, timeout=300) as response:
            response.raise_for_status()
            with output_path.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)

    _with_retries(_download, label="fal_download")


def _generate_with_fal_sync(
    job_id: str,
    clip_id: str,
    format_id: int,
    prompt: str,
    model: str,
    output_path: Path,
    reference_paths: List[Path],
    movement_amplitude: str,
) -> Tuple[Path, Dict[str, Any]]:
    if fal_client is None:
        raise RuntimeError("fal-client is not installed")
    if not config.FAL_KEY:
        raise RuntimeError("Missing FAL_KEY")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    request_payload = {
        "prompt": prompt,
        "aspect_ratio": config.FAL_ASPECT_RATIO,
        "movement_amplitude": movement_amplitude,
        "reference_image_urls": [],
    }
    # region agent log
    _debug_log(
        hypothesis_id="H1",
        location="backend/generation.py:_generate_with_fal_sync:entry",
        message="enter_generate_with_fal",
        data={
            "job_id": job_id,
            "clip_id": clip_id,
            "format_id": format_id,
            "model": model,
            "reference_count": len(reference_paths),
            "movement_amplitude": movement_amplitude,
        },
    )
    # endregion agent log
    client = fal_client.SyncClient(key=config.FAL_KEY)
    try:
        reference_urls = []
        for path in reference_paths:
            reference_urls.append(
                _with_retries(lambda: client.upload_file(path), label="fal_upload_file")
            )
        request_payload["reference_image_urls"] = reference_urls
        print(
            "fal_generation_start "
            f"job_id={job_id} clip_id={clip_id} format_id={format_id} model={model}"
        )
        response = _with_retries(
            lambda: client.run(model, arguments=request_payload),
            label="fal_run",
        )
        video_info = response.get("video") if isinstance(response, dict) else None
        video_url = video_info.get("url") if isinstance(video_info, dict) else None
        if not video_url:
            raise RuntimeError("FAL response missing video.url")
        _download_to_path(video_url, output_path)
        print(f"fal_generation_done saved_path={output_path}")
        fal_debug = {
            "model": model,
            "input": _serialize_payload(request_payload),
            "response": _serialize_payload(response),
        }
        return output_path, fal_debug
    finally:
        try:
            client.close()
        except Exception:
            pass


async def generate_reels(
    job_id: str,
    clips: List[Dict[str, Any]],
    formats_by_id: Dict[int, Dict[str, Any]],
    concurrency: int = config.FAL_MAX_CONCURRENCY,
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
                if config.DEMO_MODE or not config.FAL_KEY:
                    logger.warning(
                        "fal_generation_skipped job_id=%s clip_id=%s reason=missing_api_key_or_demo",
                        job_id,
                        clip.get("clip_id"),
                    )
                    raise RuntimeError("FAL generation skipped (missing FAL_KEY)")

                format_data = formats_by_id.get(format_id, {})
                clip_prompts = clip.get("prompts") or {}
                prompt = clip_prompts.get("video_prompt") or _render_prompt(
                    format_data.get("prompt_template", ""), clip
                )
                assets = clip.get("assets") or {}
                generated_frame_paths = assets.get("generated_frame_paths")
                if not isinstance(generated_frame_paths, list) or len(generated_frame_paths) < 2:
                    raise RuntimeError("Missing generated keyframes for Vidu reference-to-video")
                reference_paths = [Path(path) for path in generated_frame_paths]
                model = str(
                    format_data.get("model") or config.FAL_VIDU_REFERENCE_MODEL
                ).strip()
                movement_amplitude = str(format_data.get("movement_amplitude", "auto"))
                generated_path, fal_debug = await asyncio.to_thread(
                    _generate_with_fal_sync,
                    job_id,
                    clip.get("clip_id"),
                    format_id,
                    prompt,
                    model,
                    output_dir / "generated.mp4",
                    reference_paths,
                    movement_amplitude,
                )
            except Exception:
                logger.exception(
                    "fal_generation_failed job_id=%s clip_id=%s format_id=%s",
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
                    "fal_debug": fal_debug,
                }
            )

    await asyncio.gather(*[_run_one(clip) for clip in clips])
    return results
