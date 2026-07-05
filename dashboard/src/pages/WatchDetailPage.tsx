import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Pause, Play, Trash2 } from 'lucide-react';
import { watchesApi } from '../api/watches';
import { runsApi } from '../api/runs';
import { StatusBadge } from '../components/StatusBadge';
import { ApiError } from '../api/client';

function formatDatetime(iso: string | null): string {
  if (!iso) {
    return '—';
  }
  return new Date(iso).toLocaleString('sv-SE', {
    dateStyle: 'short',
    timeStyle: 'short',
  });
}

function formatDuration(start: string, end: string | null): string {
  if (!end) {
    return '—';
  }
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 1000) {
    return `${ms}ms`;
  }
  return `${(ms / 1000).toFixed(1)}s`;
}

const sourceLabels: Record<string, string> = {
  jobtech: 'JobTech',
  riksdagen: 'Riksdagen',
  entsoe: 'ENTSO-E',
};

export function WatchDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [deleteError, setDeleteError] = useState('');

  const { data: watch, isLoading } = useQuery({
    queryKey: ['watches', id],
    queryFn: () => watchesApi.get(id!),
    enabled: !!id,
  });

  const { data: runs } = useQuery({
    queryKey: ['runs', id],
    queryFn: () => runsApi.listForWatch(id!),
    enabled: !!id,
    refetchInterval: 15000,
  });

  const toggleMutation = useMutation({
    mutationFn: () =>
      watchesApi.update(id!, { is_active: !watch?.is_active }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watches'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => watchesApi.delete(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watches'] });
      navigate('/watches', { replace: true });
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setDeleteError(err.message);
      }
    },
  });

  if (isLoading || !watch) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-7 w-7 animate-spin rounded-full border-2 border-[var(--color-accent)] border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <button
        onClick={() => navigate(-1)}
        className="mb-6 flex items-center gap-2 text-sm transition-colors"
        style={{ color: 'var(--color-text-secondary)' }}
      >
        <ArrowLeft size={14} />
        Back
      </button>

      <div
        className="mb-6 rounded-xl p-6"
        style={{
          backgroundColor: 'var(--color-bg-card)',
          border: '1px solid var(--color-border)',
        }}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span
                className="rounded px-2 py-0.5 text-xs font-medium"
                style={{
                  backgroundColor: 'color-mix(in srgb, var(--color-accent) 15%, transparent)',
                  color: 'var(--color-accent)',
                }}
              >
                {sourceLabels[watch.source] ?? watch.source}
              </span>
              <StatusBadge status={watch.is_active ? 'active' : 'paused'} />
            </div>
            <h1
              className="mt-3 text-lg font-semibold leading-snug"
              style={{ color: 'var(--color-text-primary)' }}
            >
              {watch.prompt}
            </h1>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <button
              onClick={() => toggleMutation.mutate()}
              disabled={toggleMutation.isPending}
              className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-colors disabled:opacity-60"
              style={{
                backgroundColor: 'var(--color-bg-input)',
                border: '1px solid var(--color-border)',
                color: 'var(--color-text-primary)',
              }}
            >
              {watch.is_active ? <Pause size={13} /> : <Play size={13} />}
              {watch.is_active ? 'Pause' : 'Resume'}
            </button>
            <button
              onClick={() => {
                if (confirm('Delete this watch?')) {
                  deleteMutation.mutate();
                }
              }}
              disabled={deleteMutation.isPending}
              className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-colors disabled:opacity-60"
              style={{
                backgroundColor: 'color-mix(in srgb, var(--color-danger) 12%, transparent)',
                border: '1px solid color-mix(in srgb, var(--color-danger) 30%, transparent)',
                color: 'var(--color-danger)',
              }}
            >
              <Trash2 size={13} />
              Delete
            </button>
          </div>
        </div>

        {deleteError && (
          <p className="mt-3 text-sm" style={{ color: 'var(--color-danger)' }}>
            {deleteError}
          </p>
        )}

        <dl
          className="mt-5 grid grid-cols-3 gap-4 border-t pt-5 text-sm"
          style={{ borderColor: 'var(--color-border)' }}
        >
          {[
            ['Interval', `${Math.round(watch.schedule_interval_seconds / 60)}m`],
            ['Last run', formatDatetime(watch.last_run_at)],
            ['Next run', formatDatetime(watch.next_run_at)],
            ['Created', formatDatetime(watch.created_at)],
          ].map(([label, value]) => (
            <div key={label}>
              <dt style={{ color: 'var(--color-text-muted)' }} className="text-xs">
                {label}
              </dt>
              <dd style={{ color: 'var(--color-text-primary)' }} className="mt-0.5 font-medium">
                {value}
              </dd>
            </div>
          ))}
        </dl>
      </div>

      <h2
        className="mb-3 text-sm font-medium"
        style={{ color: 'var(--color-text-secondary)' }}
      >
        Run history
      </h2>

      {!runs || runs.length === 0 ? (
        <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
          No runs yet.
        </p>
      ) : (
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
                {['Status', 'Started', 'Duration', 'Error'].map((h) => (
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
              {runs.map((run) => (
                <tr
                  key={run.id}
                  onClick={() => navigate(`/runs/${run.id}`)}
                  style={{ borderBottom: '1px solid var(--color-border)' }}
                  className="cursor-pointer transition-colors last:border-0 hover:bg-[var(--color-bg-input)]"
                >
                  <td className="px-4 py-3">
                    <StatusBadge status={run.status} />
                  </td>
                  <td className="px-4 py-3" style={{ color: 'var(--color-text-secondary)' }}>
                    {formatDatetime(run.started_at)}
                  </td>
                  <td className="px-4 py-3" style={{ color: 'var(--color-text-secondary)' }}>
                    {formatDuration(run.started_at, run.finished_at)}
                  </td>
                  <td
                    className="max-w-xs truncate px-4 py-3 text-xs"
                    style={{ color: 'var(--color-danger)' }}
                  >
                    {run.error ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
