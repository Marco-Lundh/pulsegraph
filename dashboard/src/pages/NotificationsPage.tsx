import { useQuery } from '@tanstack/react-query';
import { Bell } from 'lucide-react';
import { notificationsApi } from '../api/notifications';
import { StatusBadge } from '../components/StatusBadge';

export function NotificationsPage() {
  const { data: notifications, isLoading } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => notificationsApi.list(),
    refetchInterval: 30000,
  });

  return (
    <div className="mx-auto max-w-3xl">
      <h1
        className="mb-6 text-2xl font-semibold"
        style={{ color: 'var(--color-text-primary)' }}
      >
        Notifications
      </h1>

      {isLoading && (
        <div className="flex justify-center py-16">
          <div className="h-7 w-7 animate-spin rounded-full border-2 border-[var(--color-accent)] border-t-transparent" />
        </div>
      )}

      {!isLoading && notifications?.length === 0 && (
        <div
          className="flex flex-col items-center gap-3 rounded-xl py-16 text-center"
          style={{
            backgroundColor: 'var(--color-bg-card)',
            border: '1px solid var(--color-border)',
          }}
        >
          <Bell size={32} color="var(--color-text-muted)" />
          <p className="font-medium" style={{ color: 'var(--color-text-primary)' }}>
            No notifications yet
          </p>
        </div>
      )}

      {!isLoading && notifications && notifications.length > 0 && (
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
                {['Channel', 'Status', 'Delivered', 'Key'].map((h) => (
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
              {notifications.map((n) => (
                <tr
                  key={n.id}
                  style={{ borderBottom: '1px solid var(--color-border)' }}
                  className="last:border-0"
                >
                  <td className="px-4 py-3 capitalize" style={{ color: 'var(--color-text-secondary)' }}>
                    {n.channel}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={n.status} />
                  </td>
                  <td className="px-4 py-3" style={{ color: 'var(--color-text-secondary)' }}>
                    {n.delivered_at
                      ? new Date(n.delivered_at).toLocaleString('sv-SE', {
                          dateStyle: 'short',
                          timeStyle: 'short',
                        })
                      : '—'}
                  </td>
                  <td
                    className="max-w-xs truncate px-4 py-3 font-mono text-xs"
                    style={{ color: 'var(--color-text-muted)' }}
                  >
                    {n.dedup_key}
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
