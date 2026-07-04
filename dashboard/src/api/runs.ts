import { api } from './client';

export type RunStatus = 'pending' | 'running' | 'succeeded' | 'failed';

export interface RunOut {
  id: string;
  watch_id: string;
  status: RunStatus;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export const runsApi = {
  list: (sinceIso?: string): Promise<RunOut[]> =>
    api.get<RunOut[]>(
      sinceIso ? `/runs?since=${encodeURIComponent(sinceIso)}` : '/runs'
    ),
  listForWatch: (watchId: string): Promise<RunOut[]> =>
    api.get<RunOut[]>(`/runs?watch_id=${watchId}`),
};
