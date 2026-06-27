import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Activity, Eye, PlusCircle, TrendingUp } from 'lucide-react';
import { watchesApi, type WatchOut } from '../api/watches';
import { StatusBadge } from '../components/StatusBadge';

function formatInterval(seconds: number): string {
  if (seconds < 3600) {
    return `${Math.round(seconds / 60)}m`;
  }
  if (seconds < 86400) {
    return `${Math.round(seconds / 3600)}h`;
  }
  return `${Math.round(seconds / 86400)}d`;
}

function formatRelativeTime(iso: string | null): string {
  if (!iso) {
    return 'Never';
  }
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) {
    return 'Just now';
  }
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  return `${Math.floor(hours / 24)}d ago`;
}

const sourceLabels: Record<string, string> = {
  jobtech: 'JobTech',
  riksdagen: 'Riksdagen',
  entsoe: 'ENTSO-E',
};

function StatCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string;
  value: number | string;
  icon: React.ComponentType<{ size: number; color?: string }>;
  color: string;
}) {
  return (
    <div
      className="flex items-center gap-4 rounded-xl p-5"
      style={{
        backgroundColor: 'var(--color-bg-card)',
        border: '1px solid var(--color-border)',
      }}
    >
      <div
        className="flex h-10 w-10 items-center justify-center rounded-lg"
        style={{ backgroundColor: `color-mix(in srgb, ${color} 15%, transparent)` }}
      >
        <Icon size={18} color={color} />
      </div>
      <div>
        <p className="text-2xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>
          {value}
        </p>
        <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          {label}
        </p>
      </div>
    </div>
  );
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
        {sourceLabels[watch.source]?.slice(0, 2) ?? '??'}
      </div>

      <div className="min-w-0 flex-1">
        <p
          className="truncate text-sm font-medium"
          style={{ color: 'var(--color-text-primary)' }}
        >
          {watch.prompt}
        </p>
        <p className="mt-0.5 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          {sourceLabels[watch.source]} · every {formatInterval(watch.schedule_interval_seconds)}
        </p>
      </div>

      <div className="flex shrink-0 flex-col items-end gap-1">
        <StatusBadge status={watch.is_active ? 'active' : 'paused'} />
        <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
          {formatRelativeTime(watch.last_run_at)}
        </p>
      </div>
    </Link>
  );
}

export function DashboardPage() {
  const { data: watches, isLoading } = useQuery({
    queryKey: ['watches'],
    queryFn: () => watchesApi.list(),
  });

  const active = watches?.filter((w) => w.is_active).length ?? 0;
  const total = watches?.length ?? 0;

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1
            className="text-2xl font-semibold"
            style={{ color: 'var(--color-text-primary)' }}
          >
            Dashboard
          </h1>
          <p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            Overview of your active monitors.
          </p>
        </div>
        <Link
          to="/watches/new"
          className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors"
          style={{ backgroundColor: 'var(--color-accent)', color: 'white' }}
        >
          <PlusCircle size={15} />
          New watch
        </Link>
      </div>

      <div className="mb-6 grid grid-cols-3 gap-4">
        <StatCard
          label="Total watches"
          value={total}
          icon={Eye}
          color="var(--color-accent)"
        />
        <StatCard
          label="Active"
          value={active}
          icon={Activity}
          color="var(--color-success)"
        />
        <StatCard
          label="Sources"
          value={new Set(watches?.map((w) => w.source)).size}
          icon={TrendingUp}
          color="var(--color-warning)"
        />
      </div>

      <div>
        <h2
          className="mb-3 text-sm font-medium"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          Your watches
        </h2>

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
            <div>
              <p
                className="font-medium"
                style={{ color: 'var(--color-text-primary)' }}
              >
                No watches yet
              </p>
              <p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                Create your first watch to start monitoring.
              </p>
            </div>
            <Link
              to="/watches/new"
              className="mt-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors"
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
    </div>
  );
}
