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
- `FAL_KEY`
- `FFMPEG_PATH` (default `ffmpeg`)
- `DEMO_MODE=1` to bypass real pipeline

Frontend `.env.local` (optional):
- `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`)
- `NEXT_PUBLIC_DEMO_MODE=1` to use frontend demo assets

## Notes
- MP4 only, <100MB only.
- Demo mode is intended for local UI development without API keys.
