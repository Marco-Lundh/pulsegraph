import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  Bell,
  Eye,
  LayoutDashboard,
  LogOut,
  Settings,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { adminApi, countOpsAlerts } from '../api/admin';

const navItems = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/watches', icon: Eye, label: 'Watches' },
  { to: '/notifications', icon: Bell, label: 'Notifications' },
  { to: '/runs', icon: Activity, label: 'Runs' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

export function Layout() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const isAdmin = user?.role === 'admin';

  const { data: ops } = useQuery({
    queryKey: ['admin', 'ops'],
    queryFn: () => adminApi.ops(),
    enabled: isAdmin,
    refetchInterval: 30000,
  });
  const alertCount = ops ? countOpsAlerts(ops) : 0;

  const handleSignOut = () => {
    signOut();
    navigate('/login', { replace: true });
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <aside
        style={{
          backgroundColor: 'var(--color-bg-sidebar)',
          borderRight: '1px solid var(--color-sidebar-border)',
        }}
        className="flex w-60 shrink-0 flex-col"
      >
        <div
          className="flex items-center gap-2.5 px-5 py-5"
          style={{ borderBottom: '1px solid var(--color-sidebar-border)' }}
        >
          <div
            className="flex h-8 w-8 items-center justify-center rounded-lg"
            style={{ backgroundColor: 'var(--color-accent)' }}
          >
            <Zap size={16} color="white" />
          </div>
          <span
            className="text-sm font-semibold tracking-wide"
            style={{ color: 'var(--color-sidebar-text)' }}
          >
            PulseGraph
          </span>
        </div>

        <nav className="flex flex-1 flex-col gap-0.5 p-3">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                [
                  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  isActive ? 'bg-white/10' : 'hover:bg-white/5',
                ].join(' ')
              }
              style={({ isActive }) => ({
                color: isActive
                  ? 'var(--color-sidebar-text)'
                  : 'var(--color-sidebar-text-dim)',
              })}
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}

          {isAdmin && (
            <NavLink
              to="/admin"
              className={({ isActive }) =>
                [
                  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  isActive ? 'bg-white/10' : 'hover:bg-white/5',
                ].join(' ')
              }
              style={({ isActive }) => ({
                color: isActive
                  ? 'var(--color-sidebar-text)'
                  : 'var(--color-sidebar-text-dim)',
              })}
            >
              <ShieldCheck size={16} />
              Admin
              {alertCount > 0 && (
                <span
                  className="ml-auto flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-semibold text-white"
                  style={{ backgroundColor: 'var(--color-danger)' }}
                >
                  {alertCount}
                </span>
              )}
            </NavLink>
          )}
        </nav>

        <div
          className="flex items-center gap-3 p-4"
          style={{ borderTop: '1px solid var(--color-sidebar-border)' }}
        >
          <div className="min-w-0 flex-1">
            <p
              className="truncate text-xs font-medium"
              style={{ color: 'var(--color-sidebar-text)' }}
            >
              {user?.email}
            </p>
            <p
              className="text-xs capitalize"
              style={{ color: 'var(--color-sidebar-text-dim)' }}
            >
              {user?.role}
            </p>
          </div>
          <button
            onClick={handleSignOut}
            className="rounded-md p-1.5 transition-colors hover:bg-white/5 hover:text-[var(--color-sidebar-text)]"
            style={{ color: 'var(--color-sidebar-text-dim)' }}
            title="Sign out"
          >
            <LogOut size={15} />
          </button>
        </div>
      </aside>

      <main className="flex flex-1 flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
