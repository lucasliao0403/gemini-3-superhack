import asyncio
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List

import asset_extraction
import clip_detection
import config
import format_selection
import generation
import job_store
import postprocessing
import video_analysis


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _demo_assets(input_path: Path, output_dir: Path) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    clip_path = output_dir / "clip.mp4"
    shutil.copyfile(input_path, clip_path)
    return {"clip_path": clip_path}


def _sanitize_clips(job_id: str, clips: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sanitized: List[Dict[str, Any]] = []
    base_dir = job_store.job_dir(job_id)
    for clip in clips:
        clip_copy = dict(clip)
        assets = clip_copy.get("assets") or {}
        safe_assets = {}
        for key, value in assets.items():
            try:
                safe_assets[key] = str(Path(value).relative_to(base_dir))
            except Exception:
                safe_assets[key] = str(value)
        if safe_assets:
            clip_copy["assets"] = safe_assets
        sanitized.append(clip_copy)
    return sanitized


async def run_pipeline(job_id: str, input_path: Path) -> None:
    try:
        job_store.update_job(
            job_id,
            status="running",
            stage="analyzing",
            progress=5,
            message="Starting pipeline",
        )

        analysis = await video_analysis.analyze_video(input_path)
        job_dir = job_store.job_dir(job_id)
        _write_json(job_dir / "analysis.json", analysis)

        duration_ms = None
        try:
            duration_ms = asset_extraction.probe_duration_ms(input_path)
        except Exception:
            duration_ms = None

        raw_clips = clip_detection.extract_raw_clips(analysis)
        clips = clip_detection.normalize_clips(raw_clips, duration_ms)
        if not clips:
            raise RuntimeError("No clips detected")

        for idx, clip in enumerate(clips, start=1):
            clip["clip_id"] = f"clip_{idx}"

        _write_json(job_dir / "clips.json", clips)
        job_store.update_job(
            job_id,
            stage="extracting",
            progress=20,
            clips=_sanitize_clips(job_id, clips),
        )

        for clip in clips:
            assets_dir = job_dir / "assets" / clip["clip_id"]
            if config.DEMO_MODE:
                assets = _demo_assets(input_path, assets_dir)
            else:
                assets = asset_extraction.extract_assets(input_path, clip, assets_dir)
            clip["assets"] = assets

        job_store.update_job(
            job_id,
            stage="selecting_formats",
            progress=45,
        )

        formats = format_selection.load_formats()
        formats_by_id = {int(f["id"]): f for f in formats}
        clips = format_selection.assign_format_ids(clips, formats_by_id)
        job_store.update_job(job_id, clips=_sanitize_clips(job_id, clips))

        job_store.update_job(
            job_id,
            stage="generating",
            progress=65,
        )

        generated = await generation.generate_reels(job_id, clips, formats_by_id)

        job_store.update_job(
            job_id,
            stage="postprocessing",
            progress=85,
        )

        outputs = postprocessing.postprocess_reels(job_id, clips, formats_by_id, generated)
        public_outputs = []
        for output in outputs:
            rel_path = str(Path(output["final_path"]).relative_to(job_dir))
            poster_rel = None
            if output.get("poster_path"):
                poster_rel = str(Path(output["poster_path"]).relative_to(job_dir))
            public_outputs.append(
                {
                    "id": output["id"],
                    "clip_id": output["clip_id"],
                    "format_id": output["format_id"],
                    "video_url": f"/api/jobs/{job_id}/outputs/{rel_path}",
                    "poster_url": f"/api/jobs/{job_id}/outputs/{poster_rel}" if poster_rel else None,
                    "duration_s": output["duration_s"],
                }
            )

        job_store.update_job(
            job_id,
            status="complete",
            stage="done",
            progress=100,
            outputs=public_outputs,
            message="Complete",
        )
    except Exception as exc:
        job_store.update_job(
            job_id,
            status="failed",
            stage="done",
            progress=100,
            error={"message": str(exc)},
            message="Pipeline failed",
        )
