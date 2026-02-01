"use client";

import { type FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { createJob, isDemoMode, formatBytes, getDemoJobId } from "@/lib/api";

const MAX_MB = 100;

export default function Home() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const demoMode = useMemo(() => isDemoMode(), []);

  const handleFile = (nextFile: File | null) => {
    if (!nextFile) {
      setFile(null);
      return;
    }

    const isMp4 =
      nextFile.type === "video/mp4" ||
      nextFile.name.toLowerCase().endsWith(".mp4");
    if (!isMp4) {
      setError("Only .mp4 files are supported.");
      setFile(null);
      return;
    }

    if (nextFile.size > MAX_MB * 1024 * 1024) {
      setError("File must be under 100MB.");
      setFile(null);
      return;
    }

    setError(null);
    setFile(nextFile);
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!file) {
      setError("Select an MP4 file to continue.");
      return;
    }

    setIsSubmitting(true);
    try {
      const { job_id } = await createJob(file);
      router.push(`/jobs/${job_id}`);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Upload failed. Try again."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="container">
      <div className="stack">
        <header className="stack">
          <h1 className="megaTitle">whose clip is it?</h1>
          <h2 className="title">ai-powered brainrot reels for sports clips.</h2>
          <p className="subtitle">
            upload a video. we'll find the viral moment and generate a reel.
          </p>
          {demoMode && (
            <p className="subtitle">
              Demo mode enabled: uses mock results without API keys.
            </p>
          )}
        </header>

        <form className="card stack" onSubmit={onSubmit}>
          <div>
           
            <input
              id="video"
              className="file"
              type="file"
              accept="video/mp4"
              onChange={(event) => handleFile(event.target.files?.[0] || null)}
            />
          </div>

          {file && (
            <div className="row">
              <span className="badge">{file.name}</span>
              <span className="subtitle">{formatBytes(file.size)}</span>
            </div>
          )}

          {error && <p className="status error">{error}</p>}

          <div className="row">
            <button className="button" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "uploading..." : "generate reel"}
            </button>
            <a className="button secondary" href={`/jobs/${getDemoJobId()}`}>
              View demo results
            </a>
          </div>
        </form>
      </div>
    </div>
  );
}
