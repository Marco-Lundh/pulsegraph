import { useQuery } from '@tanstack/react-query';
import { AlertTriangle } from 'lucide-react';
import { adminApi } from '../api/admin';

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <p className="text-lg font-semibold" style={{ color: 'var(--color-text-primary)' }}>
        {value}
      </p>
      <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
        {label}
      </p>
    </div>
  );
}

function SectionCard({
  title,
  alert,
  children,
}: {
  title: string;
  alert: boolean;
  children: React.ReactNode;
}) {
  return (
    <div
      className="rounded-xl p-5"
      style={{
        backgroundColor: 'var(--color-bg-card)',
        border: `1px solid ${
          alert ? 'var(--color-danger)' : 'var(--color-border)'
        }`,
      }}
    >
      <div className="mb-4 flex items-center gap-2">
        <p className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          {title}
        </p>
        {alert && <AlertTriangle size={14} color="var(--color-danger)" />}
      </div>
      <div className="grid grid-cols-2 gap-4">{children}</div>
    </div>
  );
}

export function AdminOpsPage() {
  const { data: ops, isLoading } = useQuery({
    queryKey: ['admin', 'ops'],
    queryFn: () => adminApi.ops(),
    refetchInterval: 30000,
  });

  if (isLoading || !ops) {
    return (
      <div className="flex justify-center py-16">
        <div className="h-7 w-7 animate-spin rounded-full border-2 border-[var(--color-accent)] border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-4">
      <SectionCard title="Spend" alert={ops.spend.near_cap || ops.spend.over_cap}>
        <Metric label="Spend (USD)" value={`$${ops.spend.spend_usd.toFixed(2)}`} />
        <Metric label="Cap (USD)" value={`$${ops.spend.cap_usd.toFixed(2)}`} />
        <Metric label="Ratio" value={`${(ops.spend.ratio * 100).toFixed(0)}%`} />
        <Metric label="Status" value={ops.spend.over_cap ? 'Over cap' : ops.spend.near_cap ? 'Near cap' : 'OK'} />
      </SectionCard>

      <SectionCard title="Queue" alert={ops.queue.worker_down || ops.queue.backlog}>
        <Metric label="Depth" value={ops.queue.depth} />
        <Metric label="Worker" value={ops.queue.worker_alive ? 'Alive' : 'Down'} />
        <Metric label="Backlog" value={ops.queue.backlog ? 'Yes' : 'No'} />
      </SectionCard>

      <SectionCard title="Sources" alert={ops.sources.alert}>
        <Metric label="Paused" value={ops.sources.paused.length} />
        <div>
          <p className="text-sm" style={{ color: 'var(--color-text-primary)' }}>
            {ops.sources.paused.length > 0 ? ops.sources.paused.join(', ') : 'None'}
          </p>
          <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            Paused sources
          </p>
        </div>
      </SectionCard>

      <SectionCard title="Latency" alert={ops.latency.slow}>
        <Metric label="Runs (24h)" value={ops.latency.count} />
        <Metric label="Avg (s)" value={ops.latency.avg_seconds} />
        <Metric label="p95 (s)" value={ops.latency.p95_seconds} />
        <Metric label="Max (s)" value={ops.latency.max_seconds} />
      </SectionCard>
    </div>
  );
}
