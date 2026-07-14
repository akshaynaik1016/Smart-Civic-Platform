import { NavLink, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, ClipboardList, Users, UserCheck,
  BarChart3, Map, FileText, Settings, LogOut, ChevronRight,
  Bell, Building2, Shield,
} from 'lucide-react';
import { cn, getInitials } from '../../utils/helpers';
import { useAuthStore } from '../../store/authStore';

const NAV_ITEMS = [
  { to: '/dashboard',      icon: LayoutDashboard, label: 'Dashboard',     roles: ['admin','officer'] },
  { to: '/complaints',     icon: ClipboardList,   label: 'Complaints',    roles: ['admin','officer'] },
  { to: '/map',            icon: Map,             label: 'Map & Heatmap', roles: ['admin','officer'] },
  { to: '/analytics',      icon: BarChart3,       label: 'Analytics',     roles: ['admin','officer'] },
  { to: '/officers',       icon: UserCheck,       label: 'Officers',      roles: ['admin']           },
  { to: '/users',          icon: Users,           label: 'Citizens',      roles: ['admin']           },
  { to: '/reports',        icon: FileText,        label: 'Reports',       roles: ['admin','officer'] },
  { to: '/settings',       icon: Settings,        label: 'Settings',      roles: ['admin']           },
];

export default function Sidebar() {
  const { user, logout } = useAuthStore();
  const navigate         = useNavigate();

  const visibleLinks = NAV_ITEMS.filter(item =>
    user ? item.roles.includes(user.role) : false
  );

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <aside className="fixed inset-y-0 left-0 z-40 flex flex-col"
           style={{ width: 'var(--sidebar-w)', background: 'var(--bg-sidebar)' }}>

      {/* ── Logo ───────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-5 py-5 border-b border-white/10">
        <div className="w-9 h-9 rounded-xl bg-brand-500 flex items-center justify-center flex-shrink-0">
          <Building2 size={20} className="text-white" />
        </div>
        <div>
          <p className="text-white font-bold text-sm leading-tight">Smart Civic</p>
          <p className="text-blue-300 text-2xs font-medium tracking-wide uppercase">
            Municipality Portal
          </p>
        </div>
      </div>

      {/* ── Nav ────────────────────────────────────────────────────── */}
      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
        {visibleLinks.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn('sidebar-link group', isActive && 'active')
            }
          >
            {({ isActive }) => (
              <>
                <Icon size={17} className={cn('flex-shrink-0', isActive ? 'text-white' : 'text-blue-300')} />
                <span className="flex-1 truncate">{label}</span>
                {isActive && (
                  <ChevronRight size={14} className="text-white/50 ml-auto" />
                )}
              </>
            )}
          </NavLink>
        ))}

        {/* ── Divider ─────────────────────────────────────────────── */}
        <div className="pt-3 mt-3 border-t border-white/10" />

        <button className="sidebar-link w-full">
          <Bell size={17} className="text-blue-300" />
          <span className="flex-1 text-left">Notifications</span>
          <span className="ml-auto bg-red-500 text-white text-2xs font-bold rounded-full px-1.5 py-0.5">
            3
          </span>
        </button>
      </nav>

      {/* ── User card ──────────────────────────────────────────────── */}
      <div className="px-3 pb-4 space-y-1 border-t border-white/10 pt-3">
        <div className="flex items-center gap-3 px-3 py-2.5 rounded-xl">
          <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center
                          text-white text-xs font-bold flex-shrink-0">
            {user ? getInitials(user.fullName) : 'U'}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-white text-xs font-semibold truncate">
              {user?.fullName ?? 'User'}
            </p>
            <p className="text-blue-300 text-2xs capitalize flex items-center gap-1">
              <Shield size={10} />
              {user?.role ?? 'officer'}
            </p>
          </div>
        </div>

        <button
          onClick={handleLogout}
          className="sidebar-link w-full text-red-300 hover:text-red-200 hover:bg-red-500/10"
        >
          <LogOut size={16} />
          <span>Sign out</span>
        </button>
      </div>
    </aside>
  );
}
