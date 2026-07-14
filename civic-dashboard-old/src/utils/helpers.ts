import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { formatDistanceToNow, format, parseISO } from 'date-fns';
import type { ComplaintStatus, SeverityLevel, IssueCategory } from '../types';

// ─── Classname helper ─────────────────────────────────────────────────────────

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));

// ─── Status helpers ───────────────────────────────────────────────────────────

export const STATUS_LABELS: Record<ComplaintStatus, string> = {
  submitted:      'Submitted',
  ai_processing:  'AI Processing',
  pending_review: 'Pending Review',
  assigned:       'Assigned',
  in_progress:    'In Progress',
  resolved:       'Resolved',
  verified:       'Verified',
  closed:         'Closed',
  rejected:       'Rejected',
};

export const STATUS_COLORS: Record<ComplaintStatus, { bg: string; text: string; dot: string }> = {
  submitted:      { bg: 'bg-gray-100',    text: 'text-gray-600',   dot: 'bg-gray-400'   },
  ai_processing:  { bg: 'bg-blue-50',     text: 'text-blue-600',   dot: 'bg-blue-500'   },
  pending_review: { bg: 'bg-blue-50',     text: 'text-blue-700',   dot: 'bg-blue-600'   },
  assigned:       { bg: 'bg-purple-50',   text: 'text-purple-700', dot: 'bg-purple-500' },
  in_progress:    { bg: 'bg-amber-50',    text: 'text-amber-700',  dot: 'bg-amber-500'  },
  resolved:       { bg: 'bg-emerald-50',  text: 'text-emerald-700',dot: 'bg-emerald-500'},
  verified:       { bg: 'bg-cyan-50',     text: 'text-cyan-700',   dot: 'bg-cyan-500'   },
  closed:         { bg: 'bg-slate-100',   text: 'text-slate-600',  dot: 'bg-slate-400'  },
  rejected:       { bg: 'bg-red-50',      text: 'text-red-700',    dot: 'bg-red-500'    },
};

export const SEVERITY_COLORS: Record<SeverityLevel, { bg: string; text: string; border: string }> = {
  low:      { bg: 'bg-green-50',  text: 'text-green-700',  border: 'border-green-200'  },
  medium:   { bg: 'bg-amber-50',  text: 'text-amber-700',  border: 'border-amber-200'  },
  high:     { bg: 'bg-orange-50', text: 'text-orange-700', border: 'border-orange-200' },
  critical: { bg: 'bg-red-50',    text: 'text-red-700',    border: 'border-red-200'    },
};

export const CATEGORY_META: Record<IssueCategory, { label: string; emoji: string; color: string }> = {
  pothole:             { label: 'Pothole',           emoji: '🕳️',  color: '#bf360c' },
  garbage:             { label: 'Garbage Dump',      emoji: '🗑️',  color: '#558b2f' },
  water_leakage:       { label: 'Water Leakage',     emoji: '💧',  color: '#0277bd' },
  open_manhole:        { label: 'Open Manhole',      emoji: '🔓',  color: '#4a148c' },
  broken_streetlight:  { label: 'Broken Streetlight',emoji: '💡',  color: '#f57f17' },
  fallen_tree:         { label: 'Fallen Tree',       emoji: '🌳',  color: '#1b5e20' },
  damaged_road_sign:   { label: 'Damaged Road Sign', emoji: '🚧',  color: '#b71c1c' },
  illegal_dumping:     { label: 'Illegal Dumping',   emoji: '⚠️',  color: '#37474f' },
  other:               { label: 'Other',             emoji: '📍',  color: '#455a64' },
};

// ─── Chart colors ─────────────────────────────────────────────────────────────

export const CHART_PALETTE = [
  '#1d4ed8', '#00897b', '#f59e0b', '#ef4444',
  '#8b5cf6', '#06b6d4', '#ec4899', '#84cc16',
  '#f97316', '#6366f1',
];

export const SEVERITY_CHART_COLORS: Record<SeverityLevel, string> = {
  low:      '#16a34a',
  medium:   '#d97706',
  high:     '#ea580c',
  critical: '#dc2626',
};

// ─── Date formatters ──────────────────────────────────────────────────────────

export const fmtDate    = (d: string) => format(parseISO(d), 'dd MMM yyyy');
export const fmtDateTime= (d: string) => format(parseISO(d), 'dd MMM yyyy, HH:mm');
export const fmtRelative= (d: string) => formatDistanceToNow(parseISO(d), { addSuffix: true });

// ─── Number formatters ────────────────────────────────────────────────────────

export const fmtNum = (n: number) =>
  n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M`
  : n >= 1_000   ? `${(n / 1_000).toFixed(1)}K`
  : String(n);

export const fmtPct = (n: number, decimals = 1) => `${n.toFixed(decimals)}%`;

export const fmtCurrency = (n: number) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n);

// ─── SLA helpers ──────────────────────────────────────────────────────────────

export const slaStatus = (deadline?: string, resolved?: boolean): 'on_track' | 'at_risk' | 'breached' | 'resolved' => {
  if (resolved) return 'resolved';
  if (!deadline) return 'on_track';
  const now  = new Date();
  const due  = parseISO(deadline);
  const diff = due.getTime() - now.getTime();
  if (diff < 0)          return 'breached';
  if (diff < 4 * 3600_000) return 'at_risk';
  return 'on_track';
};

// ─── Misc ─────────────────────────────────────────────────────────────────────

export const getInitials = (name: string) =>
  name.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase();

export const truncate = (s: string, max = 60) =>
  s.length > max ? `${s.slice(0, max)}…` : s;

export const changeArrow = (n: number) => (n >= 0 ? '↑' : '↓');
export const changeColor  = (n: number) => n >= 0 ? 'text-emerald-600' : 'text-red-500';
