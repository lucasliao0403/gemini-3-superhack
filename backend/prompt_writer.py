import json
import logging
import time
from typing import Any, Dict, List, Optional

import config

try:
    from google import genai
    from google.genai import errors as genai_errors
except ImportError:  # pragma: no cover - optional until deps installed
    genai = None
    genai_errors = None

logger = logging.getLogger("whos-clip-is-it")
MAX_GEMINI_OVERLOAD_RETRIES = 5
RETRYABLE_OVERLOAD_STATUS = 503

PROMPT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["frame_prompts", "video_prompt", "i2i_prompt_prefix"],
    "properties": {
        "frame_prompts": {
            "type": "array",
            "minItems": 6,
            "maxItems": 6,
            "items": {"type": "string"},
        },
        "video_prompt": {"type": "string"},
        "i2i_prompt_prefix": {"type": "string"},
        "segment_script": {"type": "string"},
    },
}


def _is_overloaded_error(exc: Exception) -> bool:
    if genai_errors and isinstance(exc, genai_errors.ServerError):
        status_code = getattr(exc, "status_code", None)
        if status_code == RETRYABLE_OVERLOAD_STATUS:
            return True
    message = str(exc).lower()
    return "503" in message and "overloaded" in message


def _generate_with_retry(client: Any, *, contents: str, config_data: Dict[str, Any]) -> Any:
    last_exc: Optional[Exception] = None
    for attempt in range(1, MAX_GEMINI_OVERLOAD_RETRIES + 1):
        try:
            return client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=contents,
                config=config_data,
            )
        except Exception as exc:
            last_exc = exc
            if not _is_overloaded_error(exc) or attempt == MAX_GEMINI_OVERLOAD_RETRIES:
                raise
            backoff_s = min(2 ** (attempt - 1), 8)
            logger.warning(
                "gemini_overloaded retrying attempt=%s backoff_s=%s",
                attempt,
                backoff_s,
            )
            time.sleep(backoff_s)
    raise last_exc  # type: ignore[misc]


def write_prompts(
    *,
    job_id: str,
    clip: Dict[str, Any],
    format_data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if config.DEMO_MODE or not config.GEMINI_API_KEY:
        return None
    if genai is None:
        raise RuntimeError("google-genai is not installed")

    reference = str(format_data.get("prompt_reference", "")).strip()
    ignore_real_beats = bool(format_data.get("ignore_real_beats"))
    description = str(clip.get("description", "")).strip()
    context = str(clip.get("context", "")).strip()
    players = ", ".join(clip.get("players", []) or [])
    clip_type = str(clip.get("type", "")).strip()
    physical_attributes = clip.get("physical_attributes") or {}
    physical_block = ""
    if isinstance(physical_attributes, dict) and physical_attributes:
        physical_block = "Player physical attributes:\n"
        for name, attrs in physical_attributes.items():
            physical_block += f"- {name}: {attrs}\n"

    storyboard_frames = clip.get("generated_storyboard_frames") or []
    storyboard_block = ""
    if not ignore_real_beats and isinstance(storyboard_frames, list) and storyboard_frames:
        storyboard_block = "Generated storyboard beats (from the generated/stylized perspective):\n"
        for idx, frame in enumerate(storyboard_frames, start=1):
            storyboard_block += f"{idx}. {frame}\n"

    extra_rules = ""
    if ignore_real_beats:
        extra_rules = (
            "- Do NOT reconstruct real clip beats or camera angles.\n"
            "- Generate reactionary studio/cutaway beats loosely inspired by the clip.\n"
            "- Every frame must be inside a studio set (desk, analysts, studio lighting).\n"
            "- The play is discussed, not depicted; no on-court action framing.\n"
        )

    if ignore_real_beats:
        base_rules = (
            "- Keep it studio-focused and analyst-driven.\n"
            "- Use the description as the topic being analyzed, not an action to depict.\n"
            "- Include studio set elements (desk, analysts, studio lighting, monitors without text) in most frames.\n"
        )
    else:
        base_rules = (
            "- Keep it football-focused and coherent.\n"
            "- Use the description as the [X action] to depict.\n"
        )

    instruction = (
        "You are a prompt-writer for a sequential image generation pipeline.\n"
        "You will produce 6 sequential keyframe prompts plus 1 overall video prompt, plus a short segment script.\n"
        "The keyframe prompts are used to generate images 1→6 in order; only the first is text-to-image.\n"
        "Prompts MUST describe the generated/stylized scene perspective, not the real broadcast camera.\n"
        "Return ONLY valid JSON with keys: frame_prompts, video_prompt, i2i_prompt_prefix, segment_script.\n"
        "Follow this reference style guide:\n"
        f"{reference}\n\n"
        "Scene details:\n"
        f"- clip_type: {clip_type}\n"
        f"- description: {description}\n"
        f"- context: {context}\n"
        f"- players: {players}\n\n"
        f"{physical_block}\n"
        f"{storyboard_block}\n"
        "Rules:\n"
        f"{base_rules}"
        "- Keyframe prompts should be sequential and cinematic (frame 1 → frame 6).\n"
        "- Frame 1 should emphasize a clear angle where the star player's face is visible.\n"
        "- Include distinct physical attributes (body build, muscularity, skin tone, hair).\n"
        f"{extra_rules}"
        "- The video prompt should describe the full dramatic stylized scene.\n"
        "- The segment_script should be a punchy 1-3 sentence voiceover script (20-50 words) that matches the chosen style.\n"
        "- The segment_script must NOT request any on-screen text, logos, watermarks, or split panels.\n"
        "- The i2i_prompt_prefix should instruct the model to blend style continuity\n"
        "  from a previous generated frame with composition from a reference frame,\n"
        "  producing a single unified image with no split panels, and ensure the\n"
        "  next image is the logical successor to the previous frame."
    )

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    try:
        response = _generate_with_retry(
            client,
            contents=instruction,
            config_data={
                "response_mime_type": "application/json",
                "response_json_schema": PROMPT_SCHEMA,
                "temperature": 0.2,
            },
        )
        raw = response.text or ""
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("Prompt writer did not return JSON object")
        frame_prompts = parsed.get("frame_prompts")
        video_prompt = str(parsed.get("video_prompt", "")).strip()
        i2i_prompt_prefix = str(parsed.get("i2i_prompt_prefix", "")).strip()
        segment_script = str(parsed.get("segment_script", "")).strip()
        if not isinstance(frame_prompts, list) or len(frame_prompts) != 6:
            raise ValueError("Prompt writer did not return 6 frame prompts")
        frame_prompts = [str(item).strip() for item in frame_prompts]
        if not all(frame_prompts) or not video_prompt or not i2i_prompt_prefix:
            raise ValueError("Prompt writer returned empty prompts")
        if not segment_script:
            # Keep the pipeline robust even if the model omits this field.
            # This will still get injected into the Grok prompt as "voiceover".
            segment_script = (
                f"Let’s break down what just happened: {description}. "
                f"Context: {context}."
            ).strip()
        return {
            "_prompt_writer_input": instruction,
            "frame_prompts": frame_prompts,
            "video_prompt": video_prompt,
            "i2i_prompt_prefix": i2i_prompt_prefix,
            "segment_script": segment_script,
        }
    except Exception:
        logger.exception("prompt_writer_failed job_id=%s clip_id=%s", job_id, clip.get("clip_id"))
        return None
    finally:
        client.close()
