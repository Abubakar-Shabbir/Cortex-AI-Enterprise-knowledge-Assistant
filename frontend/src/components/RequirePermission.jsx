import { ShieldAlert } from 'lucide-react';
import { Outlet } from 'react-router-dom';
import { useSession } from '../auth/SessionContext';
import EmptyState from './EmptyState';

// Route-level permission gate, the page-rendering counterpart to
// Sidebar.jsx's has('<codename>') nav-visibility check - that only
// hides the link, it never stopped someone reaching the page directly
// by URL, so a page whose data all comes from a permission-gated API
// (e.g. AI Tasks) would otherwise render its full static UI before the
// first request ever 403s. Reads the same useSession().hasPermission()
// source of truth the sidebar does, so the two can't disagree.
export default function RequirePermission({ codename }) {
  const { hasPermission } = useSession();

  if (!hasPermission(codename)) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="You don't have access to this page"
        message="Ask a workspace admin to grant this permission if you think you should have it."
        actionTo="/"
        actionLabel="Back to Dashboard"
      />
    );
  }

  return <Outlet />;
}
