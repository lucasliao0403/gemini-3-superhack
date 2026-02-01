import type { JobStatus } from "@/lib/types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "1";
const DEMO_JOB_ID =
  process.env.NEXT_PUBLIC_DEMO_JOB_ID || "ed9ed4aa83dd4e599ee9922f349f1fe6";

export const isDemoMode = () => DEMO_MODE;
export const getDemoJobId = () => DEMO_JOB_ID;

export const formatBytes = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  return `${mb.toFixed(1)} MB`;
};

const resolveUrl = (path?: string | null) => {
  if (!path) return null;
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  const prefix = path.startsWith("/") ? "" : "/";
  return `${API_BASE_URL}${prefix}${path}`;
};

const resolveUrlList = (paths?: string[] | null) => {
  if (!paths || paths.length === 0) return [];
  return paths.map((path) => resolveUrl(path) || path);
};

export const withResolvedUrls = (job: JobStatus): JobStatus => {
  const outputs = job.outputs?.map((output) => ({
    ...output,
    video_url: resolveUrl(output.video_url) || output.video_url,
    poster_url: resolveUrl(output.poster_url) || output.poster_url,
  }));
  const clips = job.clips?.map((clip) => {
    if (!clip.assets) return clip;
    return {
      ...clip,
      assets: {
        ...clip.assets,
        frame_url: resolveUrl(clip.assets.frame_url) || clip.assets.frame_url,
        frame_urls: resolveUrlList(clip.assets.frame_urls),
        ref_frame_url:
          resolveUrl(clip.assets.ref_frame_url) || clip.assets.ref_frame_url,
        generated_frame_urls: resolveUrlList(clip.assets.generated_frame_urls),
        clip_url: resolveUrl(clip.assets.clip_url) || clip.assets.clip_url,
        audio_url: resolveUrl(clip.assets.audio_url) || clip.assets.audio_url,
      },
    };
  });
  // #region agent log
  fetch('http://127.0.0.1:7244/ingest/0d447818-e4a9-460e-8059-568a79d8680e',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'frontend/lib/api.ts:withResolvedUrls',message:'resolved_job_assets',data:{jobId:job.job_id,clipCount:job.clips?.length ?? 0,firstClipAssets:clips?.[0]?.assets ?? null},timestamp:Date.now(),sessionId:'debug-session',runId:'run2',hypothesisId:'H6'})}).catch(()=>{});
  // #endregion
  if (!outputs && !clips) return job;
  return { ...job, outputs: outputs ?? job.outputs, clips: clips ?? job.clips };
};

export async function createJob(file: File): Promise<{ job_id: string }> {
  if (DEMO_MODE) {
    return { job_id: DEMO_JOB_ID };
  }

  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/api/jobs`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to create job.");
  }
  return response.json();
}

export async function fetchJob(
  jobId: string,
  forceDemo = false
): Promise<JobStatus> {
  if (DEMO_MODE || forceDemo) {
    const response = await fetch("/demo/results.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error("Failed to load demo results.");
    }
    return response.json();
  }

  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to load job.");
  }
  return response.json();
}
