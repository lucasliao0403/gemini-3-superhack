import asyncio
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List

import config
import job_store

logger = logging.getLogger("whos-clip-is-it")

def _render_prompt(template: str, clip: Dict[str, Any]) -> str:
    return (
        template.replace("{{description}}", str(clip.get("description", "")))
        .replace("{{context}}", str(clip.get("context", "")))
        .replace("{{players}}", ", ".join(clip.get("players", []) or []))
        .strip()
    )


def _mock_generate(clip: Dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_path = output_dir / "generated.mp4"
    source_path = Path(clip.get("assets", {}).get("clip_path", ""))
    if not source_path.exists():
        raise RuntimeError("Missing clip asset for generation")
    shutil.copyfile(source_path, generated_path)
    return generated_path


async def generate_reels(
    job_id: str,
    clips: List[Dict[str, Any]],
    formats_by_id: Dict[int, Dict[str, Any]],
    concurrency: int = 2,
) -> List[Dict[str, Any]]:
    semaphore = asyncio.Semaphore(concurrency)
    results: List[Dict[str, Any]] = []

    async def _run_one(clip: Dict[str, Any]) -> None:
        async with semaphore:
            format_id = int(clip.get("format_id", 1))
            output_dir = job_store.job_dir(job_id) / "reels" / clip["clip_id"] / str(format_id)
            logger.info(
                "generation_start job_id=%s clip_id=%s format_id=%s",
                job_id,
                clip.get("clip_id"),
                format_id,
            )

            if config.DEMO_MODE or not config.FAL_KEY:
                logger.info("generation_mode demo job_id=%s clip_id=%s", job_id, clip.get("clip_id"))
                generated_path = await asyncio.to_thread(_mock_generate, clip, output_dir)
            else:
                format_data = formats_by_id.get(format_id, {})
                _ = _render_prompt(format_data.get("prompt_template", ""), clip)
                raise RuntimeError("Fal integration not implemented. Set DEMO_MODE=1 or add integration.")

            logger.info(
                "generation_done job_id=%s clip_id=%s output=%s",
                job_id,
                clip.get("clip_id"),
                generated_path,
            )
            results.append(
                {
                    "clip_id": clip["clip_id"],
                    "format_id": format_id,
                    "generated_path": generated_path,
                }
            )

    await asyncio.gather(*[_run_one(clip) for clip in clips])
    return results
