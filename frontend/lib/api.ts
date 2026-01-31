import type { JobStatus } from "@/lib/types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "1";

export const isDemoMode = () => DEMO_MODE;

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

export const withResolvedUrls = (job: JobStatus): JobStatus => {
  if (!job.outputs) return job;
  const outputs = job.outputs.map((output) => ({
    ...output,
    video_url: resolveUrl(output.video_url) || output.video_url,
    poster_url: resolveUrl(output.poster_url) || output.poster_url,
  }));
  return { ...job, outputs };
};

export async function createJob(file: File): Promise<{ job_id: string }> {
  if (DEMO_MODE) {
    return { job_id: "demo" };
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
