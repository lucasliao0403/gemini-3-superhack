# Who's Clip Is It?

AI-powered sports highlight -> brainrot reels generator (monorepo).

## Repo layout
- `frontend/` Next.js app (upload/progress/results UI)
- `backend/` FastAPI app (async jobs + pipeline)
- `prompts/` prompt templates and format templates
- `assets/` placeholder media (SFX/music/overlays)
- `temp/` local scratch (uploads/outputs, gitignored)

## Local setup
### Frontend
1. `cd frontend`
2. `npm install`
3. `npm run dev`

### Backend
1. `cd backend`
2. Create a virtualenv and install deps:
   - `python -m venv .venv`
   - `. .venv/bin/activate`
   - `pip install -e .`
3. `uvicorn main:app --reload --host 0.0.0.0 --port 8000`

## Environment
Backend `.env` (optional):
- `GEMINI_API_KEY` (clip detection + prompt writing)
- `FAL_KEY` (video generation)
- `FAL_DEFAULT_MODEL` (default `xai/grok-imagine-video/edit-video`)
- `FAL_ASPECT_RATIO` (default `9:16`)
- `FAL_RESOLUTION` (default `720p`)
- `FAL_FPS` (default `16`)
- `FAL_MAX_CONCURRENCY` (default `1`)
- `FAL_NANO_BANANA_MODEL` (default `fal-ai/nano-banana`)
- `FAL_NANO_BANANA_EDIT_MODEL` (default `fal-ai/nano-banana/edit`)
- `FAL_NANO_BANANA_ASPECT_RATIO` (default `9:16`)
- `FFMPEG_PATH` (default `ffmpeg`)
- `DEMO_MODE=1` to bypass real pipeline

Frontend `.env.local` (optional):
- `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`)
- `NEXT_PUBLIC_DEMO_MODE=1` to use frontend demo assets

## Notes
- MP4 only, <100MB only.
- Pipeline overview: upload mp4 -> Gemini clip detection/prompts -> extract clip mp4s
  -> Grok Imagine video-to-video generates reels.
- Supported `input_mode` values: `prompt_only`, `image_plus_prompt`, `video_plus_prompt`.
- Formats that specify `audio_plus_prompt` or `image_plus_prompt` fall back to
  video-to-video using the extracted clip mp4 when available.
- We could add a layer between format selection and generation that expands a
  format-level template into a scene-specific prompt before sending it to FAL,
  instead of relying on mostly hard-coded prompt templates.
- Demo mode is intended for local UI development without API keys.

## Testing checklist
- With `GEMINI_API_KEY` and `FAL_KEY` set, run a full job and confirm logs show
  FAL generation completion, postprocessing, and job completion.
- Load the job page and verify each detected clip shows the frame image beside
  the extracted clip video.
- Confirm reel outputs are FAL-generated mp4s (not copied clips).
