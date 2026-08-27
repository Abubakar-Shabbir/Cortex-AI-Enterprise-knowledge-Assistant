import { useEffect } from 'react';
import { matchPath, useLocation } from 'react-router-dom';

// Route pattern -> tab title, mirroring App.jsx's route list and
// Breadcrumbs.jsx's BREADCRUMB_MAP in spirit. Patterns use the same
// `:param` syntax as the <Route path> they title, so a dynamic segment
// (an entity id, a run id, ...) doesn't need its own literal entry -
// react-router's own matchPath() resolves it the same way the router
// itself does, rather than re-implementing path matching by hand.
const TITLE_ROUTES = [
  ['/', 'Dashboard'],
  ['/documents/favorites', 'Favorites'],
  ['/documents/shared-with-me', 'Shared With Me'],
  ['/documents/org-library', 'Organization Library'],
  ['/documents/collections/:collectionId', 'Collection'],
  ['/documents/collections', 'Collections'],
  ['/documents', 'Documents'],
  ['/ask', 'Ask AI'],
  ['/profile', 'Profile'],
  ['/notifications', 'Notifications'],
  ['/knowledge/relationships', 'Relationships'],
  ['/knowledge/graph', 'Knowledge Graph'],
  ['/knowledge/insights', 'Insights'],
  ['/knowledge/citations', 'Citations'],
  ['/knowledge/entities/:entityId', 'Entity'],
  ['/knowledge/documents/:docId', 'Document Knowledge'],
  ['/knowledge', 'Knowledge Base'],
  ['/ai-tasks/history', 'AI Task History'],
  ['/ai-tasks/:runId/results', 'AI Task Results'],
  ['/ai-tasks', 'AI Tasks'],
  ['/analytics', 'Analytics'],
  ['/reports', 'Reports'],
  ['/history', 'Search History'],
  ['/admin/system-health', 'System Health'],
  ['/admin/users/:userId/profile', 'User Profile'],
  ['/admin/users', 'Users'],
  ['/admin/roles', 'Roles'],
  ['/admin/queries', 'Queries'],
  ['/admin/system-logs', 'System Logs'],
  ['/admin/settings', 'Settings'],
];

// Called once from AppShell so every authenticated route gets a
// correct tab title without each page component needing its own
// title effect - pre-auth pages (Login/Signup/...) already get this
// from AuthLayout's identical document.title pattern.
export default function usePageTitle() {
  const location = useLocation();

  useEffect(() => {
    const match = TITLE_ROUTES.find(([pattern]) =>
      matchPath({ path: pattern, end: true }, location.pathname)
    );
    document.title = match ? `${match[1]} · Cortex` : 'Cortex';
  }, [location.pathname]);
}
