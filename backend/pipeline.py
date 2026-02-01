import asyncio
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List

import asset_extraction
import clip_detection
import config
import format_selection
import generation
import job_store
import postprocessing
import prompt_writer
import reference_frame
import video_analysis

logger = logging.getLogger("whos-clip-is-it")
DEBUG_LOG_PATH = "/Users/lucasliao/Documents/GitHub/gemini-3-superhack/.cursor/debug.log"


def _debug_log(
    *,
    hypothesis_id: str,
    location: str,
    message: str,
    data: Dict[str, Any],
    run_id: str = "run2",
) -> None:
    payload = {
        "sessionId": "debug-session",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
    except Exception:
        pass

def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # region agent log
    _debug_log(
        hypothesis_id="H1",
        location="backend/pipeline.py:_write_json:pre",
        message="write_json_pre",
        data={
            "path": str(path),
            "data_type": type(data).__name__,
            "has_clips_key": isinstance(data, dict) and "clips" in data,
        },
    )
    # endregion agent log
    path.write_text(json.dumps(data, indent=2, default=_json_default))
    # region agent log
    _debug_log(
        hypothesis_id="H1",
        location="backend/pipeline.py:_write_json:post",
        message="write_json_post",
        data={"path": str(path)},
    )
    # endregion agent log


def _demo_assets(input_path: Path, output_dir: Path) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    clip_path = output_dir / "clip.mp4"
    shutil.copyfile(input_path, clip_path)
    return {"clip_path": clip_path}


def _sanitize_clips(job_id: str, clips: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sanitized: List[Dict[str, Any]] = []
    # region agent log
    _debug_log(
        hypothesis_id="H5",
        location="backend/pipeline.py:_sanitize_clips:entry",
        message="sanitize_entry",
        data={"job_id": job_id, "clip_count": len(clips)},
    )
    # endregion agent log
    for clip in clips:
        clip_copy = dict(clip)
        assets = clip_copy.get("assets") or {}
        safe_assets: Dict[str, str] = {}
        clip_id = clip_copy.get("clip_id")
        if clip_id:
            frame_path = assets.get("frame_path")
            if frame_path and Path(frame_path).exists():
                safe_assets["frame_url"] = (
                    f"/api/jobs/{job_id}/outputs/assets/{clip_id}/{Path(frame_path).name}"
                )
            frame_paths = assets.get("frame_paths")
            if isinstance(frame_paths, list):
                frame_urls = []
                for path in frame_paths:
                    if path and Path(path).exists():
                        frame_urls.append(
                            f"/api/jobs/{job_id}/outputs/assets/{clip_id}/{Path(path).name}"
                        )
                if frame_urls:
                    safe_assets["frame_urls"] = frame_urls
            ref_frame_path = assets.get("ref_frame_path")
            if ref_frame_path and Path(ref_frame_path).exists():
                safe_assets["ref_frame_url"] = (
                    f"/api/jobs/{job_id}/outputs/assets/{clip_id}/{Path(ref_frame_path).name}"
                )
            generated_frame_paths = assets.get("generated_frame_paths")
            if isinstance(generated_frame_paths, list):
                generated_urls = []
                for path in generated_frame_paths:
                    if path and Path(path).exists():
                        generated_urls.append(
                            f"/api/jobs/{job_id}/outputs/assets/{clip_id}/{Path(path).name}"
                        )
                if generated_urls:
                    safe_assets["generated_frame_urls"] = generated_urls
            clip_path = assets.get("clip_path")
            if clip_path and Path(clip_path).exists():
                safe_assets["clip_url"] = f"/api/jobs/{job_id}/outputs/assets/{clip_id}/clip.mp4"
            audio_path = assets.get("audio_path")
            if audio_path and Path(audio_path).exists():
                safe_assets["audio_url"] = f"/api/jobs/{job_id}/outputs/assets/{clip_id}/audio.wav"
        # region agent log
        _debug_log(
            hypothesis_id="H5",
            location="backend/pipeline.py:_sanitize_clips:per_clip",
            message="sanitize_clip_assets",
            data={
                "clip_id": clip_id,
                "has_frame_path": bool(assets.get("frame_path")),
                "has_clip_path": bool(assets.get("clip_path")),
                "frame_url": safe_assets.get("frame_url"),
                "clip_url": safe_assets.get("clip_url"),
            },
        )
        # endregion agent log
        if safe_assets:
            clip_copy["assets"] = safe_assets
        sanitized.append(clip_copy)
    # region agent log
    _debug_log(
        hypothesis_id="H5",
        location="backend/pipeline.py:_sanitize_clips:exit",
        message="sanitize_exit",
        data={"job_id": job_id, "sanitized_count": len(sanitized)},
    )
    # endregion agent log
    return sanitized


async def run_pipeline(job_id: str, input_path: Path) -> None:
    start_time = time.time()
    try:
        print(f"stage_start job_id={job_id} stage=analyzing")
        job_store.update_job(
            job_id,
            status="running",
            stage="analyzing",
            progress=5,
            message="Uploading to Gemini...",
        )

        analysis = await video_analysis.analyze_video(input_path)
        job_dir = job_store.job_dir(job_id)
        _write_json(job_dir / "analysis.json", analysis)
        print(
            "stage_end "
            f"job_id={job_id} stage=analyzing duration_ms={int((time.time() - start_time) * 1000)}"
        )

        duration_ms = None
        try:
            duration_ms = asset_extraction.probe_duration_ms(input_path)
        except Exception:
            duration_ms = None

        raw_clips = clip_detection.extract_raw_clips(analysis)
        clips = clip_detection.normalize_clips(raw_clips, duration_ms)
        if not clips:
            raise RuntimeError("No clips detected")
        print(f"clips_detected job_id={job_id} count={len(clips)}")

        for idx, clip in enumerate(clips, start=1):
            clip["clip_id"] = f"clip_{idx}"

        _write_json(job_dir / "clips.json", clips)

        job_store.update_job(
            job_id,
            stage="selecting_formats",
            progress=22,
            message="Selecting reel formats...",
        )
        print(f"stage_start job_id={job_id} stage=selecting_formats")

        formats = format_selection.load_formats()
        formats_by_id = {int(f["id"]): f for f in formats}
        clips = format_selection.assign_format_ids(clips, formats_by_id)
        job_store.update_job(job_id, clips=_sanitize_clips(job_id, clips))
        print(
            "formats_selected "
            f"job_id={job_id} format_ids={[clip.get('format_id') for clip in clips]}"
        )

        job_store.update_job(
            job_id,
            stage="extracting",
            progress=25,
            message="Extracting clip assets...",
            clips=_sanitize_clips(job_id, clips),
        )
        print(f"stage_start job_id={job_id} stage=extracting")

        for clip in clips:
            assets_dir = job_dir / "assets" / clip["clip_id"]
            format_id = int(clip.get("format_id", 0) or 0)
            format_data = formats_by_id.get(format_id, {})
            if format_data.get("skip_asset_extraction"):
                assets = {}
            elif config.DEMO_MODE:
                assets = _demo_assets(input_path, assets_dir)
            else:
                assets = asset_extraction.extract_assets(input_path, clip, assets_dir)
            clip["assets"] = assets
            job_store.update_job(
                job_id,
                message=f"Extracting {clip['clip_id']} assets...",
                progress=min(55, 25 + int(30 * (int(clip['clip_id'].split('_')[-1]) / len(clips)))),
            )

        job_store.update_job(
            job_id,
            stage="writing_prompts",
            progress=63,
            message="Writing prompts...",
        )
        print(f"stage_start job_id={job_id} stage=writing_prompts")
        for idx, clip in enumerate(clips, start=1):
            format_id = int(clip.get("format_id", 1))
            format_data = formats_by_id.get(format_id, {})
            prompts = prompt_writer.write_prompts(
                job_id=job_id,
                clip=clip,
                format_data=format_data,
            )
            if prompts:
                clip["prompts"] = prompts
            job_store.update_job(
                job_id,
                message=f"Writing {clip['clip_id']} prompts...",
                progress=min(64, 63 + int(1 * (idx / len(clips)))),
            )
        job_store.update_job(job_id, clips=_sanitize_clips(job_id, clips))
        # region agent log
        clip_asset_types = []
        for clip in clips:
            assets = clip.get("assets") or {}
            clip_asset_types.append(
                {
                    "clip_id": clip.get("clip_id"),
                    "asset_value_types": {k: type(v).__name__ for k, v in assets.items()},
                }
            )
        _debug_log(
            hypothesis_id="H2",
            location="backend/pipeline.py:run_pipeline:pre_prompts_write",
            message="pre_write_prompts_json",
            data={
                "clip_count": len(clips),
                "asset_types": clip_asset_types,
            },
        )
        # endregion agent log
        _write_json(job_dir / "prompts.json", {"clips": clips})

        job_store.update_job(
            job_id,
            stage="ref_frames",
            progress=65,
            message="Generating keyframes...",
        )
        print(f"stage_start job_id={job_id} stage=ref_frames")

        for idx, clip in enumerate(clips, start=1):
            generated_paths = reference_frame.generate_keyframes(
                job_id, clip, formats_by_id
            )
            if generated_paths:
                assets = clip.get("assets") or {}
                assets["generated_frame_paths"] = generated_paths
                assets["ref_frame_path"] = generated_paths[0]
                clip["assets"] = assets
            job_store.update_job(
                job_id,
                message=f"Generating {clip['clip_id']} keyframes...",
                progress=min(69, 65 + int(5 * (idx / len(clips)))),
            )
        job_store.update_job(job_id, clips=_sanitize_clips(job_id, clips))

        job_store.update_job(
            job_id,
            stage="generating",
            progress=70,
            message="Generating reels...",
        )
        print(f"stage_start job_id={job_id} stage=generating")

        generated = await generation.generate_reels(job_id, clips, formats_by_id)
        print(f"stage_end job_id={job_id} stage=generating generated={len(generated)}")
        fal_debug = [
            {
                "clip_id": item.get("clip_id"),
                "format_id": item.get("format_id"),
                "fal_debug": item.get("fal_debug"),
            }
            for item in generated
        ]
        job_store.update_job(job_id, fal_debug=fal_debug)

        job_store.update_job(
            job_id,
            stage="postprocessing",
            progress=92,
            message="Post-processing reels...",
        )
        print(f"stage_start job_id={job_id} stage=postprocessing")

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
        print(
            "pipeline_complete "
            f"job_id={job_id} outputs={len(public_outputs)} "
            f"duration_ms={int((time.time() - start_time) * 1000)}"
        )
    except Exception as exc:
        logger.exception("pipeline_failed job_id=%s error=%s", job_id, exc)
        job_store.update_job(
            job_id,
            status="failed",
            stage="done",
            progress=100,
            error={"message": str(exc)},
            message="Pipeline failed",
        )
