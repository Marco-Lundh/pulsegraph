import { useQuery } from '@tanstack/react-query';
import { adminApi } from '../api/admin';

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <p
        className="text-lg font-semibold"
        style={{ color: 'var(--color-text-primary)' }}
      >
        {value}
      </p>
      <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
        {label}
      </p>
    </div>
  );
}

export function AdminCostsPage() {
  const { data: costs, isLoading } = useQuery({
    queryKey: ['admin', 'costs'],
    queryFn: () => adminApi.costs(),
    refetchInterval: 30000,
  });

  if (isLoading || !costs) {
    return (
      <div className="flex justify-center py-16">
        <div className="h-7 w-7 animate-spin rounded-full border-2 border-[var(--color-accent)] border-t-transparent" />
      </div>
    );
  }

  return (
    <div>
      <div
        className="mb-6 rounded-xl p-5"
        style={{
          backgroundColor: 'var(--color-bg-card)',
          border: '1px solid var(--color-border)',
        }}
      >
        <p
          className="mb-4 text-sm font-medium"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          Cloud-model spend · last {costs.window_days} days
        </p>
        <div className="grid grid-cols-3 gap-4">
          <Metric label="Total (USD)" value={`$${costs.total_usd.toFixed(2)}`} />
          <Metric
            label="Tokens in"
            value={costs.total_tokens_in.toLocaleString('en-US')}
          />
          <Metric
            label="Tokens out"
            value={costs.total_tokens_out.toLocaleString('en-US')}
          />
        </div>
      </div>

      {costs.by_user.length === 0 ? (
        <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
          No cost events in the window.
        </p>
      ) : (
        <div
          className="overflow-x-auto rounded-xl"
          style={{
            backgroundColor: 'var(--color-bg-card)',
            border: '1px solid var(--color-border)',
          }}
        >
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                {['User', 'Events', 'Tokens in', 'Tokens out', 'Cost (USD)'].map(
                  (h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-xs font-medium"
                      style={{ color: 'var(--color-text-muted)' }}
                    >
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {costs.by_user.map((row) => (
                <tr
                  key={row.user_id}
                  style={{ borderBottom: '1px solid var(--color-border)' }}
                  className="last:border-0"
                >
                  <td
                    className="px-4 py-3"
                    style={{ color: 'var(--color-text-primary)' }}
                  >
                    {row.email ?? row.user_id}
                  </td>
                  <td
                    className="px-4 py-3"
                    style={{ color: 'var(--color-text-secondary)' }}
                  >
                    {row.events}
                  </td>
                  <td
                    className="px-4 py-3"
                    style={{ color: 'var(--color-text-secondary)' }}
                  >
                    {row.tokens_in.toLocaleString('en-US')}
                  </td>
                  <td
                    className="px-4 py-3"
                    style={{ color: 'var(--color-text-secondary)' }}
                  >
                    {row.tokens_out.toLocaleString('en-US')}
                  </td>
                  <td
                    className="px-4 py-3 font-medium"
                    style={{ color: 'var(--color-text-primary)' }}
                  >
                    ${row.cost_usd.toFixed(4)}
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
