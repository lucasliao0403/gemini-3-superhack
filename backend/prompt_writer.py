import json
import logging
from typing import Any, Dict, List, Optional

import config

try:
    from google import genai
except ImportError:  # pragma: no cover - optional until deps installed
    genai = None

logger = logging.getLogger("whos-clip-is-it")

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
    },
}


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
    description = str(clip.get("description", "")).strip()
    context = str(clip.get("context", "")).strip()
    players = ", ".join(clip.get("players", []) or [])
    clip_type = str(clip.get("type", "")).strip()

    storyboard_frames = clip.get("generated_storyboard_frames") or []
    storyboard_block = ""
    if isinstance(storyboard_frames, list) and storyboard_frames:
        storyboard_block = "Generated storyboard beats (from the generated/anime perspective):\n"
        for idx, frame in enumerate(storyboard_frames, start=1):
            storyboard_block += f"{idx}. {frame}\n"

    instruction = (
        "You are a prompt-writer for a sequential image generation pipeline.\n"
        "You will produce 6 sequential keyframe prompts plus 1 overall video prompt.\n"
        "The keyframe prompts are used to generate images 1→6 in order; only the first is text-to-image.\n"
        "Prompts MUST describe the generated/anime scene perspective, not the real broadcast camera.\n"
        "Return ONLY valid JSON with keys: frame_prompts, video_prompt, i2i_prompt_prefix.\n"
        "Follow this reference style guide:\n"
        f"{reference}\n\n"
        "Scene details:\n"
        f"- clip_type: {clip_type}\n"
        f"- description: {description}\n"
        f"- context: {context}\n"
        f"- players: {players}\n\n"
        f"{storyboard_block}\n"
        "Rules:\n"
        "- No real names, teams, logos, or brands. Use generic labels only.\n"
        "- Keep it football-focused and coherent.\n"
        "- Use the description as the [X action] to depict.\n"
        "- Keyframe prompts should be sequential and cinematic (frame 1 → frame 6).\n"
        "- Frame 1 should emphasize a clear angle where the star player's face is visible.\n"
        "- The video prompt should describe the full dramatic anime scene.\n"
        "- The i2i_prompt_prefix should instruct the model to blend style continuity\n"
        "  from a previous generated frame with composition from a reference frame,\n"
        "  producing a single unified image with no split panels."
    )

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    try:
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=instruction,
            config={
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
        if not isinstance(frame_prompts, list) or len(frame_prompts) != 6:
            raise ValueError("Prompt writer did not return 6 frame prompts")
        frame_prompts = [str(item).strip() for item in frame_prompts]
        if not all(frame_prompts) or not video_prompt or not i2i_prompt_prefix:
            raise ValueError("Prompt writer returned empty prompts")
        return {
            "frame_prompts": frame_prompts,
            "video_prompt": video_prompt,
            "i2i_prompt_prefix": i2i_prompt_prefix,
        }
    except Exception:
        logger.exception("prompt_writer_failed job_id=%s clip_id=%s", job_id, clip.get("clip_id"))
        return None
    finally:
        client.close()
