import json
import time
from pathlib import Path
import tempfile
from typing import Any, Dict

import config


JOB_FILENAME = "job.json"


def job_dir(job_id: str) -> Path:
    return config.JOBS_DIR / job_id


def job_file(job_id: str) -> Path:
    return job_dir(job_id) / JOB_FILENAME


def job_input_path(job_id: str) -> Path:
    return job_dir(job_id) / "input.mp4"


def safe_job_path(job_id: str, rel_path: str) -> Path:
    base = job_dir(job_id).resolve()
    candidate = (base / rel_path).resolve()
    if base not in candidate.parents and candidate != base:
        raise ValueError("Invalid output path")
    return candidate


def create_job(job_id: str, original_filename: str) -> Dict[str, Any]:
    config.ensure_base_dirs()
    job_dir(job_id).mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    job = {
        "job_id": job_id,
        "status": "queued",
        "stage": "upload",
        "progress": 0,
        "message": "Upload received",
        "created_at": now,
        "updated_at": now,
        "original_filename": original_filename,
        "clips": [],
        "outputs": [],
        "error": None,
    }
    write_job(job_id, job)
    return job


def load_job(job_id: str) -> Dict[str, Any]:
    path = job_file(job_id)
    if not path.exists():
        raise FileNotFoundError(job_id)
    return json.loads(path.read_text())


def write_job(job_id: str, job: Dict[str, Any]) -> None:
    job["updated_at"] = int(time.time())
    # Atomic write to avoid partially-written JSON being read by `/api/jobs/{job_id}`.
    path = job_file(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(job, indent=2)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        delete=False,
        prefix=path.name + ".",
        suffix=".tmp",
    ) as handle:
        handle.write(payload)
        tmp_path = Path(handle.name)
    tmp_path.replace(path)


def update_job(job_id: str, **fields: Any) -> Dict[str, Any]:
    job = load_job(job_id)
    job.update(fields)
    write_job(job_id, job)
    return job
