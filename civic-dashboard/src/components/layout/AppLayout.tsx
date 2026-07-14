import { Outlet, useLocation } from 'react-router-dom';
import { Search, Moon, Sun, RefreshCw } from 'lucide-react';
import { useState, useEffect } from 'react';
import Sidebar from './Sidebar';
import { cn } from '../../utils/helpers';

const PAGE_TITLES: Record<string, string> = {
  '/dashboard':  'Dashboard',
  '/complaints': 'Complaint Management',
  '/map':        'Map & Heatmap',
  '/analytics':  'Analytics',
  '/officers':   'Officer Management',
  '/users':      'Citizen Management',
  '/reports':    'Reports',
  '/settings':   'Settings',
};

export default function AppLayout() {
  const [dark,        setDark]        = useState(() => localStorage.getItem('theme') === 'dark');
  const [searchOpen,  setSearchOpen]  = useState(false);
  const location = useLocation();
  const title    = PAGE_TITLES[location.pathname] ?? 'Smart Civic';

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    localStorage.setItem('theme', dark ? 'dark' : 'light');
  }, [dark]);

  return (
    <div className="min-h-screen flex" style={{ background: 'var(--bg-page)' }}>
      <Sidebar />

      {/* ── Main ──────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col" style={{ marginLeft: 'var(--sidebar-w)' }}>

        {/* ── Top header ─────────────────────────────────────────── */}
        <header
          className="sticky top-0 z-30 flex items-center gap-4 px-6 border-b border-[var(--border)]"
          style={{ height: 'var(--header-h)', background: 'var(--bg-card)' }}
        >
          {/* Breadcrumb / title */}
          <div className="flex-1">
            <h1 className="text-[15px] font-semibold text-[var(--text-primary)]">{title}</h1>
          </div>

          {/* Search bar */}
          <div className={cn(
            'flex items-center gap-2 px-3.5 py-2 rounded-xl border border-[var(--border)]',
            'bg-slate-50 dark:bg-brand-900 text-sm text-[var(--text-muted)]',
            'transition-all duration-200',
            searchOpen ? 'w-72' : 'w-44 cursor-pointer'
          )}
          onClick={() => setSearchOpen(true)}
          onBlur={() => setSearchOpen(false)}
          >
            <Search size={15} className="flex-shrink-0" />
            <input
              className="bg-transparent outline-none w-full text-[var(--text-primary)] placeholder:text-[var(--text-muted)]"
              placeholder="Search complaints…"
              onFocus={() => setSearchOpen(true)}
            />
            <kbd className="hidden sm:inline-flex text-2xs border border-[var(--border)] rounded px-1 py-0.5 font-mono text-[var(--text-muted)]">
              ⌘K
            </kbd>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-1">
            <button
              className="btn-ghost"
              title="Refresh data"
              onClick={() => window.location.reload()}
            >
              <RefreshCw size={16} />
            </button>
            <button className="btn-ghost" onClick={() => setDark(!dark)}>
              {dark ? <Sun size={16} /> : <Moon size={16} />}
            </button>

            {/* Live indicator */}
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-50 dark:bg-emerald-950
                            border border-emerald-200 dark:border-emerald-800">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse-dot" />
              <span className="text-2xs font-semibold text-emerald-700 dark:text-emerald-400 uppercase tracking-wide">
                Live
              </span>
            </div>
          </div>
        </header>

        {/* ── Page content ───────────────────────────────────────── */}
        <main className="flex-1 p-6 overflow-auto animate-in">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
