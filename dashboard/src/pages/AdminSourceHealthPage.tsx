import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Play, Radio } from 'lucide-react';
import { adminApi } from '../api/admin';
import { ApiError } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import type { SourceKind } from '../api/watches';

const sourceLabels: Record<string, string> = {
  jobtech: 'JobTech',
  riksdagen: 'Riksdagen',
  entsoe: 'ENTSO-E',
};

export function AdminSourceHealthPage() {
  const queryClient = useQueryClient();
  const { data: sources, isLoading } = useQuery({
    queryKey: ['admin', 'source-health'],
    queryFn: () => adminApi.sourceHealth(),
  });

  const resumeMutation = useMutation({
    mutationFn: (source: SourceKind) => adminApi.resumeSource(source),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'source-health'] });
      queryClient.invalidateQueries({ queryKey: ['admin', 'ops'] });
    },
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <div className="h-7 w-7 animate-spin rounded-full border-2 border-[var(--color-accent)] border-t-transparent" />
      </div>
    );
  }

  if (!sources || sources.length === 0) {
    return (
      <div
        className="flex flex-col items-center gap-3 rounded-xl py-16 text-center"
        style={{
          backgroundColor: 'var(--color-bg-card)',
          border: '1px solid var(--color-border)',
        }}
      >
        <Radio size={32} color="var(--color-text-muted)" />
        <p className="font-medium" style={{ color: 'var(--color-text-primary)' }}>
          No source health data yet
        </p>
      </div>
    );
  }

  return (
    <div>
      {resumeMutation.isError && (
        <div
          className="mb-4 rounded-lg p-3 text-sm"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--color-danger) 12%, transparent)',
            color: 'var(--color-danger)',
          }}
        >
          {resumeMutation.error instanceof ApiError
            ? resumeMutation.error.message
            : 'Failed to resume source.'}
        </div>
      )}

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
              {['Source', 'Status', 'Drift detail', 'Last checked', ''].map((h) => (
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
            {sources.map((s) => (
              <tr
                key={s.source}
                style={{ borderBottom: '1px solid var(--color-border)' }}
                className="last:border-0"
              >
                <td className="px-4 py-3" style={{ color: 'var(--color-text-primary)' }}>
                  {sourceLabels[s.source] ?? s.source}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={s.status} />
                </td>
                <td
                  className="max-w-xs truncate px-4 py-3 text-xs"
                  style={{ color: 'var(--color-text-secondary)' }}
                >
                  {s.drift_detail ?? '—'}
                </td>
                <td className="px-4 py-3" style={{ color: 'var(--color-text-secondary)' }}>
                  {new Date(s.last_checked_at).toLocaleString('sv-SE', {
                    dateStyle: 'short',
                    timeStyle: 'short',
                  })}
                </td>
                <td className="px-4 py-3 text-right">
                  {s.status === 'paused' && (
                    <button
                      onClick={() => resumeMutation.mutate(s.source)}
                      disabled={resumeMutation.isPending}
                      className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors disabled:opacity-50"
                      style={{
                        color: 'var(--color-accent)',
                        border: '1px solid var(--color-border)',
                      }}
                      title="Resume this source once its schema is back"
                    >
                      <Play size={12} />
                      Resume
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
