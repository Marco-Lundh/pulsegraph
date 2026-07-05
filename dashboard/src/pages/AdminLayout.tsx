import { NavLink, Outlet } from 'react-router-dom';

const tabs = [
  { to: 'ops', label: 'Ops' },
  { to: 'source-health', label: 'Source health' },
  { to: 'review-queue', label: 'Review queue' },
  { to: 'costs', label: 'Costs' },
  { to: 'users', label: 'Users' },
];

export function AdminLayout() {
  return (
    <div className="mx-auto max-w-4xl">
      <h1
        className="mb-1 text-2xl font-semibold"
        style={{ color: 'var(--color-text-primary)' }}
      >
        Admin
      </h1>
      <p className="mb-6 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
        Operational health, review queue, spend, and user management.
      </p>

      <div
        className="mb-6 flex gap-1 border-b"
        style={{ borderColor: 'var(--color-border)' }}
      >
        {tabs.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              [
                'border-b-2 px-3 py-2 text-sm font-medium transition-colors',
                isActive ? 'border-[var(--color-accent)]' : 'border-transparent',
              ].join(' ')
            }
            style={({ isActive }) => ({
              color: isActive
                ? 'var(--color-accent)'
                : 'var(--color-text-secondary)',
            })}
          >
            {label}
          </NavLink>
        ))}
      </div>

      <Outlet />
    </div>
  );
}
