import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Eye, PlusCircle } from 'lucide-react';
import { watchesApi, type WatchOut } from '../api/watches';
import { StatusBadge } from '../components/StatusBadge';

const sourceLabels: Record<string, string> = {
  jobtech: 'JobTech',
  riksdagen: 'Riksdagen',
  entsoe: 'ENTSO-E',
};

function formatInterval(seconds: number): string {
  if (seconds < 3600) {
    return `every ${Math.round(seconds / 60)}m`;
  }
  if (seconds < 86400) {
    return `every ${Math.round(seconds / 3600)}h`;
  }
  return `every ${Math.round(seconds / 86400)}d`;
}

function WatchRow({ watch }: { watch: WatchOut }) {
  return (
    <Link
      to={`/watches/${watch.id}`}
      className="flex items-center gap-4 rounded-xl px-5 py-4 transition-colors hover:bg-white/5"
      style={{
        backgroundColor: 'var(--color-bg-card)',
        border: '1px solid var(--color-border)',
      }}
    >
      <div
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-xs font-bold"
        style={{
          backgroundColor: 'color-mix(in srgb, var(--color-accent) 15%, transparent)',
          color: 'var(--color-accent)',
        }}
      >
        {(sourceLabels[watch.source] ?? '?').slice(0, 2)}
      </div>
      <div className="min-w-0 flex-1">
        <p
          className="truncate text-sm font-medium"
          style={{ color: 'var(--color-text-primary)' }}
        >
          {watch.prompt}
        </p>
        <p className="mt-0.5 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          {sourceLabels[watch.source]} · {formatInterval(watch.schedule_interval_seconds)}
        </p>
      </div>
      <StatusBadge status={watch.is_active ? 'active' : 'paused'} />
    </Link>
  );
}

export function WatchesPage() {
  const { data: watches, isLoading } = useQuery({
    queryKey: ['watches'],
    queryFn: () => watchesApi.list(),
  });

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6 flex items-center justify-between">
        <h1
          className="text-2xl font-semibold"
          style={{ color: 'var(--color-text-primary)' }}
        >
          Watches
        </h1>
        <Link
          to="/watches/new"
          className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium"
          style={{ backgroundColor: 'var(--color-accent)', color: 'white' }}
        >
          <PlusCircle size={15} />
          New watch
        </Link>
      </div>

      {isLoading && (
        <div className="flex justify-center py-16">
          <div className="h-7 w-7 animate-spin rounded-full border-2 border-[var(--color-accent)] border-t-transparent" />
        </div>
      )}

      {!isLoading && watches?.length === 0 && (
        <div
          className="flex flex-col items-center gap-3 rounded-xl py-16 text-center"
          style={{
            backgroundColor: 'var(--color-bg-card)',
            border: '1px solid var(--color-border)',
          }}
        >
          <Eye size={32} color="var(--color-text-muted)" />
          <p className="font-medium" style={{ color: 'var(--color-text-primary)' }}>
            No watches yet
          </p>
          <Link
            to="/watches/new"
            className="rounded-lg px-4 py-2 text-sm font-medium"
            style={{ backgroundColor: 'var(--color-accent)', color: 'white' }}
          >
            Create a watch
          </Link>
        </div>
      )}

      {!isLoading && watches && watches.length > 0 && (
        <div className="flex flex-col gap-2">
          {watches.map((w) => (
            <WatchRow key={w.id} watch={w} />
          ))}
        </div>
      )}
    </div>
  );
}
