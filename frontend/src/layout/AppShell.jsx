import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Topbar from './Topbar';
import Breadcrumbs from './Breadcrumbs';

// Port of templates/base.html's shell: ONE sidebar, ONE topbar for
// every authenticated page, exactly like the Django version - only the
// routed page content (Outlet) changes.
export default function AppShell() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen flex">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="flex-1 min-w-0 flex flex-col lg:pl-64">
        <Topbar onOpenSidebar={() => setSidebarOpen(true)} />

        <main className="flex-1 px-4 sm:px-6 lg:px-8 py-6 lg:py-8 w-full max-w-[1600px] mx-auto">
          <Breadcrumbs />
          <Outlet />
        </main>
      </div>
    </div>
  );
}
