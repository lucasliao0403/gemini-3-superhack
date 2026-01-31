import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List

import config

try:
    from google import genai
    from google.genai import errors as genai_errors
except ImportError:  # pragma: no cover - optional until deps installed
    genai = None
    genai_errors = None


logger = logging.getLogger("whos-clip-is-it")
MAX_GEMINI_OVERLOAD_RETRIES = 10
RETRYABLE_OVERLOAD_STATUS = 503

CLIP_JSON_SCHEMA: Dict[str, Any] = {
    "type": "array",
    "minItems": 2,
    "maxItems": 5,
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "start",
            "peak",
            "end",
            "type",
            "description",
            "players",
            "context",
            "announcer_energy",
            "crowd_energy",
        ],
        "properties": {
            "start": {"type": "string", "description": "Start timestamp MM:SS"},
            "peak": {"type": "string", "description": "Peak timestamp MM:SS"},
            "end": {"type": "string", "description": "End timestamp MM:SS"},
            "type": {
                "type": "string",
                "enum": [
                    "big_play",
                    "fail",
                    "reaction",
                    "controversial",
                    "clutch",
                    "funny",
                ],
            },
            "description": {"type": "string"},
            "players": {"type": "array", "items": {"type": "string"}},
            "context": {"type": "string"},
            "announcer_energy": {"type": "integer", "minimum": 1, "maximum": 10},
            "crowd_energy": {"type": "integer", "minimum": 1, "maximum": 10},
        },
    },
}


def _load_clip_detection_prompt() -> str:
    prompt_path = config.PROMPTS_DIR / "prompts.json"
    if not prompt_path.exists():
        return ""
    data = json.loads(prompt_path.read_text())
    return data.get("clip_detection", "")


def _mock_analysis() -> List[Dict[str, Any]]:
    return [
        {
            "start": "02:34",
            "peak": "02:41",
            "end": "02:47",
            "type": "big_play",
            "description": "Explosive touchdown after a broken tackle",
            "players": ["Player A"],
            "context": "Gives the team a late lead in the 4th quarter",
            "announcer_energy": 9,
            "crowd_energy": 9,
        },
        {
            "start": "08:12",
            "peak": "08:18",
            "end": "08:25",
            "type": "fail",
            "description": "Quarterback throws a costly interception",
            "players": ["Player B"],
            "context": "Momentum swing after a promising drive",
            "announcer_energy": 7,
            "crowd_energy": 6,
        },
    ]


def _thinking_level() -> str:
    level = (config.GEMINI_REASONING or "medium").lower()
    if level not in {"minimal", "low", "medium", "high"}:
        return "medium"
    return level


def _parse_response(raw_text: str) -> List[Dict[str, Any]]:
    parsed = json.loads(raw_text)
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict) and isinstance(parsed.get("clips"), list):
        return parsed["clips"]
    raise ValueError("Gemini response did not contain a clip array")


def _is_overloaded_error(exc: Exception) -> bool:
    if genai_errors and isinstance(exc, genai_errors.ServerError):
        status_code = getattr(exc, "status_code", None)
        if status_code == RETRYABLE_OVERLOAD_STATUS:
            return True
    message = str(exc).lower()
    return "503" in message and "overloaded" in message


def _generate_with_retry(client: Any, *, contents: List[Any], config_data: Dict[str, Any]) -> Any:
    for attempt in range(1, MAX_GEMINI_OVERLOAD_RETRIES + 1):
        try:
            return client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=contents,
                config=config_data,
            )
        except Exception as exc:
            if not _is_overloaded_error(exc) or attempt == MAX_GEMINI_OVERLOAD_RETRIES:
                raise
            backoff_s = min(2 ** (attempt - 1), 10)
            logger.warning(
                "gemini_overloaded retrying attempt=%s backoff_s=%s",
                attempt,
                backoff_s,
            )
            time.sleep(backoff_s)


def _call_gemini_sync(input_path: Path, prompt: str) -> Dict[str, Any]:
    if genai is None:
        raise RuntimeError("google-genai is not installed")

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    try:
        print(
            "gemini_upload_start "
            f"model={config.GEMINI_MODEL} reasoning={_thinking_level()}"
        )
        uploaded = client.files.upload(file=str(input_path))

        name = getattr(uploaded, "name", None)
        if name:
            deadline = time.time() + 120
            while time.time() < deadline:
                current = client.files.get(name=name)
                raw_state = getattr(current, "state", "")
                if hasattr(raw_state, "name"):
                    state = raw_state.name
                else:
                    state = str(raw_state)
                state = state.upper()
                print(f"gemini_upload_state name={name} state={state}")
                if "ACTIVE" in state:
                    uploaded = current
                    break
                if "FAILED" in state:
                    raise RuntimeError("Gemini file processing failed")
                time.sleep(1.5)
        base_config: Dict[str, Any] = {
            "response_mime_type": "application/json",
            "response_json_schema": CLIP_JSON_SCHEMA,
            "thinking_config": {"thinking_level": _thinking_level()},
            "temperature": 0.2,
        }
        response = _generate_with_retry(
            client,
            contents=[uploaded, prompt],
            config_data=base_config,
        )
        try:
            clips = _parse_response(response.text or "")
        except Exception:
            logger.warning("gemini_response_invalid_json retrying")
            repair_prompt = (
                f"{prompt}\n\n"
                "Return ONLY a valid JSON array matching the schema. "
                "No markdown, no extra keys."
            )
            retry = _generate_with_retry(
                client,
                contents=[uploaded, repair_prompt],
                config_data=base_config,
            )
            clips = _parse_response(retry.text or "")
    finally:
        client.close()

    print(f"gemini_response_parsed clips={len(clips)}")
    return {"prompt_used": bool(prompt), "clips": clips}


async def analyze_video(input_path: Path) -> Dict[str, Any]:
    prompt = _load_clip_detection_prompt()
    if config.DEMO_MODE or not config.GEMINI_API_KEY:
        return {"prompt_used": bool(prompt), "clips": _mock_analysis()}
    return await asyncio.to_thread(_call_gemini_sync, input_path, prompt)
