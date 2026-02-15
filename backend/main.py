import asyncio
import logging
import os
import threading
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

DEMO_JOB_ID = os.getenv("DEMO_JOB_ID", "ed9ed4aa83dd4e599ee9922f349f1fe6")
DEMO_JOB_FALLBACK = os.getenv("DEMO_JOB_FALLBACK", "demo_this")


def _start_pipeline_background(job_id: str, input_path: Path) -> None:
    """
    Run the pipeline off the main server event loop.

    The pipeline currently performs substantial synchronous work (ffmpeg/subprocess,
    file IO, sync SDK calls). Running it as an asyncio task on the main event loop
    can prevent the API from serving requests while a job is generating.
    """

    def _runner() -> None:
        try:
            asyncio.run(pipeline.run_pipeline(job_id, input_path))
        except Exception:
            # `run_pipeline` already catches and records failures, but keep a log
            # in case we fail before its internal try/except executes.
            logger.exception("pipeline_thread_failed job_id=%s", job_id)

    thread = threading.Thread(
        target=_runner, name=f"pipeline-{job_id[:8]}", daemon=True
    )
    thread.start()


def _resolve_job_id(job_id: str) -> str:
    if job_id == DEMO_JOB_ID and not job_store.job_file(job_id).exists():
        if job_store.job_file(DEMO_JOB_FALLBACK).exists():
            return DEMO_JOB_FALLBACK
    return job_id


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
    print(f"job_created job_id={job_id} filename={file.filename}")
    job_store.create_job(job_id, original_filename=file.filename or "upload.mp4")
    input_path = job_store.job_input_path(job_id)
    input_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        size = await _save_upload(file, input_path)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    print(f"upload_saved job_id={job_id} bytes={size} path={input_path}")

    job_store.update_job(
        job_id,
        stage="queued",
        progress=1,
        message="Queued for processing",
    )

    print(f"pipeline_start job_id={job_id}")
    _start_pipeline_background(job_id, input_path)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job_id = _resolve_job_id(job_id)
    try:
        return job_store.load_job(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")


@app.get("/api/jobs/{job_id}/outputs/{path:path}")
def get_output(job_id: str, path: str) -> FileResponse:
    job_id = _resolve_job_id(job_id)
    try:
        output_path = job_store.safe_job_path(job_id, path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not output_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(output_path)


@app.get("/api/jobs")
def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    """
    List stored jobs on disk.

    Jobs are stored under config.JOBS_DIR/<job_id>/job.json.
    """
    try:
        config.ensure_base_dirs()
        job_ids = [
            p.name
            for p in config.JOBS_DIR.iterdir()
            if p.is_dir() and (p / job_store.JOB_FILENAME).exists()
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    jobs: list[dict[str, Any]] = []
    for job_id in job_ids:
        try:
            jobs.append(job_store.load_job(job_id))
        except Exception:
            # Skip malformed/unreadable jobs rather than failing the whole list.
            continue

    jobs.sort(key=lambda j: int(j.get("created_at") or 0), reverse=True)
    if limit > 0:
        jobs = jobs[:limit]
    return jobs
