import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './contexts/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Layout } from './components/Layout';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { DashboardPage } from './pages/DashboardPage';
import { WatchesPage } from './pages/WatchesPage';
import { WatchDetailPage } from './pages/WatchDetailPage';
import { CreateWatchPage } from './pages/CreateWatchPage';
import { NotificationsPage } from './pages/NotificationsPage';
import { RunsPage } from './pages/RunsPage';

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
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
