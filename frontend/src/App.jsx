import { lazy } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useSession } from './auth/SessionContext';
import AppShell from './layout/AppShell';
import AppLoader from './components/AppLoader';
import Login from './pages/Login';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Documents = lazy(() => import('./pages/Documents'));
const AskAI = lazy(() => import('./pages/AskAI'));

function ProtectedLayout() {
  const { loading, authenticated } = useSession();
  const location = useLocation();

  if (loading) {
    return <AppLoader variant="fullscreen" />;
  }
  if (!authenticated) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  return <AppShell />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<ProtectedLayout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/documents" element={<Documents />} />
        <Route path="/ask" element={<AskAI />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
