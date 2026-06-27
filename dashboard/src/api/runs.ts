import { api } from './client';

export type RunStatus = 'pending' | 'running' | 'success' | 'failed';

export interface RunOut {
  id: string;
  watch_id: string;
  status: RunStatus;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export const runsApi = {
  listForWatch: (watchId: string): Promise<RunOut[]> =>
    api.get<RunOut[]>(`/runs?watch_id=${watchId}`),
};
