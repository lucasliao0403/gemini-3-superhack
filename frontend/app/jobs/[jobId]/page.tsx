"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { fetchJob, isDemoMode, withResolvedUrls } from "@/lib/api";
import type { JobStatus } from "@/lib/types";

const POLL_INTERVAL_MS = 1500;

export default function JobPage() {
  const params = useParams<{ jobId: string }>();
  const jobId = params?.jobId || "";
  const [job, setJob] = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const demoMode = useMemo(
    () => isDemoMode() || jobId === "demo",
    [jobId]
  );

  useEffect(() => {
    if (!jobId) {
      return;
    }
    let active = true;
    let interval: ReturnType<typeof setInterval> | null = null;
    let timeout: ReturnType<typeof setTimeout> | null = null;

    const loadJob = async () => {
      try {
        const data = await fetchJob(jobId, demoMode);
        if (!active) return;
        setJob(withResolvedUrls(data));
        setIsLoading(false);
        if (data.status === "complete" || data.status === "failed") {
          if (interval) clearInterval(interval);
        }
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Failed to load job.");
        setIsLoading(false);
        if (interval) clearInterval(interval);
      }
    };

    if (demoMode) {
      setJob({
        job_id: jobId,
        status: "running",
        stage: "generating",
        progress: 65,
        message: "Generating demo reels",
      });
      timeout = setTimeout(loadJob, 900);
    } else {
      loadJob();
      interval = setInterval(loadJob, POLL_INTERVAL_MS);
    }

    return () => {
      active = false;
      if (interval) clearInterval(interval);
      if (timeout) clearTimeout(timeout);
    };
  }, [jobId, demoMode]);

  const statusClass =
    job?.status === "failed"
      ? "status error"
      : job?.status === "complete"
      ? "status success"
      : "status";

  return (
    <div className="container stack">
      <div className="row">
        <Link className="button secondary" href="/">
          Back to upload
        </Link>
        <span className="badge">Job {jobId || "..."}</span>
      </div>

      <div className="card stack">
        <div className="row">
          <h1 className="title">Processing status</h1>
          {job?.status && <span className={statusClass}>{job.status}</span>}
        </div>
        {isLoading && <p className="subtitle">Loading job details...</p>}
        {error && <p className="status error">{error}</p>}
        {job && !error && (
          <div className="stack">
            <p className="subtitle">{job.message || "Working..."}</p>
            {job.stage && (
              <p className="subtitle">
                Stage: <strong>{job.stage}</strong>
              </p>
            )}
            {typeof job.progress === "number" && (
              <progress
                className="progress"
                value={job.progress}
                max={100}
              />
            )}
          </div>
        )}
      </div>

      {job?.clips && job.clips.length > 0 && (
        <div className="card stack">
          <h2>Detected clips</h2>
          <div className="stack">
            {job.clips.map((clip, index) => (
              <div key={`${clip.clip_id || index}`} className="row">
                <span className="badge">{clip.type}</span>
                <span>{clip.description}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {job?.outputs && job.outputs.length > 0 && (
        <div className="card stack">
          <h2>Reels</h2>
          <div className="grid">
            {job.outputs.map((output) => (
              <div key={output.id} className="stack">
                <video
                  className="video"
                  controls
                  src={output.video_url}
                  poster={output.poster_url || undefined}
                />
                <div className="row">
                  <span className="badge">Format {output.format_id}</span>
                  {output.duration_s && (
                    <span className="subtitle">{output.duration_s}s</span>
                  )}
                </div>
                <a
                  className="button secondary"
                  href={output.video_url}
                  download
                >
                  Download
                </a>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
