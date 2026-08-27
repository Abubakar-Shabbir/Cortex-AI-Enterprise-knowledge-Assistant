import { lazy } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useSession } from './auth/SessionContext';
import AppShell from './layout/AppShell';
import AppLoader from './components/AppLoader';
import RequirePermission from './components/RequirePermission';
import Login from './pages/Login';
import Signup from './pages/Signup';
import VerifyOtp from './pages/VerifyOtp';
import ForgotPassword from './pages/ForgotPassword';
import PasswordResetSent from './pages/PasswordResetSent';
import PasswordResetConfirm from './pages/PasswordResetConfirm';
import PasswordResetComplete from './pages/PasswordResetComplete';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Documents = lazy(() => import('./pages/Documents'));
const AskAI = lazy(() => import('./pages/AskAI'));
const Profile = lazy(() => import('./pages/Profile'));
const Notifications = lazy(() => import('./pages/Notifications'));
const KnowledgeBrowse = lazy(() => import('./pages/knowledge/Browse'));
const KnowledgeRelationships = lazy(() => import('./pages/knowledge/Relationships'));
const KnowledgeGraph = lazy(() => import('./pages/knowledge/Graph'));
const KnowledgeInsights = lazy(() => import('./pages/knowledge/Insights'));
const KnowledgeCitations = lazy(() => import('./pages/knowledge/Citations'));
const EntityDetail = lazy(() => import('./pages/knowledge/EntityDetail'));
const DocumentKnowledge = lazy(() => import('./pages/knowledge/DocumentKnowledge'));
const AiTasks = lazy(() => import('./pages/AiTasks'));
const AiTaskResults = lazy(() => import('./pages/AiTaskResults'));
const AiTaskHistory = lazy(() => import('./pages/AiTaskHistory'));
const Analytics = lazy(() => import('./pages/Analytics'));
const Reports = lazy(() => import('./pages/Reports'));
const Favorites = lazy(() => import('./pages/Favorites'));
const SharedWithMe = lazy(() => import('./pages/SharedWithMe'));
const OrgLibrary = lazy(() => import('./pages/OrgLibrary'));
const Collections = lazy(() => import('./pages/Collections'));
const CollectionDetail = lazy(() => import('./pages/CollectionDetail'));
const SearchHistory = lazy(() => import('./pages/SearchHistory'));
const Monitoring = lazy(() => import('./pages/Monitoring'));
const AdminUsers = lazy(() => import('./pages/AdminUsers'));
const AdminUserProfile = lazy(() => import('./pages/AdminUserProfile'));
const AdminRoles = lazy(() => import('./pages/AdminRoles'));
const AdminQueries = lazy(() => import('./pages/AdminQueries'));
const AdminSystemLogs = lazy(() => import('./pages/AdminSystemLogs'));
const AdminSettings = lazy(() => import('./pages/AdminSettings'));

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
      <Route path="/signup" element={<Signup />} />
      <Route path="/verify-otp" element={<VerifyOtp />} />
      <Route path="/password-reset" element={<ForgotPassword />} />
      <Route path="/password-reset/sent" element={<PasswordResetSent />} />
      <Route path="/reset/done" element={<PasswordResetComplete />} />
      <Route path="/reset/:uidb64/:token" element={<PasswordResetConfirm />} />
      <Route element={<ProtectedLayout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/documents" element={<Documents />} />
        <Route path="/ask" element={<AskAI />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/knowledge" element={<KnowledgeBrowse />} />
        <Route path="/knowledge/relationships" element={<KnowledgeRelationships />} />
        <Route path="/knowledge/graph" element={<KnowledgeGraph />} />
        <Route path="/knowledge/insights" element={<KnowledgeInsights />} />
        <Route path="/knowledge/citations" element={<KnowledgeCitations />} />
        <Route path="/knowledge/entities/:entityId" element={<EntityDetail />} />
        <Route path="/knowledge/documents/:docId" element={<DocumentKnowledge />} />
        <Route element={<RequirePermission codename="pages.ai_tasks" />}>
          <Route path="/ai-tasks" element={<AiTasks />} />
          <Route path="/ai-tasks/history" element={<AiTaskHistory />} />
          <Route path="/ai-tasks/:runId/results" element={<AiTaskResults />} />
        </Route>
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/documents/favorites" element={<Favorites />} />
        <Route path="/documents/shared-with-me" element={<SharedWithMe />} />
        <Route path="/documents/org-library" element={<OrgLibrary />} />
        <Route path="/documents/collections" element={<Collections />} />
        <Route path="/documents/collections/:collectionId" element={<CollectionDetail />} />
        <Route path="/history" element={<SearchHistory />} />
        <Route path="/admin/system-health" element={<Monitoring />} />
        <Route path="/admin/users" element={<AdminUsers />} />
        <Route path="/admin/users/:userId/profile" element={<AdminUserProfile />} />
        <Route path="/admin/roles" element={<AdminRoles />} />
        <Route path="/admin/queries" element={<AdminQueries />} />
        <Route path="/admin/system-logs" element={<AdminSystemLogs />} />
        <Route path="/admin/settings" element={<AdminSettings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
