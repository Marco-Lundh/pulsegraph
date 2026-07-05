import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Activity } from 'lucide-react';
import { watchesApi } from '../api/watches';
import { runsApi } from '../api/runs';
import { StatusBadge } from '../components/StatusBadge';

export function RunsPage() {
  const navigate = useNavigate();
  const { data: watches } = useQuery({
    queryKey: ['watches'],
    queryFn: () => watchesApi.list(),
  });

  const watchIds = watches?.map((w) => w.id) ?? [];

  const { data: allRuns, isLoading } = useQuery({
    queryKey: ['runs', 'all', watchIds],
    queryFn: async () => {
      const nested = await Promise.all(
        watchIds.map((id) => runsApi.listForWatch(id)),
      );
      return nested.flat().sort(
        (a, b) =>
          new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
      );
    },
    enabled: watchIds.length > 0,
    refetchInterval: 15000,
  });

  const watchMap = new Map(watches?.map((w) => [w.id, w]));

  return (
    <div className="mx-auto max-w-3xl">
      <h1
        className="mb-6 text-2xl font-semibold"
        style={{ color: 'var(--color-text-primary)' }}
      >
        Runs
      </h1>

      {(isLoading || !watches) && (
        <div className="flex justify-center py-16">
          <div className="h-7 w-7 animate-spin rounded-full border-2 border-[var(--color-accent)] border-t-transparent" />
        </div>
      )}

      {!isLoading && watchIds.length === 0 && (
        <div
          className="flex flex-col items-center gap-3 rounded-xl py-16 text-center"
          style={{
            backgroundColor: 'var(--color-bg-card)',
            border: '1px solid var(--color-border)',
          }}
        >
          <Activity size={32} color="var(--color-text-muted)" />
          <p className="font-medium" style={{ color: 'var(--color-text-primary)' }}>
            No runs yet
          </p>
        </div>
      )}

      {!isLoading && allRuns && allRuns.length > 0 && (
        <div
          className="overflow-hidden rounded-xl"
          style={{
            backgroundColor: 'var(--color-bg-card)',
            border: '1px solid var(--color-border)',
          }}
        >
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                {['Status', 'Watch', 'Started', 'Error'].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-3 text-left text-xs font-medium"
                    style={{ color: 'var(--color-text-muted)' }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {allRuns.map((run) => {
                const watch = watchMap.get(run.watch_id);
                return (
                  <tr
                    key={run.id}
                    onClick={() => navigate(`/runs/${run.id}`)}
                    style={{ borderBottom: '1px solid var(--color-border)' }}
                    className="cursor-pointer transition-colors last:border-0 hover:bg-[var(--color-bg-input)]"
                  >
                    <td className="px-4 py-3">
                      <StatusBadge status={run.status} />
                    </td>
                    <td
                      className="max-w-[160px] truncate px-4 py-3 text-xs"
                      style={{ color: 'var(--color-text-secondary)' }}
                    >
                      {watch?.prompt ?? run.watch_id.slice(0, 8)}
                    </td>
                    <td className="px-4 py-3" style={{ color: 'var(--color-text-secondary)' }}>
                      {new Date(run.started_at).toLocaleString('sv-SE', {
                        dateStyle: 'short',
                        timeStyle: 'short',
                      })}
                    </td>
                    <td
                      className="max-w-xs truncate px-4 py-3 text-xs"
                      style={{ color: 'var(--color-danger)' }}
                    >
                      {run.error ?? '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
