import { cn, STATUS_COLORS, STATUS_LABELS, SEVERITY_COLORS, CATEGORY_META, getInitials, changeArrow, changeColor } from '../../utils/helpers';
import type { ComplaintStatus, SeverityLevel, IssueCategory } from '../../types';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

// ─── StatusBadge ──────────────────────────────────────────────────────────────

export function StatusBadge({ status, size = 'sm' }: { status: ComplaintStatus; size?: 'xs' | 'sm' }) {
  const c = STATUS_COLORS[status];
  return (
    <span className={cn(
      'badge gap-1.5',
      c.bg, c.text,
      size === 'xs' ? 'text-[10px] px-2 py-0.5' : 'text-2xs'
    )}>
      <span className={cn('w-1.5 h-1.5 rounded-full flex-shrink-0', c.dot)} />
      {STATUS_LABELS[status]}
    </span>
  );
}

// ─── SeverityBadge ────────────────────────────────────────────────────────────

export function SeverityBadge({ severity }: { severity: SeverityLevel }) {
  const c = SEVERITY_COLORS[severity];
  return (
    <span className={cn('badge border', c.bg, c.text, c.border)}>
      {severity.toUpperCase()}
    </span>
  );
}

// ─── CategoryBadge ────────────────────────────────────────────────────────────

export function CategoryBadge({ category }: { category: IssueCategory }) {
  const m = CATEGORY_META[category];
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-brand-900
                     text-2xs font-semibold text-slate-700 dark:text-slate-300">
      <span>{m.emoji}</span>
      {m.label}
    </span>
  );
}

// ─── StatCard ─────────────────────────────────────────────────────────────────

interface StatCardProps {
  title:      string;
  value:      string | number;
  change?:    number;
  icon:       React.ReactNode;
  iconBg?:    string;
  subtitle?:  string;
  loading?:   boolean;
}

export function StatCard({ title, value, change, icon, iconBg = 'bg-brand-50 dark:bg-brand-900', subtitle, loading }: StatCardProps) {
  if (loading) {
    return (
      <div className="card p-5">
        <div className="flex items-start justify-between mb-4">
          <div className="w-10 h-10 rounded-xl bg-slate-100 dark:bg-brand-900 animate-pulse" />
          <div className="w-16 h-5 rounded-lg bg-slate-100 dark:bg-brand-900 animate-pulse" />
        </div>
        <div className="w-24 h-8 rounded-lg bg-slate-100 dark:bg-brand-900 animate-pulse mb-2" />
        <div className="w-32 h-4 rounded-lg bg-slate-100 dark:bg-brand-900 animate-pulse" />
      </div>
    );
  }

  return (
    <div className="card card-hover p-5 group transition-all duration-200 hover:-translate-y-0.5">
      <div className="flex items-start justify-between mb-3">
        <div className={cn('w-10 h-10 rounded-xl flex items-center justify-center', iconBg)}>
          {icon}
        </div>
        {change !== undefined && (
          <div className={cn('flex items-center gap-1 text-xs font-semibold', changeColor(change))}>
            {change > 0 ? <TrendingUp size={13} />
             : change < 0 ? <TrendingDown size={13} />
             : <Minus size={13} />}
            {Math.abs(change).toFixed(1)}%
          </div>
        )}
      </div>
      <p className="stat-number mb-0.5">{value}</p>
      <p className="text-sm font-semibold text-[var(--text-primary)]">{title}</p>
      {subtitle && (
        <p className="text-2xs text-[var(--text-muted)] mt-1">{subtitle}</p>
      )}
    </div>
  );
}

// ─── Avatar ───────────────────────────────────────────────────────────────────

export function Avatar({ name, url, size = 8 }: { name: string; url?: string; size?: number }) {
  if (url) {
    return (
      <img
        src={url} alt={name}
        className={cn(`w-${size} h-${size}`, 'rounded-full object-cover')}
      />
    );
  }
  return (
    <div className={cn(
      `w-${size} h-${size}`, 'rounded-full flex items-center justify-center',
      'bg-brand-100 dark:bg-brand-800 text-brand-700 dark:text-brand-200',
      'text-xs font-bold flex-shrink-0',
    )}>
      {getInitials(name)}
    </div>
  );
}

// ─── Spinner ──────────────────────────────────────────────────────────────────

export function Spinner({ size = 6, className }: { size?: number; className?: string }) {
  return (
    <div className={cn(`w-${size} h-${size}`, 'border-2 border-brand-200 border-t-brand-600 rounded-full animate-spin', className)} />
  );
}

// ─── EmptyState ───────────────────────────────────────────────────────────────

export function EmptyState({
  icon, title, description, action,
}: {
  icon:        React.ReactNode;
  title:       string;
  description: string;
  action?:     React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-16 h-16 rounded-2xl bg-slate-100 dark:bg-brand-900 flex items-center justify-center mb-4 text-2xl">
        {icon}
      </div>
      <h3 className="text-base font-semibold text-[var(--text-primary)] mb-1">{title}</h3>
      <p className="text-sm text-[var(--text-muted)] max-w-sm">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

// ─── PageHeader ───────────────────────────────────────────────────────────────

export function PageHeader({
  title, subtitle, actions,
}: {
  title:    string;
  subtitle?: string;
  actions?:  React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between mb-6">
      <div>
        <h1 className="text-xl font-bold text-[var(--text-primary)] tracking-tight">{title}</h1>
        {subtitle && (
          <p className="text-sm text-[var(--text-muted)] mt-0.5">{subtitle}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

// ─── SectionCard ─────────────────────────────────────────────────────────────

export function SectionCard({
  title, subtitle, actions, children, className,
}: {
  title?:    string;
  subtitle?: string;
  actions?:  React.ReactNode;
  children:  React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('card', className)}>
      {(title || actions) && (
        <div className="flex items-center justify-between px-5 pt-5 pb-4 border-b border-[var(--border)]">
          <div>
            {title && <h3 className="section-title">{title}</h3>}
            {subtitle && <p className="text-xs text-[var(--text-muted)] mt-0.5">{subtitle}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className="p-5">{children}</div>
    </div>
  );
}

// ─── Progress bar ─────────────────────────────────────────────────────────────

export function ProgressBar({ value, max = 100, color = 'bg-brand-600', className }: {
  value: number; max?: number; color?: string; className?: string;
}) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div className={cn('w-full h-1.5 bg-slate-100 dark:bg-brand-900 rounded-full overflow-hidden', className)}>
      <div
        className={cn('h-full rounded-full transition-all duration-500', color)}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
