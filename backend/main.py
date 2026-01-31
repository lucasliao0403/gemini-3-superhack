import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import config
import job_store
import pipeline


LOG_FORMAT = "%(asctime)s | %(levelname)s | %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("whos-clip-is-it")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _validate_upload(file: UploadFile) -> None:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only .mp4 files are supported")
    if file.content_type not in config.ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid content type")


async def _save_upload(file: UploadFile, dest_path: Path) -> int:
    size = 0
    max_bytes = config.MAX_UPLOAD_MB * 1024 * 1024
    with dest_path.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise HTTPException(status_code=413, detail="File exceeds size limit")
            out.write(chunk)
    return size


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok"}


@app.post("/api/jobs")
async def create_job(file: UploadFile = File(...)) -> dict[str, Any]:
    _validate_upload(file)

    job_id = uuid.uuid4().hex
    logger.info("job_created job_id=%s filename=%s", job_id, file.filename)
    job_store.create_job(job_id, original_filename=file.filename or "upload.mp4")
    input_path = job_store.job_input_path(job_id)
    input_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        size = await _save_upload(file, input_path)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    logger.info("upload_saved job_id=%s bytes=%s path=%s", job_id, size, input_path)

    job_store.update_job(
        job_id,
        stage="queued",
        progress=1,
        message="Queued for processing",
    )

    logger.info("pipeline_start job_id=%s", job_id)
    asyncio.create_task(pipeline.run_pipeline(job_id, input_path))
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    try:
        return job_store.load_job(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")


@app.get("/api/jobs/{job_id}/outputs/{path:path}")
def get_output(job_id: str, path: str) -> FileResponse:
    try:
        output_path = job_store.safe_job_path(job_id, path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not output_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(output_path)
