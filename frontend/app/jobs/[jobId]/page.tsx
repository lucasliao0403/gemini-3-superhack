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
  const [hasLoggedFal, setHasLoggedFal] = useState(false);

  const demoMode = useMemo(() => isDemoMode(), []);

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

  useEffect(() => {
    if (!hasLoggedFal && job?.fal_debug) {
      console.log("FAL debug", job.fal_debug);
      setHasLoggedFal(true);
    }
  }, [hasLoggedFal, job?.fal_debug]);

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
              <div key={`${clip.clip_id || index}`} className="card stack">
                <div className="row">
                  <span className="badge">{clip.type}</span>
                  {typeof clip.format_id === "number" && (
                    <span className="badge">Format {clip.format_id}</span>
                  )}
                  <span>{clip.description}</span>
                </div>
                {(clip.assets?.frame_urls?.length ||
                  clip.assets?.generated_frame_urls?.length ||
                  clip.assets?.clip_url ||
                  clip.assets?.frame_url ||
                  clip.assets?.ref_frame_url) && (
                  <div className="stack">
                    {clip.assets?.frame_urls?.length ? (
                      <details className="stack">
                        <summary className="subtitle">Freeze frames (6)</summary>
                        <div className="scroll-row">
                          {clip.assets.frame_urls.map((url, idx) => (
                            <img
                              key={`${url}-${idx}`}
                              className="video"
                              src={url}
                              alt={`Freeze frame ${idx + 1} for ${clip.clip_id || "clip"}`}
                            />
                          ))}
                        </div>
                      </details>
                    ) : clip.assets?.frame_url ? (
                      <details className="stack">
                        <summary className="subtitle">Freeze frame</summary>
                        <div className="scroll-row">
                          <img
                            className="video"
                            src={clip.assets.frame_url}
                            alt={`Frame for ${clip.clip_id || "clip"}`}
                          />
                        </div>
                      </details>
                    ) : null}

                    {clip.assets?.generated_frame_urls?.length ? (
                      <details className="stack">
                        <summary className="subtitle">Generated keyframes (6)</summary>
                        <div className="scroll-row">
                          {clip.assets.generated_frame_urls.map((url, idx) => (
                            <img
                              key={`${url}-${idx}`}
                              className="video"
                              src={url}
                              alt={`Generated frame ${idx + 1} for ${clip.clip_id || "clip"}`}
                            />
                          ))}
                        </div>
                      </details>
                    ) : clip.assets?.ref_frame_url ? (
                      <details className="stack">
                        <summary className="subtitle">Generated keyframe</summary>
                        <div className="scroll-row">
                          <img
                            className="video"
                            src={clip.assets.ref_frame_url}
                            alt={`Reference frame for ${clip.clip_id || "clip"}`}
                          />
                        </div>
                      </details>
                    ) : null}

                    {clip.assets?.clip_url && (
                      <div className="stack">
                        <span className="subtitle">Source clip</span>
                        <div className="row">
                          <video
                            className="video"
                            controls
                            src={clip.assets.clip_url}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                )}
                {(clip.prompts?.frame_prompts?.length ||
                  clip.prompts?.image_prompt ||
                  clip.prompts?.video_prompt) && (
                  <div className="stack">
                    {clip.prompts?.frame_prompts?.length ? (
                      <div className="stack">
                        <span className="subtitle">Keyframe prompts</span>
                        <pre className="code">
                          {clip.prompts.frame_prompts
                            .map((prompt, idx) => `#${idx + 1} ${prompt}`)
                            .join("\n")}
                        </pre>
                      </div>
                    ) : clip.prompts?.image_prompt ? (
                      <div className="stack">
                        <span className="subtitle">Image prompt</span>
                        <pre className="code">{clip.prompts.image_prompt}</pre>
                      </div>
                    ) : null}
                    {clip.prompts?.video_prompt && (
                      <div className="stack">
                        <span className="subtitle">Video prompt</span>
                        <pre className="code">{clip.prompts.video_prompt}</pre>
                      </div>
                    )}
                  </div>
                )}
                {clip.debug_prompts && (
                  <details className="stack">
                    <summary className="subtitle">Prompt steps</summary>
                    <div className="stack">
                      {clip.debug_prompts.prompt_writer && (
                        <details className="stack">
                          <summary className="subtitle">Prompt writer</summary>
                          {clip.debug_prompts.prompt_writer.input && (
                            <div className="stack">
                              <span className="subtitle">Input</span>
                              <pre className="code">
                                {clip.debug_prompts.prompt_writer.input}
                              </pre>
                            </div>
                          )}
                          {clip.debug_prompts.prompt_writer.output && (
                            <div className="stack">
                              <span className="subtitle">Output (JSON)</span>
                              <pre className="code">
                                {JSON.stringify(
                                  clip.debug_prompts.prompt_writer.output,
                                  null,
                                  2
                                )}
                              </pre>
                            </div>
                          )}
                        </details>
                      )}

                      {clip.debug_prompts.keyframes && (
                        <details className="stack">
                          <summary className="subtitle">Keyframe generation</summary>
                          {clip.debug_prompts.keyframes.frame_prompts?.length ? (
                            <div className="stack">
                              <span className="subtitle">Prompts</span>
                              <pre className="code">
                                {clip.debug_prompts.keyframes.frame_prompts
                                  .map((prompt, idx) => `#${idx + 1} ${prompt}`)
                                  .join("\n")}
                              </pre>
                            </div>
                          ) : null}
                          {clip.debug_prompts.keyframes.i2i_prompt_prefix && (
                            <div className="stack">
                              <span className="subtitle">i2i prefix</span>
                              <pre className="code">
                                {clip.debug_prompts.keyframes.i2i_prompt_prefix}
                              </pre>
                            </div>
                          )}
                          {clip.debug_prompts.keyframes.generated_frame_urls?.length ? (
                            <div className="stack">
                              <span className="subtitle">Generated keyframes</span>
                              <div className="scroll-row">
                                {clip.debug_prompts.keyframes.generated_frame_urls.map(
                                  (url, idx) => (
                                    <img
                                      key={`${url}-${idx}`}
                                      className="video"
                                      src={url}
                                      alt={`Generated keyframe ${idx + 1} for ${clip.clip_id || "clip"}`}
                                    />
                                  )
                                )}
                              </div>
                            </div>
                          ) : null}
                        </details>
                      )}

                      {clip.debug_prompts.storyboard?.url && (
                        <details className="stack">
                          <summary className="subtitle">Storyboard</summary>
                          <div className="scroll-row">
                            <img
                              className="video"
                              src={clip.debug_prompts.storyboard.url}
                              alt={`Storyboard for ${clip.clip_id || "clip"}`}
                            />
                          </div>
                        </details>
                      )}

                      {clip.debug_prompts.video && (
                        <details className="stack">
                          <summary className="subtitle">Video generation</summary>
                          {clip.debug_prompts.video.model && (
                            <div className="stack">
                              <span className="subtitle">Model</span>
                              <pre className="code">{clip.debug_prompts.video.model}</pre>
                            </div>
                          )}
                          {clip.debug_prompts.video.grok_prompt && (
                            <div className="stack">
                              <span className="subtitle">Grok prompt</span>
                              <pre className="code">
                                {clip.debug_prompts.video.grok_prompt}
                              </pre>
                            </div>
                          )}
                          {clip.debug_prompts.video.fal_payload && (
                            <div className="stack">
                              <span className="subtitle">FAL payload</span>
                              <pre className="code">
                                {JSON.stringify(
                                  clip.debug_prompts.video.fal_payload,
                                  null,
                                  2
                                )}
                              </pre>
                            </div>
                          )}
                        </details>
                      )}
                    </div>
                  </details>
                )}
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
