import { api } from './client';

export type RunStatus = 'running' | 'succeeded' | 'failed' | 'paused';
export type ModelKind = 'ollama' | 'claude';
export type EvalStatus = 'approved' | 'review';

export interface RunOut {
  id: string;
  watch_id: string;
  status: RunStatus;
  error: string | null;
  langsmith_trace_id: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface ItemResult {
  item_id: string;
  external_id: string | null;
  source: string;
  fetched_at: string;
  model_used: ModelKind;
  model_version: string;
  summary: string;
  analysis_confidence: number;
  relevance_score: number | null;
  eval_confidence: number | null;
  eval_status: EvalStatus | null;
  notified: boolean;
}

export const runsApi = {
  list: (sinceIso?: string): Promise<RunOut[]> =>
    api.get<RunOut[]>(
      sinceIso ? `/runs?since=${encodeURIComponent(sinceIso)}` : '/runs'
    ),
  listForWatch: (watchId: string): Promise<RunOut[]> =>
    api.get<RunOut[]>(`/runs?watch_id=${watchId}`),
  get: (runId: string): Promise<RunOut> => api.get<RunOut>(`/runs/${runId}`),
  itemsForRun: (runId: string): Promise<ItemResult[]> =>
    api.get<ItemResult[]>(`/runs/${runId}/items`),
};
