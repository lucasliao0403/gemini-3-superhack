export type ClipMoment = {
  clip_id?: string;
  start_ms?: number;
  peak_ms?: number;
  end_ms?: number;
  type: string;
  description: string;
  players?: string[];
  context?: string;
  announcer_energy?: number;
  crowd_energy?: number;
  format_id?: number;
  assets?: {
    frame_url?: string;
    ref_frame_url?: string;
    clip_url?: string;
    audio_url?: string;
  };
  prompts?: {
    image_prompt?: string;
    video_prompt?: string;
  };
};

export type ReelResult = {
  id: string;
  clip_id?: string;
  format_id: number;
  video_url: string;
  poster_url?: string | null;
  duration_s?: number;
};

export type JobStatus = {
  job_id: string;
  status: "queued" | "running" | "failed" | "complete";
  stage?: string;
  progress?: number;
  message?: string;
  error?: { message: string };
  clips?: ClipMoment[];
  outputs?: ReelResult[];
  fal_debug?: unknown;
};
