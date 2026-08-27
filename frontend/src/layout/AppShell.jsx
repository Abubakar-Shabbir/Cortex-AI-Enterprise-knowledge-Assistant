import { Suspense, useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Topbar from './Topbar';
import Breadcrumbs from './Breadcrumbs';
import PageSkeleton from '../components/PageSkeleton';
import usePageTitle from '../hooks/usePageTitle';

export default function AppShell() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  usePageTitle();

  return (
    <div className="min-h-screen flex">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="flex-1 min-w-0 flex flex-col lg:pl-64">
        <Topbar onOpenSidebar={() => setSidebarOpen(true)} />

        <main className="relative flex-1 px-4 sm:px-6 lg:px-8 py-6 lg:py-8 w-full max-w-[1600px] mx-auto">
          <Breadcrumbs />
          <Suspense
            fallback={<PageSkeleton variant="list" />}
          >
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}
