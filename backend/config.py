import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional until deps installed
    load_dotenv = None


BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent

if load_dotenv:
    # Prefer backend/.env, then repo-root .env as a fallback.
    load_dotenv(BACKEND_DIR / ".env")
    load_dotenv(BASE_DIR / ".env")
TEMP_DIR = BASE_DIR / "temp"
JOBS_DIR = TEMP_DIR / "jobs"
PROMPTS_DIR = BASE_DIR / "prompts"
ASSETS_DIR = BASE_DIR / "assets"

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))
ALLOWED_EXTENSIONS = {".mp4"}
ALLOWED_CONTENT_TYPES = {"video/mp4"}

DEMO_MODE = os.getenv("DEMO_MODE", "").lower() in {"1", "true", "yes"}
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
GEMINI_REASONING = os.getenv("GEMINI_REASONING", "medium")
NANO_BANANA_MODEL = os.getenv("NANO_BANANA_MODEL", "gemini-2.5-flash-image")
NANO_BANANA_ASPECT_RATIO = os.getenv("NANO_BANANA_ASPECT_RATIO", "9:16")
FAL_KEY = os.getenv("FAL_KEY")
FAL_DEFAULT_MODEL = os.getenv(
    "FAL_DEFAULT_MODEL", "xai/grok-imagine-video/edit-video"
)
FAL_ASPECT_RATIO = os.getenv("FAL_ASPECT_RATIO", "9:16")
FAL_RESOLUTION = os.getenv("FAL_RESOLUTION", "720p")
FAL_FPS = int(os.getenv("FAL_FPS", "16"))
FAL_MAX_CONCURRENCY = int(os.getenv("FAL_MAX_CONCURRENCY", "1"))
FAL_GROK_IMAGE_MODEL = os.getenv("FAL_GROK_IMAGE_MODEL", "xai/grok-imagine-image")
FAL_GROK_IMAGE_EDIT_MODEL = os.getenv(
    "FAL_GROK_IMAGE_EDIT_MODEL",
    "xai/grok-imagine-image/edit",
)
FAL_VIDU_REFERENCE_MODEL = os.getenv(
    "FAL_VIDU_REFERENCE_MODEL",
    "fal-ai/vidu/reference-to-video",
)
FAL_NANO_BANANA_MODEL = os.getenv("FAL_NANO_BANANA_MODEL", "fal-ai/nano-banana")
FAL_NANO_BANANA_EDIT_MODEL = os.getenv(
    "FAL_NANO_BANANA_EDIT_MODEL",
    "fal-ai/nano-banana/edit",
)
FAL_NANO_BANANA_ASPECT_RATIO = os.getenv("FAL_NANO_BANANA_ASPECT_RATIO", "9:16")

FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
FFPROBE_PATH = os.getenv("FFPROBE_PATH", "ffprobe")


def ensure_base_dirs() -> None:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
