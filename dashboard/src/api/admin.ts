import { api } from './client';
import type { SourceKind } from './watches';
import type { UserOut } from './auth';

export type SourceStatus = 'healthy' | 'paused';

export interface SourceHealthOut {
  source: SourceKind;
  status: SourceStatus;
  drift_detail: string | null;
  last_checked_at: string;
}

export interface OpsSummary {
  spend: {
    spend_usd: number;
    cap_usd: number;
    ratio: number;
    near_cap: boolean;
    over_cap: boolean;
  };
  queue: {
    depth: number;
    worker_alive: boolean;
    worker_down: boolean;
    backlog: boolean;
  };
  sources: {
    paused: string[];
    alert: boolean;
  };
  latency: {
    count: number;
    avg_seconds: number;
    p95_seconds: number;
    max_seconds: number;
    slow: boolean;
  };
}

export interface EvalHealth {
  window_hours: number;
  total: number;
  approved: number;
  review: number;
  pct_approved: number | null;
}

export interface ReviewQueueItem {
  id: string;
  analysis_id: string;
  relevance_score: number;
  confidence: number;
  evaluated_at: string;
}

export interface CostByUser {
  user_id: string;
  email: string | null;
  events: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
}

export interface CostSummary {
  window_days: number;
  total_usd: number;
  total_tokens_in: number;
  total_tokens_out: number;
  by_user: CostByUser[];
}

export type ReviewDecisionKind = 'approved' | 'rejected' | 'corrected';

export interface ReviewDecisionCreate {
  decision: ReviewDecisionKind;
  corrected_label?: string | null;
  note?: string | null;
}

export const adminApi = {
  sourceHealth: (): Promise<SourceHealthOut[]> =>
    api.get<SourceHealthOut[]>('/admin/source-health'),
  resumeSource: (source: SourceKind): Promise<SourceHealthOut> =>
    api.post<SourceHealthOut>(`/admin/source-health/${source}/resume`, {}),
  ops: (): Promise<OpsSummary> => api.get<OpsSummary>('/admin/ops'),
  costs: (): Promise<CostSummary> => api.get<CostSummary>('/admin/costs'),
  evalHealth: (): Promise<EvalHealth> =>
    api.get<EvalHealth>('/admin/eval-health'),
  reviewQueue: (): Promise<ReviewQueueItem[]> =>
    api.get<ReviewQueueItem[]>('/admin/review-queue'),
  decide: (
    evaluationId: string,
    body: ReviewDecisionCreate,
  ): Promise<{ id: string; decision: string }> =>
    api.post(`/admin/review-queue/${evaluationId}/decide`, body),
  users: (): Promise<UserOut[]> => api.get<UserOut[]>('/admin/users'),
  deleteUser: (userId: string): Promise<void> =>
    api.delete<void>(`/admin/users/${userId}`),
};

export function countOpsAlerts(ops: OpsSummary): number {
  let count = 0;
  if (ops.spend.near_cap || ops.spend.over_cap) count++;
  if (ops.queue.worker_down) count++;
  if (ops.queue.backlog) count++;
  if (ops.sources.alert) count++;
  if (ops.latency.slow) count++;
  return count;
}
