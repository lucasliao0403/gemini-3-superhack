import json
import logging
from typing import Any, Dict, Optional

import config

try:
    from google import genai
except ImportError:  # pragma: no cover - optional until deps installed
    genai = None

logger = logging.getLogger("whos-clip-is-it")

PROMPT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["image_prompt", "video_prompt"],
    "properties": {
        "image_prompt": {"type": "string"},
        "video_prompt": {"type": "string"},
    },
}


def write_prompts(
    *,
    job_id: str,
    clip: Dict[str, Any],
    format_data: Dict[str, Any],
) -> Optional[Dict[str, str]]:
    if config.DEMO_MODE or not config.GEMINI_API_KEY:
        return None
    if genai is None:
        raise RuntimeError("google-genai is not installed")

    reference = str(format_data.get("prompt_reference", "")).strip()
    description = str(clip.get("description", "")).strip()
    context = str(clip.get("context", "")).strip()
    players = ", ".join(clip.get("players", []) or [])
    clip_type = str(clip.get("type", "")).strip()

    instruction = (
        "You are a prompt-writer for two generation steps.\n"
        "Step 1 is for an image model (Nano Banana). Step 2 is for a video model (FAL v2v).\n"
        "Return ONLY valid JSON with keys: image_prompt, video_prompt.\n"
        "Follow this reference style guide:\n"
        f"{reference}\n\n"
        "Scene details:\n"
        f"- clip_type: {clip_type}\n"
        f"- description: {description}\n"
        f"- context: {context}\n"
        f"- players: {players}\n\n"
        "Rules:\n"
        "- No real names, teams, logos, or brands. Use generic labels only.\n"
        "- Keep it football-focused and coherent.\n"
        "- Use the description as the [X action] to depict.\n"
        "- The image prompt should emphasize a clear angle where the star player's face is visible.\n"
        "- The video prompt should describe the full dramatic anime scene."
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
        image_prompt = str(parsed.get("image_prompt", "")).strip()
        video_prompt = str(parsed.get("video_prompt", "")).strip()
        if not image_prompt or not video_prompt:
            raise ValueError("Prompt writer returned empty prompts")
        return {"image_prompt": image_prompt, "video_prompt": video_prompt}
    except Exception:
        logger.exception("prompt_writer_failed job_id=%s clip_id=%s", job_id, clip.get("clip_id"))
        return None
    finally:
        client.close()
