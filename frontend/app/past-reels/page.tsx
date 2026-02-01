"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { listJobs, withResolvedUrls } from "../../lib/api";
import type { JobStatus } from "../../lib/types";

export default function PastReelsPage() {
  const [jobs, setJobs] = useState<JobStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const run = async () => {
      setError(null);
      setIsLoading(true);
      try {
        const data = await listJobs();
        if (!active) return;
        setJobs(data.map((j) => withResolvedUrls(j)));
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Failed to load jobs.");
        setJobs([]);
      } finally {
        if (!active) return;
        setIsLoading(false);
      }
    };
    run();
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="container stack">
      <div className="row">
        <Link className="button secondary" href="/">
          Back
        </Link>
        <h1 className="title">Past reels</h1>
        {jobs && <span className="badge">{jobs.length} jobs</span>}
      </div>

      {isLoading && <p className="subtitle">Loading past reels…</p>}
      {error && <p className="status error">{error}</p>}

      {jobs && !isLoading && !error && jobs.length === 0 && (
        <div className="card stack">
          <p className="subtitle">No past jobs found yet.</p>
        </div>
      )}

      {jobs && jobs.length > 0 && (
        <div className="stack">
          {jobs.map((job) => (
            <details key={job.job_id} className="card stack">
              <summary className="row" style={{ cursor: "pointer" }}>
                <span className="badge">{job.status}</span>
                <strong>{job.job_id}</strong>
                {job.original_filename && (
                  <span className="subtitle">{job.original_filename}</span>
                )}
                {typeof job.created_at === "number" && (
                  <span className="subtitle">
                    {new Date(job.created_at * 1000).toLocaleString()}
                  </span>
                )}
              </summary>

              {job.outputs && job.outputs.length > 0 ? (
                <div className="stack">
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
              ) : (
                <p className="subtitle">No reels available for this job yet.</p>
              )}
            </details>
          ))}
        </div>
      )}
    </div>
  );
}

