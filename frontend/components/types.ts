export type JobStatus = "pending" | "running" | "done" | "failed";

export interface JobLogResponse {
  level: "info" | "warn" | "error" | string;
  message: string;
  timestamp: string;
}

export interface ArtifactResponse {
  id: number;
  job_id: number;
  file_path: string;
  file_size: number | null;
  hash: string | null;
  created_at: string;
}

export interface JobResponse {
  id: number;
  status: JobStatus;
  created_at: string;
  target_url: string;
}

export interface JobDetailResponse {
  id: number;
  status: JobStatus;
  target_url: string;
  created_at: string;
  updated_at: string;
  artifact: ArtifactResponse | null;
  progress_pct: number;
}

