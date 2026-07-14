import { useQuery } from '@tanstack/react-query';
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import {
  ClipboardList, CheckCircle, Clock, AlertTriangle,
  Users, UserCheck, TrendingUp, Star,
} from 'lucide-react';
import { analyticsApi, complaintApi } from '../../services/api';
import {
  StatCard, StatusBadge, SeverityBadge, CategoryBadge,
  SectionCard, PageHeader, Avatar, Spinner,
} from '../../components/ui';
import {
  CHART_PALETTE, SEVERITY_CHART_COLORS, CATEGORY_META,
  fmtDate, fmtRelative, fmtNum, fmtPct, truncate,
} from '../../utils/helpers';
import type { SeverityLevel, IssueCategory } from '../../types';

const CUSTOM_TOOLTIP = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="card p-3 text-xs shadow-card-lg border border-[var(--border)]">
      <p className="font-semibold text-[var(--text-primary)] mb-1.5">{label}</p>
      {payload.map((p: any) => (
        <div key={p.name} className="flex items-center gap-2 mb-0.5">
          <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-[var(--text-muted)] capitalize">{p.name}:</span>
          <span className="font-semibold text-[var(--text-primary)]">{p.value}</span>
        </div>
      ))}
    </div>
  );
};

export default function DashboardPage() {
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn:  () => analyticsApi.dashboard().then(r => r.data),
    refetchInterval: 60_000,
  });

  const { data: trend } = useQuery({
    queryKey: ['monthly-trend'],
    queryFn:  () => analyticsApi.monthlyTrend(6).then(r => r.data),
  });

  const { data: categories } = useQuery({
    queryKey: ['category-counts'],
    queryFn:  () => analyticsApi.categoryCounts().then(r => r.data),
  });

  const { data: severities } = useQuery({
    queryKey: ['severity-dist'],
    queryFn:  () => analyticsApi.severityDistribution().then(r => r.data),
  });

  const { data: recentPage } = useQuery({
    queryKey: ['recent-complaints'],
    queryFn:  () => complaintApi.list({ pageSize: 8, sortBy: 'created_at', sortOrder: 'desc' }).then(r => r.data),
    refetchInterval: 30_000,
  });

  const { data: officerPerf } = useQuery({
    queryKey: ['officer-perf'],
    queryFn:  () => analyticsApi.wardSummary().then(r => r.data),
  });

  const recent = recentPage?.items ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="City Dashboard"
        subtitle="Real-time civic issue intelligence for Hubballi-Dharwad"
        actions={
          <div className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse-dot" />
            Updates every 60s
          </div>
        }
      />

      {/* ── KPI Cards ───────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Complaints"
          value={fmtNum(stats?.totalComplaints ?? 0)}
          change={stats?.changeVsPrevWeek.totalComplaints}
          icon={<ClipboardList size={20} className="text-brand-600" />}
          iconBg="bg-brand-50 dark:bg-brand-950"
          subtitle="All time"
          loading={statsLoading}
        />
        <StatCard
          title="Open Issues"
          value={fmtNum(stats?.openComplaints ?? 0)}
          change={stats?.changeVsPrevWeek.openComplaints}
          icon={<Clock size={20} className="text-amber-600" />}
          iconBg="bg-amber-50 dark:bg-amber-950"
          subtitle="Pending action"
          loading={statsLoading}
        />
        <StatCard
          title="Resolved Today"
          value={fmtNum(stats?.resolvedToday ?? 0)}
          change={stats?.changeVsPrevWeek.resolvedToday}
          icon={<CheckCircle size={20} className="text-emerald-600" />}
          iconBg="bg-emerald-50 dark:bg-emerald-950"
          subtitle="vs yesterday"
          loading={statsLoading}
        />
        <StatCard
          title="Avg. Resolution"
          value={`${stats?.avgResolutionDays?.toFixed(1) ?? '—'} days`}
          change={stats?.changeVsPrevWeek.avgResolutionDays}
          icon={<TrendingUp size={20} className="text-purple-600" />}
          iconBg="bg-purple-50 dark:bg-purple-950"
          subtitle="Time to close"
          loading={statsLoading}
        />
      </div>

      {/* ── Secondary stats ──────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="SLA Breach Rate"
          value={fmtPct(stats?.slaBreachRate ?? 0)}
          icon={<AlertTriangle size={20} className="text-red-500" />}
          iconBg="bg-red-50 dark:bg-red-950"
          loading={statsLoading}
        />
        <StatCard
          title="Citizen Satisfaction"
          value={`${(stats?.citizenSatisfaction ?? 0).toFixed(1)} / 5`}
          icon={<Star size={20} className="text-yellow-500" />}
          iconBg="bg-yellow-50 dark:bg-yellow-950"
          loading={statsLoading}
        />
        <StatCard
          title="Registered Citizens"
          value={fmtNum(stats?.totalCitizens ?? 0)}
          icon={<Users size={20} className="text-cyan-600" />}
          iconBg="bg-cyan-50 dark:bg-cyan-950"
          loading={statsLoading}
        />
        <StatCard
          title="Active Officers"
          value={stats?.activeOfficers ?? 0}
          icon={<UserCheck size={20} className="text-teal-600" />}
          iconBg="bg-teal-50 dark:bg-teal-950"
          loading={statsLoading}
        />
      </div>

      {/* ── Charts row 1 ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* Monthly trend area chart */}
        <SectionCard
          title="Complaint Trend"
          subtitle="Last 6 months"
          className="lg:col-span-2"
        >
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={trend ?? []} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
              <defs>
                <linearGradient id="submitted" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#1d4ed8" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#1d4ed8" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="resolved" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#10b981" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
              <Tooltip content={<CUSTOM_TOOLTIP />} />
              <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
              <Area type="monotone" dataKey="submitted" name="Submitted" stroke="#1d4ed8" strokeWidth={2} fill="url(#submitted)" dot={false} />
              <Area type="monotone" dataKey="resolved"  name="Resolved"  stroke="#10b981" strokeWidth={2} fill="url(#resolved)"  dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </SectionCard>

        {/* Severity pie */}
        <SectionCard title="Severity Distribution" subtitle="Current open issues">
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie
                data={severities ?? []}
                dataKey="count"
                nameKey="severity"
                cx="50%" cy="50%"
                innerRadius={48}
                outerRadius={78}
                paddingAngle={3}
              >
                {(severities ?? []).map((s) => (
                  <Cell
                    key={s.severity}
                    fill={SEVERITY_CHART_COLORS[s.severity as SeverityLevel]}
                  />
                ))}
              </Pie>
              <Tooltip content={<CUSTOM_TOOLTIP />} />
            </PieChart>
          </ResponsiveContainer>
          <div className="space-y-2 mt-1">
            {(severities ?? []).map(s => (
              <div key={s.severity} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full"
                    style={{ background: SEVERITY_CHART_COLORS[s.severity as SeverityLevel] }} />
                  <span className="capitalize font-medium text-[var(--text-primary)]">{s.severity}</span>
                </div>
                <span className="text-[var(--text-muted)]">
                  {s.count} <span className="text-2xs">({fmtPct(s.percentage, 0)})</span>
                </span>
              </div>
            ))}
          </div>
        </SectionCard>
      </div>

      {/* ── Charts row 2 ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* Category bar chart */}
        <SectionCard title="Issues by Category" subtitle="All time counts" className="lg:col-span-2">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart
              data={(categories ?? []).map(c => ({
                name:  CATEGORY_META[c.category as IssueCategory]?.label ?? c.category,
                count: c.count,
              }))}
              margin={{ top: 4, right: 4, bottom: 30, left: -20 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                angle={-35} textAnchor="end" interval={0} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
              <Tooltip content={<CUSTOM_TOOLTIP />} />
              <Bar dataKey="count" name="Reports" radius={[4, 4, 0, 0]}>
                {(categories ?? []).map((_, i) => (
                  <Cell key={i} fill={CHART_PALETTE[i % CHART_PALETTE.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </SectionCard>

        {/* Top categories list */}
        <SectionCard title="Top Issues" subtitle="By complaint volume">
          <div className="space-y-3">
            {(categories ?? []).slice(0, 5).map((c, i) => {
              const meta  = CATEGORY_META[c.category as IssueCategory];
              const pct   = c.percentage;
              return (
                <div key={c.category}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium text-[var(--text-primary)] flex items-center gap-1.5">
                      <span>{meta?.emoji}</span>
                      {meta?.label ?? c.category}
                    </span>
                    <span className="text-xs text-[var(--text-muted)]">{c.count}</span>
                  </div>
                  <div className="w-full h-1.5 bg-slate-100 dark:bg-brand-900 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-700"
                      style={{ width: `${pct}%`, background: CHART_PALETTE[i % CHART_PALETTE.length] }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </SectionCard>
      </div>

      {/* ── Recent Complaints table ──────────────────────────────────── */}
      <SectionCard
        title="Recent Reports"
        subtitle="Latest citizen submissions"
        actions={
          <a href="/complaints" className="btn-ghost text-xs">View all →</a>
        }
      >
        <div className="overflow-x-auto -mx-5 px-5">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border)]">
                {['ID', 'Title', 'Category', 'Severity', 'Status', 'Citizen', 'Submitted'].map(h => (
                  <th key={h} className="label text-left py-3 pr-4 whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recent.length === 0 ? (
                <tr><td colSpan={7} className="py-12 text-center text-[var(--text-muted)] text-sm">
                  No recent complaints
                </td></tr>
              ) : recent.map(c => (
                <tr key={c.id} className="table-row">
                  <td className="py-3 pr-4 font-mono text-xs text-[var(--text-muted)] whitespace-nowrap">
                    {c.complaintNumber}
                  </td>
                  <td className="py-3 pr-4 max-w-[180px]">
                    <a href={`/complaints/${c.id}`} className="font-medium text-[var(--text-primary)] hover:text-brand-600 transition-colors line-clamp-1">
                      {truncate(c.title, 40)}
                    </a>
                    {c.address && (
                      <p className="text-2xs text-[var(--text-muted)] mt-0.5 truncate">{c.address}</p>
                    )}
                  </td>
                  <td className="py-3 pr-4 whitespace-nowrap">
                    <CategoryBadge category={c.category} />
                  </td>
                  <td className="py-3 pr-4">
                    <SeverityBadge severity={c.severity} />
                  </td>
                  <td className="py-3 pr-4 whitespace-nowrap">
                    <StatusBadge status={c.status} />
                  </td>
                  <td className="py-3 pr-4">
                    <div className="flex items-center gap-2">
                      <Avatar name={c.citizen.fullName} url={c.citizen.avatarUrl} size={6} />
                      <span className="text-xs text-[var(--text-muted)] truncate max-w-[100px]">
                        {c.citizen.fullName}
                      </span>
                    </div>
                  </td>
                  <td className="py-3 pr-4 text-xs text-[var(--text-muted)] whitespace-nowrap">
                    {fmtRelative(c.createdAt)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}
