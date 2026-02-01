export type ClipMoment = {
  clip_id?: string;
  start_ms?: number;
  peak_ms?: number;
  end_ms?: number;
  beats?: { timestamp: string; caption: string }[];
  beat_timestamps_ms?: number[];
  beat_captions?: string[];
  type: string;
  description: string;
  players?: string[];
  context?: string;
  announcer_energy?: number;
  crowd_energy?: number;
  format_id?: number;
  assets?: {
    frame_url?: string;
    frame_urls?: string[];
    ref_frame_url?: string;
    generated_frame_urls?: string[];
    clip_url?: string;
    audio_url?: string;
  };
  prompts?: {
    image_prompt?: string;
    frame_prompts?: string[];
    video_prompt?: string;
    i2i_prompt_prefix?: string;
    segment_script?: string;
  };
  debug_prompts?: {
    prompt_writer?: {
      input?: string | null;
      output?: {
        frame_prompts?: string[];
        video_prompt?: string;
        i2i_prompt_prefix?: string;
        segment_script?: string;
      };
    };
    keyframes?: {
      frame_prompts?: string[];
      i2i_prompt_prefix?: string;
      generated_frame_urls?: string[];
    };
    storyboard?: {
      url?: string;
    };
    video?: {
      grok_prompt?: string;
      fal_payload?: unknown;
      model?: string;
    };
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
  created_at?: number;
  updated_at?: number;
  original_filename?: string;
  clips?: ClipMoment[];
  outputs?: ReelResult[];
  fal_debug?: unknown;
};
