import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './contexts/AuthProvider';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AdminRoute } from './components/AdminRoute';
import { Layout } from './components/Layout';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { DashboardPage } from './pages/DashboardPage';
import { WatchesPage } from './pages/WatchesPage';
import { WatchDetailPage } from './pages/WatchDetailPage';
import { CreateWatchPage } from './pages/CreateWatchPage';
import { NotificationsPage } from './pages/NotificationsPage';
import { RunsPage } from './pages/RunsPage';
import { RunDetailPage } from './pages/RunDetailPage';
import { SettingsPage } from './pages/SettingsPage';
import { AdminLayout } from './pages/AdminLayout';
import { AdminOpsPage } from './pages/AdminOpsPage';
import { AdminSourceHealthPage } from './pages/AdminSourceHealthPage';
import { AdminReviewQueuePage } from './pages/AdminReviewQueuePage';
import { AdminUsersPage } from './pages/AdminUsersPage';
import { AdminCostsPage } from './pages/AdminCostsPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/watches" element={<WatchesPage />} />
              <Route path="/watches/new" element={<CreateWatchPage />} />
              <Route path="/watches/:id" element={<WatchDetailPage />} />
              <Route path="/notifications" element={<NotificationsPage />} />
              <Route path="/runs" element={<RunsPage />} />
              <Route path="/runs/:runId" element={<RunDetailPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route
                path="/admin"
                element={
                  <AdminRoute>
                    <AdminLayout />
                  </AdminRoute>
                }
              >
                <Route index element={<Navigate to="ops" replace />} />
                <Route path="ops" element={<AdminOpsPage />} />
                <Route path="source-health" element={<AdminSourceHealthPage />} />
                <Route path="review-queue" element={<AdminReviewQueuePage />} />
                <Route path="costs" element={<AdminCostsPage />} />
                <Route path="users" element={<AdminUsersPage />} />
              </Route>
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
