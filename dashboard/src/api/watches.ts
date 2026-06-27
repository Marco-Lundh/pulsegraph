import { api } from './client';

export type SourceKind = 'jobtech' | 'riksdagen' | 'entsoe';

export interface WatchOut {
  id: string;
  user_id: string;
  source: SourceKind;
  prompt: string;
  config: Record<string, unknown>;
  is_active: boolean;
  schedule_interval_seconds: number;
  last_run_at: string | null;
  next_run_at: string;
  created_at: string;
  updated_at: string;
}

export interface WatchCreate {
  source: SourceKind;
  prompt: string;
  config?: Record<string, unknown>;
  schedule_interval_seconds?: number;
}

export interface WatchUpdate {
  prompt?: string;
  config?: Record<string, unknown>;
  is_active?: boolean;
  schedule_interval_seconds?: number;
}

export const watchesApi = {
  list: (): Promise<WatchOut[]> => api.get<WatchOut[]>('/watches'),
  get: (id: string): Promise<WatchOut> => api.get<WatchOut>(`/watches/${id}`),
  create: (body: WatchCreate): Promise<WatchOut> =>
    api.post<WatchOut>('/watches', body),
  update: (id: string, body: WatchUpdate): Promise<WatchOut> =>
    api.patch<WatchOut>(`/watches/${id}`, body),
  delete: (id: string): Promise<void> => api.delete<void>(`/watches/${id}`),
};
