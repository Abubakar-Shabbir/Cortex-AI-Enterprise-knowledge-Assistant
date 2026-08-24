import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useSession } from './auth/SessionContext';
import AppShell from './layout/AppShell';
import Login from './pages/Login';

// Route-level code splitting (Phase 5) - each page's bundle is only
// fetched when the user actually navigates to it, instead of one
// bundle up front.
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Documents = lazy(() => import('./pages/Documents'));
const AskAI = lazy(() => import('./pages/AskAI'));

function PageFallback() {
  return (
    <div className="flex items-center justify-center py-24 text-sm text-muted dark:text-muted-dark">
      Loading…
    </div>
  );
}

function ProtectedLayout() {
  const { loading, authenticated } = useSession();
  const location = useLocation();

  if (loading) return <PageFallback />;
  if (!authenticated) return <Navigate to="/login" state={{ from: location.pathname }} replace />;

  return <AppShell />;
}

export default function App() {
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<ProtectedLayout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/documents" element={<Documents />} />
          <Route path="/ask" element={<AskAI />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
