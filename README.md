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
- `GEMINI_API_KEY`
- `VEO_MODEL` (default `veo-3.1-fast-generate-preview`)
- `VEO_ASPECT_RATIO` (default `9:16`)
- `VEO_RESOLUTION` (default `720p`)
- `VEO_MAX_CONCURRENCY` (default `1`)
- `FFMPEG_PATH` (default `ffmpeg`)
- `DEMO_MODE=1` to bypass real pipeline

Frontend `.env.local` (optional):
- `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`)
- `NEXT_PUBLIC_DEMO_MODE=1` to use frontend demo assets

## Notes
- MP4 only, <100MB only.
- Fal AI has been replaced by Veo 3.1 generation (Gemini API).
- Video-to-video generation is not implemented because Veo 3.1 in this workflow
  only supports text-to-video and image-to-video inputs.
- Supported `input_mode` values: `prompt_only`, `image_plus_prompt`.
- Formats that specify `audio_plus_prompt` or `video_plus_prompt` fall back to
  image-to-video when a freeze frame is available, otherwise text-to-video.
- We could add a layer between format selection and generation that expands a
  format-level template into a scene-specific prompt before sending it to Veo,
  instead of relying on mostly hard-coded prompt templates.
- Demo mode is intended for local UI development without API keys.

## Testing checklist
- With `GEMINI_API_KEY` set, run a full job and confirm logs show Veo polling,
  generation completion, postprocessing, and job completion.
- Load the job page and verify each detected clip shows the frame image beside
  the extracted clip video.
- Confirm reel outputs are Veo-generated mp4s (not copied clips).
