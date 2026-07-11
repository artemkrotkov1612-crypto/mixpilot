/** Контракты worker'а (01_DOCS/TZ.md §7). */

export interface Track {
  id: string;
  user_id: string;
  title: string;
  artist: string | null;
  duration_s: number;
  sample_rate: number | null;
  format: string | null;
  src_path: string | null;
  media_path: string;
  content_hash: string;
  added_at: string;
  is_favorite: 0 | 1;
  origin: 'import' | 'render';
}

export interface ImportedTrack extends Track {
  duplicate: boolean;
}

export interface PeaksDoc {
  version: number;
  buckets: number;
  duration_s: number;
  peaks: number[];
}

export type ProjectMode = 'remix' | 'merge' | 'voice_cover' | 'voice_self' | 'voice_overbeat';

export interface RemixParams {
  style?: string;
  chips?: string[];
  text?: string;
  quality?: 'fast' | 'max';
}

export interface ProjectTrack extends Track {
  role: 'source' | 'reference' | 'beat';
  position: number;
}

export interface Project {
  id: string;
  mode: ProjectMode;
  title: string;
  status: 'draft' | 'processing' | 'ready' | 'error';
  params: RemixParams & Record<string, unknown>;
  created_at: string;
  updated_at: string;
  tracks: ProjectTrack[];
  track_count?: number;
}

export interface Settings {
  quality_mode: 'fast' | 'max';
  cloud_enabled: boolean;
  learning_enabled: boolean;
  results_dir: string;
}

export interface Section {
  id: string;
  label: 'intro' | 'verse' | 'chorus' | 'bridge' | 'drop' | 'outro';
  start_s: number;
  end_s: number;
  start_beat: number;
  end_beat: number;
  energy: number;
}

export interface Analysis {
  track_id: string;
  bpm: number;
  bpm_conf: number;
  key_root: string;
  key_mode: 'major' | 'minor';
  key_conf: number;
  beats: number[];
  downbeats: number[];
  sections: Section[];
  engine_ver: string;
}

export type JobStatus = 'queued' | 'running' | 'done' | 'error' | 'cancelled';

export interface Job {
  id: string;
  kind: string;
  status: JobStatus;
  priority: number;
  progress: number;
  stage: string | null;
  error_code: string | null;
  error_detail: string | null;
  gpu: boolean;
}

/** POST /analysis|/stems: сразу готово или поставлено в очередь. */
export interface StartProcessing {
  status: 'ready' | 'queued';
  analysis?: Analysis;
  job?: Job;
}

export interface StorageInfo {
  data_dir: string;
  disk_total_gb: number;
  disk_free_gb: number;
  media_mb: number;
  cache_mb: number;
  renders_mb: number;
}
