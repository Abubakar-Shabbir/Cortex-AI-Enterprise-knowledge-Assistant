import { Link, useLocation } from 'react-router-dom';

// Port of templates/dashboard/_nav_item.html. `to` is an internal SPA
// route (React Router Link, no full page reload); `href` is used
// instead for a page this migration hasn't ported yet, so it still
// navigates (full reload) straight to the working classic Django page
// rather than a dead link or a fake placeholder.
export default function NavItem({ to, href, icon: Icon, label, activeMatch }) {
  const location = useLocation();
  const isActive = to ? (activeMatch ? location.pathname.startsWith(activeMatch) : location.pathname === to) : false;

  const className = `flex items-center gap-3 rounded-lg px-3 py-2.5 font-medium transition-all duration-150 ease-out ${
    isActive
      ? 'bg-white/[0.08] text-white shadow-[inset_2.5px_0_0_0_#E7C8CC]'
      : 'text-muted-dark hover:bg-white/[0.05] hover:text-white'
  }`;
  const iconClassName = `h-4 w-4 shrink-0 ${isActive ? 'text-primary-soft' : ''}`;

  if (to) {
    return (
      <Link to={to} className={className}>
        <Icon className={iconClassName} /> {label}
      </Link>
    );
  }

  return (
    <a href={href} className={className}>
      <Icon className={iconClassName} /> {label}
    </a>
  );
}
