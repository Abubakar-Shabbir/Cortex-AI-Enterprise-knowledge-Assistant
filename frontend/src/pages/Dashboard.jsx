import { useSession } from '../auth/SessionContext';
import AdminOverview from './dashboard/AdminOverview';
import UserOverview from './dashboard/UserOverview';

// Mirrors RAG.services.permission_service.get_dashboard_url_for_user:
// an account with admin-area access lands on Admin Overview (KPI
// trend charts, Documents Over Time, Document Types, System Status -
// templates/dashboard.html), everyone else on the simpler, chart-free
// User Overview (templates/user_dashboard.html). Both are reachable at
// the same "/" route here since the SPA doesn't yet port the classic
// app's separate /admin/ shell.
export default function Dashboard() {
  const { canViewAdminArea } = useSession();
  return canViewAdminArea ? <AdminOverview /> : <UserOverview />;
}
