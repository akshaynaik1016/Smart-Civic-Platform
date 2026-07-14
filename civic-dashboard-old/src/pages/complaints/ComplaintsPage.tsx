import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Search, Filter, Download, RefreshCw, ChevronLeft, ChevronRight,
  Eye, UserCheck, X, CheckCircle, AlertOctagon, SlidersHorizontal,
} from 'lucide-react';
import { complaintApi, officerApi } from '../../services/api';
import {
  StatusBadge, SeverityBadge, CategoryBadge,
  PageHeader, SectionCard, Avatar, EmptyState, Spinner,
} from '../../components/ui';
import {
  STATUS_LABELS, CATEGORY_META, cn, fmtDateTime, fmtRelative, truncate,
} from '../../utils/helpers';
import type { Complaint, ComplaintFilters, ComplaintStatus, SeverityLevel, IssueCategory } from '../../types';
import toast from 'react-hot-toast';

const PAGE_SIZE = 15;
const STATUSES: ComplaintStatus[] = [
  'submitted','ai_processing','pending_review','assigned','in_progress','resolved','verified','closed','rejected',
];

export default function ComplaintsPage() {
  const qc = useQueryClient();

  const [filters, setFilters]   = useState<ComplaintFilters>({ page: 1, pageSize: PAGE_SIZE });
  const [search,  setSearch]    = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [detail,   setDetail]   = useState<Complaint | null>(null);
  const [showFilters, setShowFilters] = useState(false);

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['complaints', filters, search],
    queryFn:  () => complaintApi.list({ ...filters, search: search || undefined }).then(r => r.data),
    placeholderData: prev => prev,
  });

  const { data: officers } = useQuery({
    queryKey: ['officers-list'],
    queryFn:  () => officerApi.list({ available: true }).then(r => r.data),
  });

  const updateStatus = useMutation({
    mutationFn: ({ id, status, notes }: { id: string; status: string; notes?: string }) =>
      complaintApi.updateStatus(id, status, notes),
    onSuccess: () => {
      toast.success('Status updated');
      qc.invalidateQueries({ queryKey: ['complaints'] });
      if (detail) setDetail(null);
    },
    onError: () => toast.error('Failed to update status'),
  });

  const assignOfficer = useMutation({
    mutationFn: ({ id, officerId }: { id: string; officerId: string }) =>
      complaintApi.assign(id, officerId),
    onSuccess: () => {
      toast.success('Officer assigned');
      qc.invalidateQueries({ queryKey: ['complaints'] });
    },
  });

  const bulkAssign = useMutation({
    mutationFn: ({ officerId }: { officerId: string }) =>
      complaintApi.bulkAssign(Array.from(selected), officerId),
    onSuccess: () => {
      toast.success(`${selected.size} complaints assigned`);
      setSelected(new Set());
      qc.invalidateQueries({ queryKey: ['complaints'] });
    },
  });

  const exportCsv = async () => {
    try {
      const { data: blob } = await complaintApi.exportCsv(filters);
      const url = URL.createObjectURL(blob);
      const a   = document.createElement('a');
      a.href = url; a.download = 'complaints.csv'; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error('Export failed'); }
  };

  const toggleSelect = useCallback((id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const toggleAll = () => {
    if (selected.size === (data?.items.length ?? 0)) {
      setSelected(new Set());
    } else {
      setSelected(new Set(data?.items.map(c => c.id)));
    }
  };

  const setFilter = (key: keyof ComplaintFilters, val: any) =>
    setFilters(p => ({ ...p, [key]: val, page: 1 }));

  const complaints = data?.items ?? [];
  const total      = data?.total  ?? 0;
  const pages      = data?.pages  ?? 1;
  const page       = filters.page ?? 1;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Complaints"
        subtitle={`${total.toLocaleString()} total reports`}
        actions={
          <>
            <button onClick={() => refetch()} className="btn-secondary">
              <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />
              Refresh
            </button>
            <button onClick={exportCsv} className="btn-secondary">
              <Download size={14} /> Export CSV
            </button>
          </>
        }
      />

      {/* ── Filter bar ────────────────────────────────────────────────── */}
      <div className="card p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          {/* Search */}
          <div className="flex items-center gap-2 flex-1 min-w-[220px] input px-3.5 py-2">
            <Search size={14} className="text-[var(--text-muted)] flex-shrink-0" />
            <input
              className="bg-transparent outline-none w-full text-sm"
              placeholder="Search by title, ID, citizen name…"
              value={search}
              onChange={e => { setSearch(e.target.value); setFilter('page', 1); }}
            />
            {search && (
              <button onClick={() => setSearch('')}>
                <X size={14} className="text-[var(--text-muted)]" />
              </button>
            )}
          </div>

          {/* Status filter */}
          <select
            className="input w-44 py-2"
            value={filters.status ?? ''}
            onChange={e => setFilter('status', e.target.value || undefined)}
          >
            <option value="">All Statuses</option>
            {STATUSES.map(s => (
              <option key={s} value={s}>{STATUS_LABELS[s]}</option>
            ))}
          </select>

          {/* Severity filter */}
          <select
            className="input w-36 py-2"
            value={filters.severity ?? ''}
            onChange={e => setFilter('severity', e.target.value || undefined)}
          >
            <option value="">All Severities</option>
            {(['critical','high','medium','low'] as SeverityLevel[]).map(s => (
              <option key={s} value={s} className="capitalize">{s.charAt(0).toUpperCase()+s.slice(1)}</option>
            ))}
          </select>

          {/* Category filter */}
          <select
            className="input w-48 py-2"
            value={filters.category ?? ''}
            onChange={e => setFilter('category', e.target.value || undefined)}
          >
            <option value="">All Categories</option>
            {Object.entries(CATEGORY_META).map(([k, v]) => (
              <option key={k} value={k}>{v.emoji} {v.label}</option>
            ))}
          </select>

          <button
            onClick={() => setFilters({ page: 1, pageSize: PAGE_SIZE })}
            className="btn-ghost text-xs"
          >
            <X size={13} /> Clear
          </button>
        </div>

        {/* Bulk actions */}
        {selected.size > 0 && (
          <div className="flex items-center gap-3 pt-2 border-t border-[var(--border)]">
            <span className="text-sm font-medium text-brand-600">
              {selected.size} selected
            </span>
            <select
              className="input w-48 py-1.5 text-xs"
              onChange={e => {
                if (e.target.value) bulkAssign.mutate({ officerId: e.target.value });
              }}
              defaultValue=""
            >
              <option value="">Assign to officer…</option>
              {officers?.items.map(o => (
                <option key={o.id} value={o.id}>
                  {o.user.fullName} — {o.badgeNumber}
                </option>
              ))}
            </select>
            <button
              className="btn-secondary text-xs py-1.5"
              onClick={() => setSelected(new Set())}
            >
              Cancel
            </button>
          </div>
        )}
      </div>

      {/* ── Table ─────────────────────────────────────────────────────── */}
      <SectionCard>
        {isLoading ? (
          <div className="flex items-center justify-center py-20">
            <Spinner size={8} />
          </div>
        ) : complaints.length === 0 ? (
          <EmptyState
            icon="📋"
            title="No complaints found"
            description="Try adjusting your search or filter criteria."
          />
        ) : (
          <div className="overflow-x-auto -mx-5 px-5">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border)]">
                  <th className="py-3 pr-3 w-8">
                    <input
                      type="checkbox"
                      className="rounded"
                      checked={selected.size === complaints.length && complaints.length > 0}
                      onChange={toggleAll}
                    />
                  </th>
                  {['ID', 'Issue', 'Category', 'Severity', 'Status', 'Officer', 'SLA', 'Submitted', ''].map(h => (
                    <th key={h} className="label text-left py-3 pr-4 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {complaints.map(c => {
                  const slaOk = !c.slaBreached && c.status !== 'resolved' && c.status !== 'verified';
                  return (
                    <tr key={c.id} className={cn(
                      'table-row',
                      selected.has(c.id) && 'bg-brand-50 dark:bg-brand-950/50'
                    )}>
                      <td className="py-3 pr-3">
                        <input
                          type="checkbox"
                          className="rounded"
                          checked={selected.has(c.id)}
                          onChange={() => toggleSelect(c.id)}
                        />
                      </td>
                      <td className="py-3 pr-4">
                        <span className="font-mono text-xs text-[var(--text-muted)]">
                          {c.complaintNumber}
                        </span>
                      </td>
                      <td className="py-3 pr-4 max-w-[200px]">
                        <p className="font-medium text-[var(--text-primary)] truncate">{c.title}</p>
                        <p className="text-2xs text-[var(--text-muted)] truncate">{c.address}</p>
                      </td>
                      <td className="py-3 pr-4 whitespace-nowrap">
                        <CategoryBadge category={c.category} />
                      </td>
                      <td className="py-3 pr-4">
                        <SeverityBadge severity={c.severity} />
                      </td>
                      <td className="py-3 pr-4">
                        <StatusBadge status={c.status} />
                      </td>
                      <td className="py-3 pr-4">
                        {c.officer ? (
                          <div className="flex items-center gap-1.5">
                            <Avatar name={c.officer.user.fullName} size={5} />
                            <span className="text-xs truncate max-w-[80px]">
                              {c.officer.user.fullName}
                            </span>
                          </div>
                        ) : (
                          <button
                            className="text-2xs text-brand-600 hover:underline font-medium"
                            onClick={() => setDetail(c)}
                          >
                            + Assign
                          </button>
                        )}
                      </td>
                      <td className="py-3 pr-4">
                        {c.slaDeadline && (
                          <span className={cn(
                            'text-2xs font-semibold',
                            c.slaBreached ? 'text-red-600' : 'text-emerald-600'
                          )}>
                            {c.slaBreached ? '⚠ Breached' : '✓ On track'}
                          </span>
                        )}
                      </td>
                      <td className="py-3 pr-4 text-xs text-[var(--text-muted)] whitespace-nowrap">
                        {fmtRelative(c.createdAt)}
                      </td>
                      <td className="py-3">
                        <button
                          className="btn-ghost py-1 px-2"
                          onClick={() => setDetail(c)}
                        >
                          <Eye size={14} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* ── Pagination ─────────────────────────────────────────────── */}
        {!isLoading && (
          <div className="flex items-center justify-between pt-4 mt-2 border-t border-[var(--border)]">
            <p className="text-xs text-[var(--text-muted)]">
              Showing {((page - 1) * PAGE_SIZE) + 1}–{Math.min(page * PAGE_SIZE, total)} of {total.toLocaleString()}
            </p>
            <div className="flex items-center gap-1">
              <button
                className="btn-ghost py-1 px-2 disabled:opacity-40"
                disabled={page <= 1}
                onClick={() => setFilter('page', page - 1)}
              >
                <ChevronLeft size={15} />
              </button>
              {Array.from({ length: Math.min(pages, 5) }, (_, i) => {
                const p = i + 1;
                return (
                  <button
                    key={p}
                    onClick={() => setFilter('page', p)}
                    className={cn(
                      'w-8 h-8 rounded-lg text-xs font-semibold transition-colors',
                      p === page
                        ? 'bg-brand-600 text-white'
                        : 'hover:bg-slate-100 dark:hover:bg-brand-900 text-[var(--text-muted)]'
                    )}
                  >
                    {p}
                  </button>
                );
              })}
              <button
                className="btn-ghost py-1 px-2 disabled:opacity-40"
                disabled={page >= pages}
                onClick={() => setFilter('page', page + 1)}
              >
                <ChevronRight size={15} />
              </button>
            </div>
          </div>
        )}
      </SectionCard>

      {/* ── Detail Drawer ─────────────────────────────────────────────── */}
      {detail && (
        <ComplaintDrawer
          complaint={detail}
          officers={officers?.items ?? []}
          onClose={() => setDetail(null)}
          onUpdateStatus={(status, notes) =>
            updateStatus.mutate({ id: detail.id, status, notes })
          }
          onAssign={(officerId) =>
            assignOfficer.mutate({ id: detail.id, officerId })
          }
          isUpdating={updateStatus.isPending}
        />
      )}
    </div>
  );
}

// ─── Complaint Drawer ─────────────────────────────────────────────────────────

function ComplaintDrawer({ complaint: c, officers, onClose, onUpdateStatus, onAssign, isUpdating }: {
  complaint:      Complaint;
  officers:       any[];
  onClose:        () => void;
  onUpdateStatus: (status: string, notes?: string) => void;
  onAssign:       (officerId: string) => void;
  isUpdating:     boolean;
}) {
  const [notes,      setNotes]      = useState('');
  const [newStatus,  setNewStatus]  = useState<string>(c.status);
  const [officerId,  setOfficerId]  = useState<string>(c.officerId ?? '');

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/30 backdrop-blur-sm z-40"
        onClick={onClose}
      />
      {/* Drawer */}
      <div className={cn(
        'fixed right-0 top-0 h-full z-50 flex flex-col',
        'bg-white dark:bg-[var(--bg-card)] border-l border-[var(--border)]',
        'shadow-card-lg w-full max-w-lg animate-slide-up'
      )}>
        {/* Header */}
        <div className="flex items-start justify-between p-5 border-b border-[var(--border)]">
          <div>
            <p className="font-mono text-xs text-[var(--text-muted)]">{c.complaintNumber}</p>
            <h2 className="text-base font-bold text-[var(--text-primary)] mt-0.5">{c.title}</h2>
            <div className="flex items-center gap-2 mt-2">
              <StatusBadge status={c.status} />
              <SeverityBadge severity={c.severity} />
              <CategoryBadge category={c.category} />
            </div>
          </div>
          <button className="btn-ghost" onClick={onClose}><X size={18} /></button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* Image */}
          {c.images?.[0]?.cdnUrl && (
            <img
              src={c.images[0].cdnUrl}
              alt="complaint"
              className="w-full h-44 object-cover rounded-xl"
            />
          )}

          {/* Description */}
          <div>
            <p className="label">Description</p>
            <p className="text-sm text-[var(--text-primary)] leading-relaxed">{c.description}</p>
          </div>
          {c.aiDescription && (
            <div className="p-3.5 rounded-xl bg-brand-50 dark:bg-brand-950 border border-brand-100 dark:border-brand-800">
              <p className="text-2xs font-bold text-brand-600 uppercase tracking-wide mb-1">
                ✨ AI Description
              </p>
              <p className="text-xs text-[var(--text-primary)] leading-relaxed">{c.aiDescription}</p>
              {c.aiConfidence && (
                <p className="text-2xs text-[var(--text-muted)] mt-1">
                  Confidence: {(c.aiConfidence * 100).toFixed(0)}%
                </p>
              )}
            </div>
          )}

          {/* Location */}
          <div>
            <p className="label">Location</p>
            <p className="text-sm text-[var(--text-primary)]">{c.address ?? `${c.latitude}, ${c.longitude}`}</p>
          </div>

          {/* Citizen */}
          <div className="flex items-center gap-3 p-3 rounded-xl bg-slate-50 dark:bg-brand-900">
            <Avatar name={c.citizen.fullName} url={c.citizen.avatarUrl} size={9} />
            <div>
              <p className="text-sm font-semibold text-[var(--text-primary)]">{c.citizen.fullName}</p>
              <p className="text-xs text-[var(--text-muted)]">{c.citizen.email}</p>
              <p className="text-2xs text-[var(--text-muted)]">
                ⭐ Reputation: {c.citizen.reputationScore}
              </p>
            </div>
          </div>

          {/* Assign Officer */}
          <div>
            <label className="label">Assign Officer</label>
            <div className="flex gap-2">
              <select
                className="input flex-1"
                value={officerId}
                onChange={e => setOfficerId(e.target.value)}
              >
                <option value="">Select officer…</option>
                {officers.map(o => (
                  <option key={o.id} value={o.id}>
                    {o.user.fullName} — {o.badgeNumber} ({o.totalAssigned} assigned)
                  </option>
                ))}
              </select>
              <button
                className="btn-primary py-2"
                disabled={!officerId}
                onClick={() => onAssign(officerId)}
              >
                <UserCheck size={14} /> Assign
              </button>
            </div>
          </div>

          {/* Update Status */}
          <div>
            <label className="label">Update Status</label>
            <select
              className="input mb-2"
              value={newStatus}
              onChange={e => setNewStatus(e.target.value)}
            >
              {STATUSES.map(s => (
                <option key={s} value={s}>{STATUS_LABELS[s]}</option>
              ))}
            </select>
            <textarea
              className="input resize-none text-sm"
              rows={3}
              placeholder="Resolution notes (optional)…"
              value={notes}
              onChange={e => setNotes(e.target.value)}
            />
          </div>

          {/* Status timeline */}
          <div>
            <p className="label">Status History</p>
            <div className="space-y-2">
              {(c.statusHistory ?? []).map((h, i) => (
                <div key={h.id} className="flex items-start gap-3">
                  <div className={cn(
                    'w-2 h-2 rounded-full mt-1.5 flex-shrink-0',
                    i === 0 ? 'bg-brand-600' : 'bg-slate-300 dark:bg-slate-600'
                  )} />
                  <div>
                    <p className="text-xs font-semibold text-[var(--text-primary)]">
                      {STATUS_LABELS[h.toStatus]}
                    </p>
                    {h.notes && <p className="text-2xs text-[var(--text-muted)]">{h.notes}</p>}
                    <p className="text-2xs text-[var(--text-muted)]">
                      by {h.changedBy.fullName} · {fmtDateTime(h.createdAt)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex gap-2 p-5 border-t border-[var(--border)]">
          <button className="btn-secondary flex-1" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary flex-1"
            disabled={isUpdating || newStatus === c.status}
            onClick={() => onUpdateStatus(newStatus, notes)}
          >
            {isUpdating ? <Spinner size={4} className="border-white border-t-transparent" /> : <CheckCircle size={14} />}
            Update Status
          </button>
        </div>
      </div>
    </>
  );
}

const STATUSES: ComplaintStatus[] = [
  'submitted','ai_processing','pending_review','assigned','in_progress','resolved','verified','closed','rejected',
];
