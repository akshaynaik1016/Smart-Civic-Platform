import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ComposedChart, Bar, Line, BarChart, RadialBarChart, RadialBar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, Cell,
  ResponsiveContainer, PieChart, Pie,
} from 'recharts';
import { TrendingUp, Award, Clock, Target, Download } from 'lucide-react';
import { analyticsApi } from '../../services/api';
import {
  PageHeader, SectionCard, StatCard, ProgressBar,
} from '../../components/ui';
import {
  CHART_PALETTE, CATEGORY_META, SEVERITY_CHART_COLORS,
  fmtPct, fmtNum, cn,
} from '../../utils/helpers';
import type { IssueCategory, SeverityLevel } from '../../types';

const PERIOD_OPTIONS = [
  { label: '7 days',   months: 1  },
  { label: '3 months', months: 3  },
  { label: '6 months', months: 6  },
  { label: '1 year',   months: 12 },
];

const CUSTOM_TOOLTIP = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="card p-3 text-xs shadow-card-lg">
      <p className="font-semibold mb-1.5">{label}</p>
      {payload.map((p: any) => (
        <div key={p.name} className="flex items-center gap-2 mb-0.5">
          <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-[var(--text-muted)] capitalize">{p.name}:</span>
          <span className="font-semibold">{typeof p.value === 'number' ? p.value.toLocaleString() : p.value}</span>
        </div>
      ))}
    </div>
  );
};

export default function AnalyticsPage() {
  const [months, setMonths] = useState(6);

  const { data: trend }     = useQuery({ queryKey: ['trend', months], queryFn: () => analyticsApi.monthlyTrend(months).then(r => r.data) });
  const { data: categories} = useQuery({ queryKey: ['categories'],   queryFn: () => analyticsApi.categoryCounts().then(r => r.data) });
  const { data: wards }     = useQuery({ queryKey: ['wards'],        queryFn: () => analyticsApi.wardSummary().then(r => r.data) });
  const { data: severity }  = useQuery({ queryKey: ['severity'],     queryFn: () => analyticsApi.severityDistribution().then(r => r.data) });
  const { data: officers }  = useQuery({ queryKey: ['officer-perf'], queryFn: () => analyticsApi.performance().then(r => r.data) });
  const { data: stats }     = useQuery({ queryKey: ['dashboard-stats'], queryFn: () => analyticsApi.dashboard().then(r => r.data) });

  // Compute resolution rate from trend
  const totalSubmitted = trend?.reduce((s, t) => s + t.submitted, 0) ?? 0;
  const totalResolved  = trend?.reduce((s, t) => s + t.resolved,  0) ?? 0;
  const resolutionRate = totalSubmitted > 0 ? (totalResolved / totalSubmitted) * 100 : 0;

  // Category enriched for chart
  const categoryData = (categories ?? []).map(c => ({
    name:       CATEGORY_META[c.category as IssueCategory]?.label ?? c.category,
    emoji:      CATEGORY_META[c.category as IssueCategory]?.emoji,
    submitted:  c.count,
    resolved:   c.resolved,
    pending:    c.pending,
    rate:       c.count > 0 ? Math.round((c.resolved / c.count) * 100) : 0,
  }));

  // Ward data
  const wardData = (wards ?? []).slice(0, 10).map(w => ({
    name:     w.wardName,
    total:    w.totalComplaints,
    resolved: w.resolved,
    pending:  w.pending,
    rate:     Math.round(w.resolutionRate),
  }));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Analytics"
        subtitle="Civic performance metrics and trend analysis"
        actions={
          <div className="flex items-center gap-1.5 border border-[var(--border)] rounded-xl p-1">
            {PERIOD_OPTIONS.map(o => (
              <button
                key={o.months}
                onClick={() => setMonths(o.months)}
                className={cn(
                  'px-3 py-1.5 rounded-lg text-xs font-semibold transition-all',
                  months === o.months
                    ? 'bg-brand-600 text-white'
                    : 'text-[var(--text-muted)] hover:bg-slate-100 dark:hover:bg-brand-900'
                )}
              >
                {o.label}
              </button>
            ))}
          </div>
        }
      />

      {/* ── KPI overview ──────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Resolution Rate"
          value={fmtPct(resolutionRate)}
          icon={<Target size={20} className="text-brand-600" />}
          iconBg="bg-brand-50 dark:bg-brand-950"
          subtitle="Complaints closed vs submitted"
        />
        <StatCard
          title="Avg. Resolution"
          value={`${stats?.avgResolutionDays?.toFixed(1) ?? '—'} days`}
          icon={<Clock size={20} className="text-amber-600" />}
          iconBg="bg-amber-50 dark:bg-amber-950"
          subtitle="Time to resolve"
        />
        <StatCard
          title="SLA Compliance"
          value={fmtPct(100 - (stats?.slaBreachRate ?? 0))}
          icon={<Award size={20} className="text-emerald-600" />}
          iconBg="bg-emerald-50 dark:bg-emerald-950"
          subtitle="Within SLA deadline"
        />
        <StatCard
          title="Citizen Satisfaction"
          value={`${(stats?.citizenSatisfaction ?? 0).toFixed(2)}/5`}
          icon={<TrendingUp size={20} className="text-purple-600" />}
          iconBg="bg-purple-50 dark:bg-purple-950"
          subtitle="Average rating"
        />
      </div>

      {/* ── Monthly trend composed chart ──────────────────────────────── */}
      <SectionCard title="Monthly Trend" subtitle="Submission vs resolution over time">
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart data={trend ?? []} margin={{ top: 4, right: 8, bottom: 0, left: -10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
            <YAxis yAxisId="left"  tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
            <Tooltip content={<CUSTOM_TOOLTIP />} />
            <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
            <Bar yAxisId="left" dataKey="submitted" name="Submitted" fill="#bfdbfe" radius={[3,3,0,0]} />
            <Bar yAxisId="left" dataKey="resolved"  name="Resolved"  fill="#1d4ed8" radius={[3,3,0,0]} />
            <Line yAxisId="right" type="monotone" dataKey="pending" name="Pending" stroke="#f59e0b" strokeWidth={2.5} dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </SectionCard>

      {/* ── Category analysis ─────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SectionCard title="Category Breakdown" subtitle="Submitted vs resolved per issue type">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={categoryData} layout="vertical" margin={{ left: 10, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
              <YAxis dataKey="name" type="category" width={120} tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
              <Tooltip content={<CUSTOM_TOOLTIP />} />
              <Legend iconType="square" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="submitted" name="Submitted" fill="#bfdbfe" radius={[0,3,3,0]} />
              <Bar dataKey="resolved"  name="Resolved"  fill="#1d4ed8" radius={[0,3,3,0]} />
            </BarChart>
          </ResponsiveContainer>
        </SectionCard>

        {/* Category resolution rates */}
        <SectionCard title="Resolution Rates by Category" subtitle="% of complaints closed">
          <div className="space-y-4">
            {categoryData.slice(0, 8).map((c, i) => (
              <div key={c.name}>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-medium flex items-center gap-1.5">
                    <span>{c.emoji}</span>
                    <span className="text-[var(--text-primary)]">{c.name}</span>
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-[var(--text-muted)]">{c.resolved}/{c.submitted}</span>
                    <span className={cn(
                      'text-xs font-bold',
                      c.rate >= 80 ? 'text-emerald-600' : c.rate >= 50 ? 'text-amber-600' : 'text-red-500'
                    )}>
                      {c.rate}%
                    </span>
                  </div>
                </div>
                <ProgressBar
                  value={c.rate}
                  color={c.rate >= 80 ? 'bg-emerald-500' : c.rate >= 50 ? 'bg-amber-500' : 'bg-red-500'}
                />
              </div>
            ))}
          </div>
        </SectionCard>
      </div>

      {/* ── Ward analysis ─────────────────────────────────────────────── */}
      <SectionCard title="Ward-Level Analysis" subtitle="Top 10 wards by complaint volume">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={wardData} margin={{ top: 4, right: 4, bottom: 20, left: -10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                angle={-30} textAnchor="end" interval={0} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
              <Tooltip content={<CUSTOM_TOOLTIP />} />
              <Legend iconType="square" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="total"    name="Total"    fill="#e0e7ff" radius={[3,3,0,0]} />
              <Bar dataKey="resolved" name="Resolved" fill="#4f46e5" radius={[3,3,0,0]} />
              <Bar dataKey="pending"  name="Pending"  fill="#f59e0b" radius={[3,3,0,0]} />
            </BarChart>
          </ResponsiveContainer>

          {/* Ward table */}
          <div className="overflow-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[var(--border)]">
                  <th className="label text-left py-2 pr-3">Ward</th>
                  <th className="label text-right py-2 pr-3">Total</th>
                  <th className="label text-right py-2 pr-3">Resolved</th>
                  <th className="label text-right py-2">Rate</th>
                </tr>
              </thead>
              <tbody>
                {wardData.map(w => (
                  <tr key={w.name} className="table-row">
                    <td className="py-2.5 pr-3 font-medium text-[var(--text-primary)]">{w.name}</td>
                    <td className="py-2.5 pr-3 text-right text-[var(--text-muted)]">{w.total}</td>
                    <td className="py-2.5 pr-3 text-right text-[var(--text-muted)]">{w.resolved}</td>
                    <td className="py-2.5 text-right">
                      <span className={cn(
                        'font-bold',
                        w.rate >= 80 ? 'text-emerald-600' : w.rate >= 50 ? 'text-amber-600' : 'text-red-500'
                      )}>
                        {w.rate}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </SectionCard>

      {/* ── Officer performance table ─────────────────────────────────── */}
      <SectionCard title="Officer Performance" subtitle="Resolution metrics by officer">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border)]">
                {['Officer', 'Badge', 'Assigned', 'Resolved', 'Avg Days', 'Score', 'Rating'].map(h => (
                  <th key={h} className="label text-left py-3 pr-4 whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(officers ?? []).map((o, i) => (
                <tr key={o.officerId} className="table-row">
                  <td className="py-3 pr-4">
                    <div className="flex items-center gap-2">
                      <div className={cn(
                        'w-6 h-6 rounded-full flex items-center justify-center text-white text-2xs font-bold',
                        i === 0 ? 'bg-yellow-500' : i === 1 ? 'bg-slate-400' : i === 2 ? 'bg-amber-700' : 'bg-slate-200 text-slate-600'
                      )}>
                        {i < 3 ? ['🥇','🥈','🥉'][i] : i+1}
                      </div>
                      <span className="font-medium text-[var(--text-primary)]">{o.officerName}</span>
                    </div>
                  </td>
                  <td className="py-3 pr-4 font-mono text-xs text-[var(--text-muted)]">{o.badgeNumber}</td>
                  <td className="py-3 pr-4 text-[var(--text-muted)]">{o.totalAssigned}</td>
                  <td className="py-3 pr-4 text-[var(--text-muted)]">{o.totalResolved}</td>
                  <td className="py-3 pr-4 text-[var(--text-muted)]">{o.avgResolutionDays?.toFixed(1) ?? '—'}</td>
                  <td className="py-3 pr-4">
                    <div className="flex items-center gap-2">
                      <ProgressBar value={o.performanceScore} color="bg-brand-600" className="w-20" />
                      <span className="text-xs font-bold text-brand-600">{o.performanceScore}%</span>
                    </div>
                  </td>
                  <td className="py-3 pr-4">
                    <span className="text-xs font-semibold text-amber-600">
                      ⭐ {o.satisfactionRating?.toFixed(1) ?? '—'}
                    </span>
                  </td>
                </tr>
              ))}
              {!officers?.length && (
                <tr><td colSpan={7} className="py-10 text-center text-[var(--text-muted)] text-sm">
                  No officer data available
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}
