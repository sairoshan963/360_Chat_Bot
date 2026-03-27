import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Input, Button, Typography, Tooltip, Avatar, Modal, Popconfirm } from 'antd';
import {
  SendOutlined, RobotOutlined, UserOutlined,
  CopyOutlined, CheckOutlined,
  ThunderboltOutlined, InfoCircleOutlined,
  CheckCircleOutlined, CloseCircleOutlined,
  PlusOutlined, DeleteOutlined, EditOutlined, PushpinOutlined,
  ShrinkOutlined, PaperClipOutlined,
} from '@ant-design/icons';
import { sendMessage, sendMessageStream, confirmAction, getChatHistory, getChatSessions, discardSession, deleteSession, deleteAllSessions, renameSession, uploadChatFile } from '../../api/chat';
import useAuthStore from '../../store/authStore';
import { useSpeechToText } from '../../hooks/useSpeechToText';

/* ─── Chat capabilities per role ────────────────────────────────────────────── */
const CAPABILITIES = {
  EMPLOYEE: {
    label: 'Employee',
    can: [
      { icon: '✅', text: 'Show my tasks' },
      { icon: '💬', text: 'Show my feedback / report' },
      { icon: '🤝', text: 'Show my nominations' },
      { icon: '👥', text: 'Nominate peers for a cycle' },
      { icon: '🔄', text: 'Show cycles I am in' },
      { icon: '📅', text: 'Show upcoming deadlines' },
      { icon: '📢', text: 'Show announcements' },
    ],
    cannot: [
      { text: 'Fill feedback form (rating questions)', goto: 'My Tasks page' },
      { text: 'View detailed report charts', goto: 'My Report page' },
    ],
  },
  MANAGER: {
    label: 'Manager',
    can: [
      { icon: '✅', text: 'Show my tasks' },
      { icon: '💬', text: 'Show my feedback / report' },
      { icon: '🤝', text: 'Show my nominations' },
      { icon: '👥', text: 'Nominate peers for a cycle' },
      { icon: '🔄', text: 'Show cycles I am in' },
      { icon: '📅', text: 'Show upcoming deadlines' },
      { icon: '📢', text: 'Show announcements' },
      { icon: '👥', text: 'Show team summary' },
      { icon: '📋', text: 'Show team nominations' },
      { icon: '⏳', text: 'Show pending reviews' },
    ],
    cannot: [
      { text: 'Approve / reject nominations', goto: 'Nominations page' },
      { text: 'View employee report charts', goto: 'Reports page' },
      { text: 'Fill feedback form', goto: 'My Tasks page' },
    ],
  },
  HR_ADMIN: {
    label: 'HR Admin',
    can: [
      { icon: '📊', text: 'Show cycle status' },
      { icon: '📈', text: 'Show participation statistics' },
      { icon: '📝', text: 'Show all templates' },
      { icon: '👤', text: 'Show all employees' },
      { icon: '📅', text: 'Show cycle deadlines' },
      { icon: '📢', text: 'Show announcements' },
      { icon: '➕', text: 'Create a new cycle (DRAFT)' },
      { icon: '➕', text: 'Create a new template' },
      { icon: '▶️', text: 'Activate a cycle' },
      { icon: '⏹️', text: 'Close a cycle' },
      { icon: '🚀', text: 'Release results for a cycle' },
      { icon: '❌', text: 'Cancel / archive a cycle' },
    ],
    cannot: [
      { text: 'Full cycle configuration (participants, settings)', goto: 'Cycles page' },
      { text: 'Edit template sections & questions', goto: 'Templates page' },
      { text: 'Create / edit announcements', goto: 'Announcements page' },
      { text: 'View detailed report charts', goto: 'Reports page' },
    ],
  },
  SUPER_ADMIN: {
    label: 'Super Admin',
    can: [
      { icon: '📊', text: 'Show cycle status' },
      { icon: '📈', text: 'Show participation statistics' },
      { icon: '📝', text: 'Show all templates' },
      { icon: '👤', text: 'Show all employees' },
      { icon: '📅', text: 'Show cycle deadlines' },
      { icon: '📢', text: 'Show announcements' },
      { icon: '➕', text: 'Create a new cycle (DRAFT)' },
      { icon: '➕', text: 'Create a new template' },
      { icon: '▶️', text: 'Activate a cycle' },
      { icon: '⏹️', text: 'Close a cycle' },
      { icon: '🚀', text: 'Release results for a cycle' },
      { icon: '❌', text: 'Cancel / archive a cycle' },
      { icon: '🔍', text: 'Show audit logs' },
      { icon: '👥', text: 'Show team summary' },
      { icon: '📋', text: 'Show team nominations' },
    ],
    cannot: [
      { text: 'Manage users (create, deactivate)', goto: 'Admin → Users page' },
      { text: 'View org chart', goto: 'Admin → Org page' },
      { text: 'Full cycle configuration', goto: 'Cycles page' },
      { text: 'Edit template sections', goto: 'Templates page' },
    ],
  },
};

const { Text } = Typography;

/* ─── State badge colors ────────────────────────────────────────────────────── */
const STATE_COLORS = {
  ACTIVE:           { bg: '#f0fdf4', border: '#86efac', text: '#15803d', dot: '#22c55e' },
  NOMINATION:       { bg: '#eff6ff', border: '#93c5fd', text: '#1d4ed8', dot: '#3b82f6' },
  DRAFT:            { bg: '#f9fafb', border: '#d1d5db', text: '#374151', dot: '#9ca3af' },
  FINALIZED:        { bg: '#fdf4ff', border: '#d8b4fe', text: '#7e22ce', dot: '#a855f7' },
  CLOSED:           { bg: '#fef3c7', border: '#fcd34d', text: '#92400e', dot: '#f59e0b' },
  RESULTS_RELEASED: { bg: '#ecfeff', border: '#67e8f9', text: '#0e7490', dot: '#06b6d4' },
  ARCHIVED:         { bg: '#f1f5f9', border: '#cbd5e1', text: '#475569', dot: '#94a3b8' },
};

const STATUS_COLORS = {
  ASSIGNED:    { bg: '#eff6ff', text: '#1d4ed8' },
  SUBMITTED:   { bg: '#f0fdf4', text: '#15803d' },
  LOCKED:      { bg: '#f9fafb', text: '#374151' },
  PENDING:     { bg: '#fffbeb', text: '#92400e' },
  IN_PROGRESS: { bg: '#eff6ff', text: '#1d4ed8' },
  CREATED:     { bg: '#f9fafb', text: '#475569' },
};

/* ─── Role-based suggestions ────────────────────────────────────────────────── */
const ROLE_SUGGESTIONS = {
  EMPLOYEE: [
    { label: 'Show my feedback',     icon: '💬' },
    { label: 'Show my tasks',        icon: '✅' },
    { label: 'Show my nominations',  icon: '🤝' },
    { label: 'Catch me up on everything', icon: '⚡' },
    { label: 'Show my cycles',       icon: '🔄' },
    { label: 'Show cycle deadlines', icon: '📅' },
  ],
  MANAGER: [
    { label: 'Show team summary',       icon: '👥' },
    { label: 'Show team nominations',   icon: '📋' },
    { label: 'Show pending reviews',    icon: '⏳' },
    { label: 'Catch me up on everything', icon: '⚡' },
    { label: 'Show cycle status',       icon: '📊' },
    { label: 'Show cycle deadlines',    icon: '📅' },
  ],
  HR_ADMIN: [
    { label: 'Show cycle status',             icon: '📊' },
    { label: 'Who are the top performers?',   icon: '🏆' },
    { label: 'Show participation stats',      icon: '📈' },
    { label: 'Which department scores highest?', icon: '🏢' },
    { label: 'Create a cycle',                icon: '➕' },
    { label: 'Show templates',                icon: '📝' },
  ],
  SUPER_ADMIN: [
    { label: 'Give me an org overview',       icon: '🌐' },
    { label: 'Who are the top performers?',   icon: '🏆' },
    { label: 'Show participation stats',      icon: '📈' },
    { label: 'Which department scores highest?', icon: '🏢' },
    { label: 'Show audit logs',               icon: '🔍' },
    { label: 'Show employees',                icon: '👤' },
  ],
};
const DEFAULT_SUGGESTIONS = [
  { label: 'Show cycle status',    icon: '📊' },
  { label: 'Show my tasks',        icon: '✅' },
  { label: 'Show cycle deadlines', icon: '📅' },
  { label: 'Show my feedback',     icon: '💬' },
  { label: 'Show announcements',   icon: '📢' },
  { label: 'Nominate peers',       icon: '🤝' },
];

/* ─── Typing indicator ──────────────────────────────────────────────────────── */
function TypingDots() {
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'center', padding: '4px 0' }}>
      {[0, 1, 2].map((i) => (
        <div key={i} style={{
          width: 7, height: 7, borderRadius: '50%', background: '#94a3b8',
          animation: 'bounce 1.2s infinite',
          animationDelay: `${i * 0.2}s`,
        }} />
      ))}
      <style>{`
        @keyframes bounce {
          0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
          40% { transform: translateY(-6px); opacity: 1; }
        }
        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
        @keyframes wblink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
      `}</style>
    </div>
  );
}

/* ─── State badge ───────────────────────────────────────────────────────────── */
function StateBadge({ state }) {
  const c = STATE_COLORS[state] || STATE_COLORS.DRAFT;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      background: c.bg, border: `1px solid ${c.border}`, color: c.text,
      borderRadius: 20, padding: '2px 10px', fontSize: 11, fontWeight: 600,
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: c.dot, display: 'inline-block' }} />
      {state?.replace(/_/g, ' ')}
    </span>
  );
}

/* ─── Data renderer ─────────────────────────────────────────────────────────── */
function DataCard({ data, onPick, onDirectAction }) {
  if (!data || !Object.keys(data).length) return null;

  const card = {
    background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10,
    boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
  };

  // Grouped tasks — show_my_tasks, show_pending_reviews (grouped by cycle)
  if (data.grouped_tasks?.length) {
    const SC = STATUS_COLORS;
    return (
      <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 10 }}>
        {data.grouped_tasks.map((g, gi) => (
          <div key={gi} style={{ ...card, overflow: 'hidden' }}>
            <div style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', padding: '8px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 700, fontSize: 13, color: '#1e293b' }}>{g.cycle}</span>
              <StateBadge state={g.state} />
            </div>
            {g.tasks.map((t, ti) => {
              const sc = SC[t.status] || { bg: '#f1f5f9', text: '#475569' };
              return (
                <div key={ti} style={{ padding: '8px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: ti < g.tasks.length - 1 ? '1px solid #f8fafc' : 'none' }}>
                  <span style={{ fontSize: 13, color: '#334155', fontWeight: 500 }}>{t.reviewee}</span>
                  <span style={{ fontSize: 11, fontWeight: 600, background: sc.bg, color: sc.text, borderRadius: 20, padding: '2px 10px' }}>{t.status}</span>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    );
  }

  // Grouped nominations — show_my_nominations
  if (data.grouped_nominations?.length) {
    const NOM_COLORS = { PENDING: '#f59e0b', APPROVED: '#22c55e', REJECTED: '#ef4444' };
    return (
      <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 10 }}>
        {data.grouped_nominations.map((g, gi) => (
          <div key={gi} style={{ ...card, overflow: 'hidden' }}>
            <div style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', padding: '8px 14px' }}>
              <span style={{ fontWeight: 700, fontSize: 13, color: '#1e293b' }}>{g.cycle}</span>
            </div>
            {g.nominations.map((n, ni) => (
              <div key={ni} style={{ padding: '8px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: ni < g.nominations.length - 1 ? '1px solid #f8fafc' : 'none' }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#1e293b' }}>{n.peer}</div>
                  <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 1 }}>{n.email}</div>
                </div>
                <span style={{ fontSize: 11, fontWeight: 600, borderRadius: 20, padding: '2px 10px', background: `${NOM_COLORS[n.status] || '#94a3b8'}20`, color: NOM_COLORS[n.status] || '#94a3b8' }}>{n.status}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    );
  }

  // Grouped team nominations — show_team_nominations
  if (data.grouped_team_nominations?.length) {
    const NOM_COLORS = { PENDING: '#f59e0b', APPROVED: '#22c55e', REJECTED: '#ef4444' };
    return (
      <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 10 }}>
        {data.grouped_team_nominations.map((g, gi) => (
          <div key={gi} style={{ ...card, overflow: 'hidden' }}>
            <div style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', padding: '8px 14px' }}>
              <span style={{ fontWeight: 700, fontSize: 13, color: '#1e293b' }}>👤 {g.reviewee}</span>
            </div>
            {g.nominations.map((n, ni) => (
              <div key={ni} style={{ padding: '8px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: ni < g.nominations.length - 1 ? '1px solid #f8fafc' : 'none' }}>
                <div>
                  <div style={{ fontSize: 13, color: '#334155', fontWeight: 500 }}>{n.peer}</div>
                  <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 1 }}>{n.cycle}</div>
                </div>
                {n.status === 'PENDING' && onDirectAction ? (
                  <div style={{ display: 'flex', gap: 4 }}>
                    <button onClick={() => onDirectAction('approve_nomination', n.nomination_id)} style={{ fontSize: 11, fontWeight: 600, padding: '3px 9px', borderRadius: 6, border: 'none', background: '#22c55e20', color: '#16a34a', cursor: 'pointer' }}>✓ Approve</button>
                    <button onClick={() => onDirectAction('reject_nomination', n.nomination_id)} style={{ fontSize: 11, fontWeight: 600, padding: '3px 9px', borderRadius: 6, border: 'none', background: '#ef444420', color: '#dc2626', cursor: 'pointer' }}>✗ Reject</button>
                  </div>
                ) : (
                  <span style={{ fontSize: 11, fontWeight: 600, borderRadius: 20, padding: '2px 10px', background: `${NOM_COLORS[n.status] || '#94a3b8'}20`, color: NOM_COLORS[n.status] || '#94a3b8' }}>{n.status}</span>
                )}
              </div>
            ))}
          </div>
        ))}
      </div>
    );
  }

  // Cycles list
  if (data.cycles?.length) {
    return (
      <div style={{ marginTop: 10, maxHeight: 260, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {data.cycles.map((c, i) => (
          <div key={i} style={{
            background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10,
            padding: '10px 14px', display: 'flex', justifyContent: 'space-between',
            alignItems: 'center', gap: 12, boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{c.name}</div>
              {c.review_deadline && <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>📅 {c.review_deadline}</div>}
            </div>
            <StateBadge state={c.state} />
          </div>
        ))}
      </div>
    );
  }

  // Deadlines
  if (data.deadlines?.length) {
    return (
      <div style={{ marginTop: 10, maxHeight: 260, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {data.deadlines.map((d, i) => (
          <div key={i} style={{
            background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10,
            padding: '10px 14px', display: 'flex', justifyContent: 'space-between',
            alignItems: 'center', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{d.cycle}</div>
              <div style={{ fontSize: 11, color: '#f59e0b', marginTop: 2, fontWeight: 500 }}>⏰ {d.deadline}</div>
            </div>
            <StateBadge state={d.state} />
          </div>
        ))}
      </div>
    );
  }

  // Tasks (flat list fallback)
  if (data.tasks?.length) {
    return (
      <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {data.tasks.map((t, i) => {
          const sc = STATUS_COLORS[t.status] || { bg: '#f1f5f9', text: '#475569' };
          return (
            <div key={i} style={{
              background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10,
              padding: '10px 14px', display: 'flex', justifyContent: 'space-between',
              alignItems: 'center', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
            }}>
              <div>
                <div style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{t.reviewee || t.name}</div>
                <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>{t.cycle}</div>
              </div>
              <span style={{
                background: sc.bg, color: sc.text, borderRadius: 20,
                padding: '2px 10px', fontSize: 11, fontWeight: 600,
              }}>{t.status}</span>
            </div>
          );
        })}
      </div>
    );
  }

  // Team summary
  if (data.team?.length) {
    return (
      <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {data.team.map((m, i) => {
          const pct = m.total_tasks > 0 ? Math.round((m.submitted / m.total_tasks) * 100) : 0;
          return (
            <div key={i} style={{
              background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10,
              padding: '10px 14px', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{m.name}</span>
                <span style={{ fontSize: 12, color: '#64748b' }}>{m.submitted}/{m.total_tasks} submitted</span>
              </div>
              <div style={{ background: '#f1f5f9', borderRadius: 4, height: 6 }}>
                <div style={{ background: '#22c55e', borderRadius: 4, height: 6, width: `${pct}%`, transition: 'width 0.6s ease' }} />
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  // Participation stats
  if (data.participation?.length) {
    return (
      <div style={{ marginTop: 10, maxHeight: 260, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {data.participation.map((p, i) => (
          <div key={i} style={{
            background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10,
            padding: '10px 14px', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{p.cycle}</span>
              <span style={{ fontSize: 12, color: '#64748b' }}>{p.submitted}/{p.total} · {p.completion_pct}%</span>
            </div>
            <div style={{ background: '#f1f5f9', borderRadius: 4, height: 6 }}>
              <div style={{ background: '#3b82f6', borderRadius: 4, height: 6, width: `${p.completion_pct}%`, transition: 'width 0.6s ease' }} />
            </div>
          </div>
        ))}
      </div>
    );
  }

  // Available cycles (for picking)
  if (data.available_cycles?.length) {
    return (
      <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {data.available_cycles.map((c, i) => (
          <div
            key={`${c.id || i}`}
            onClick={() => onPick?.({ id: c.id, label: c.name })}
            style={{
              background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10,
              padding: '10px 14px', display: 'flex', justifyContent: 'space-between',
              alignItems: 'center', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
              cursor: onPick ? 'pointer' : 'default', transition: 'background 0.15s',
            }}
            onMouseEnter={(e) => { if (onPick) e.currentTarget.style.background = '#eef2ff'; }}
            onMouseLeave={(e) => { if (onPick) e.currentTarget.style.background = '#fff'; }}
          >
            <span style={{ fontWeight: 400, fontSize: 12, color: '#94a3b8', marginRight: 8 }}>{i + 1}.</span>
            <span style={{ fontWeight: 500, fontSize: 13, color: '#1e293b', flex: 1 }}>{c.name}</span>
            <StateBadge state={c.state} />
          </div>
        ))}
      </div>
    );
  }

  // Available nominations picker (for approve/reject)
  if (data.available_nominations?.length) {
    return (
      <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {data.available_nominations.map((n, i) => (
          <div
            key={`${n.nomination_id}-${i}`}
            onClick={() => onPick?.({ id: n.nomination_id, label: `${n.peer} reviewing ${n.reviewee}` })}
            style={{
              background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10,
              padding: '10px 14px', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
              cursor: onPick ? 'pointer' : 'default', transition: 'background 0.15s',
            }}
            onMouseEnter={(e) => { if (onPick) e.currentTarget.style.background = '#eef2ff'; }}
            onMouseLeave={(e) => { if (onPick) e.currentTarget.style.background = '#fff'; }}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
              <span style={{ fontWeight: 400, fontSize: 12, color: '#94a3b8', marginTop: 2 }}>{i + 1}.</span>
              <div>
                <div style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{n.peer}</div>
                <div style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>
                  reviewing {n.reviewee} · <span style={{ color: '#6366f1' }}>{n.cycle}</span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  // Nominations (my nominations)
  if (data.nominations?.length) {
    const NOM_COLORS = { PENDING: '#f59e0b', APPROVED: '#22c55e', REJECTED: '#ef4444' };
    return (
      <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {data.nominations.map((n, i) => (
          <div key={i} style={{
            background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10,
            padding: '10px 14px', display: 'flex', justifyContent: 'space-between',
            alignItems: 'center', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{n.peer}</div>
              <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>{n.email} · {n.cycle}</div>
            </div>
            <span style={{
              fontSize: 11, fontWeight: 600, borderRadius: 20, padding: '2px 10px',
              background: `${NOM_COLORS[n.status]}20`, color: NOM_COLORS[n.status],
            }}>{n.status}</span>
          </div>
        ))}
      </div>
    );
  }

  // Team nominations
  if (data.team_nominations?.length) {
    const NOM_COLORS = { PENDING: '#f59e0b', APPROVED: '#22c55e', REJECTED: '#ef4444' };
    return (
      <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {data.team_nominations.map((n, i) => (
          <div key={i} style={{
            background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10,
            padding: '10px 14px', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: 12, color: '#64748b' }}>
                  <span style={{ fontWeight: 600, color: '#1e293b' }}>{n.reviewee}</span> ← {n.peer}
                </div>
                <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>{n.cycle}</div>
              </div>
              <span style={{
                fontSize: 11, fontWeight: 600, borderRadius: 20, padding: '2px 10px',
                background: `${NOM_COLORS[n.status]}20`, color: NOM_COLORS[n.status],
              }}>{n.status}</span>
            </div>
          </div>
        ))}
      </div>
    );
  }

  // Templates
  if (data.templates?.length) {
    return (
      <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {data.templates.map((t, i) => (
          <div key={i} style={{
            background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10,
            padding: '10px 14px', display: 'flex', justifyContent: 'space-between',
            alignItems: 'center', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{t.name}</div>
              {t.description && <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>{t.description}</div>}
            </div>
            <span style={{
              background: '#eff6ff', color: '#1d4ed8', borderRadius: 20,
              padding: '2px 10px', fontSize: 11, fontWeight: 600,
            }}>{t.cycle_count} cycle{t.cycle_count !== 1 ? 's' : ''}</span>
          </div>
        ))}
      </div>
    );
  }

  // Employees
  if (data.employees?.length) {
    const ROLE_COLORS = {
      SUPER_ADMIN: '#7e22ce', HR_ADMIN: '#1d4ed8',
      MANAGER: '#0e7490', EMPLOYEE: '#374151',
    };
    return (
      <div style={{ marginTop: 10, maxHeight: 260, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 5 }}>
        {data.employees.map((e, i) => (
          <div key={i} style={{
            background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10,
            padding: '8px 14px', display: 'flex', justifyContent: 'space-between',
            alignItems: 'center', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{e.name}</div>
              <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 1 }}>{e.email} · {e.department}</div>
            </div>
            <span style={{
              fontSize: 10, fontWeight: 600, borderRadius: 20, padding: '2px 8px',
              background: '#f1f5f9', color: ROLE_COLORS[e.role] || '#374151',
            }}>{e.role?.replace('_', ' ')}</span>
          </div>
        ))}
      </div>
    );
  }

  // Announcements
  if (data.announcements?.length) {
    const ANN_COLORS = {
      info:    { bg: '#eff6ff', border: '#93c5fd', text: '#1d4ed8', icon: 'ℹ️' },
      warning: { bg: '#fffbeb', border: '#fcd34d', text: '#92400e', icon: '⚠️' },
      success: { bg: '#f0fdf4', border: '#86efac', text: '#15803d', icon: '✅' },
    };
    return (
      <div style={{ marginTop: 10, maxHeight: 260, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {data.announcements.map((a, i) => {
          const c = ANN_COLORS[a.type] || ANN_COLORS.info;
          return (
            <div key={i} style={{
              background: c.bg, border: `1px solid ${c.border}`, borderRadius: 10,
              padding: '10px 14px', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
            }}>
              <div style={{ fontSize: 13, color: c.text, lineHeight: 1.6 }}>
                {c.icon} {a.message}
              </div>
              <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 4 }}>{fmtIso(a.created_at)}</div>
            </div>
          );
        })}
      </div>
    );
  }

  // Audit logs
  if (data.audit_logs?.length) {
    return (
      <div style={{ marginTop: 10, maxHeight: 260, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 5 }}>
        {data.audit_logs.map((l, i) => (
          <div key={i} style={{
            background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10,
            padding: '8px 14px', display: 'flex', justifyContent: 'space-between',
            alignItems: 'center', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}>
            <div>
              <div style={{ fontSize: 12, color: '#1e293b' }}>
                <span style={{ fontWeight: 600 }}>{l.actor}</span>
                {' · '}<span style={{ color: '#7c3aed' }}>{l.action}</span>
                {' on '}<span style={{ color: '#0e7490' }}>{l.entity}</span>
              </div>
              <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 2 }}>
                {l.at ? new Date(l.at).toLocaleString([], { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  // Feedback results
  if (data.results?.length) {
    return (
      <div style={{ marginTop: 10, maxHeight: 260, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {data.results.map((r, i) => (
          <div key={i} style={{
            background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10,
            padding: '10px 14px', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: r.overall_score != null ? 8 : 0 }}>
              <div style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{r.cycle}</div>
              {r.overall_score != null && (
                <div style={{
                  background: '#f0fdf4', border: '1px solid #86efac', color: '#15803d',
                  borderRadius: 8, padding: '3px 12px', fontWeight: 700, fontSize: 16,
                }}>
                  {parseFloat(r.overall_score).toFixed(1)}
                </div>
              )}
            </div>
            {(r.peer_score != null || r.self_score != null) && (
              <div style={{ display: 'flex', gap: 6 }}>
                {r.peer_score != null && (
                  <span style={{
                    fontSize: 11, fontWeight: 500, background: '#eff6ff',
                    border: '1px solid #bfdbfe', color: '#1d4ed8',
                    borderRadius: 20, padding: '1px 8px',
                  }}>Peer {parseFloat(r.peer_score).toFixed(1)}</span>
                )}
                {r.self_score != null && (
                  <span style={{
                    fontSize: 11, fontWeight: 500, background: '#fdf4ff',
                    border: '1px solid #e9d5ff', color: '#7e22ce',
                    borderRadius: 20, padding: '1px 8px',
                  }}>Self {parseFloat(r.self_score).toFixed(1)}</span>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  }

  // Pending approvals
  if (data.pending_approvals?.length) {
    return (
      <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {data.pending_approvals.map((a, i) => (
          <div key={i} style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, padding: '10px 14px', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{a.reviewee} → {a.peer}</div>
                <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{a.cycle} · {fmtIso(a.created_at)}</div>
              </div>
              <span style={{ fontSize: 10, fontWeight: 600, background: '#fef9c3', color: '#92400e', borderRadius: 20, padding: '2px 10px', border: '1px solid #fde68a' }}>PENDING</span>
            </div>
          </div>
        ))}
        {data.pending_approvals.length > 6 && (
          <div style={{ textAlign: 'center', fontSize: 11, color: '#94a3b8' }}>+{data.pending_approvals.length - 6} more</div>
        )}
      </div>
    );
  }

  // Cycle results
  if (data.cycle_results?.length) {
    return (
      <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {data.cycle_results.map((r, i) => (
          <div key={i} style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, padding: '10px 14px', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
              <div style={{ fontWeight: 600, fontSize: 13, color: '#1e293b', flex: 1 }}>{r.name}</div>
              <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                {r.overall_score != null && <span style={{ fontSize: 11, fontWeight: 700, background: '#f0fdf4', color: '#15803d', border: '1px solid #86efac', borderRadius: 20, padding: '2px 10px' }}>⭐ {r.overall_score}</span>}
                {r.peer_score != null && <span style={{ fontSize: 11, background: '#eff6ff', color: '#1d4ed8', borderRadius: 20, padding: '2px 8px' }}>Peer {r.peer_score}</span>}
                {r.self_score != null && <span style={{ fontSize: 11, background: '#fdf4ff', color: '#7e22ce', borderRadius: 20, padding: '2px 8px' }}>Self {r.self_score}</span>}
                {r.manager_score != null && <span style={{ fontSize: 11, background: '#fff7ed', color: '#c2410c', borderRadius: 20, padding: '2px 8px' }}>Mgr {r.manager_score}</span>}
              </div>
            </div>
          </div>
        ))}
        {data.cycle_results.length > 8 && (
          <div style={{ textAlign: 'center', fontSize: 11, color: '#94a3b8' }}>+{data.cycle_results.length - 8} more</div>
        )}
      </div>
    );
  }

  // Export nominations
  if (data.export_nominations?.length) {
    const csvContent = [
      'Reviewee,Reviewee Email,Peer,Peer Email,Status,Nominated On',
      ...data.export_nominations.map(n =>
        `"${n.reviewee}","${n.reviewee_email}","${n.peer}","${n.peer_email}","${n.status}","${n.nominated_on}"`
      ),
    ].join('\n');
    const downloadCsv = () => {
      const blob = new Blob([csvContent], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url;
      a.download = `nominations_${data.cycle_name || 'export'}.csv`; a.click();
      URL.revokeObjectURL(url);
    };
    return (
      <div style={{ marginTop: 10 }}>
        <button onClick={downloadCsv} style={{
          marginBottom: 10, background: '#4f46e5', color: '#fff', border: 'none',
          borderRadius: 8, padding: '7px 16px', cursor: 'pointer', fontSize: 12, fontWeight: 600,
        }}>⬇ Download CSV ({data.export_nominations.length} rows)</button>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          {data.export_nominations.map((n, i) => (
            <div key={i} style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, padding: '8px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontWeight: 600, fontSize: 12, color: '#1e293b' }}>{n.reviewee} → {n.peer}</div>
                <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 2 }}>{fmtIso(n.nominated_on)}</div>
              </div>
              <span style={{ fontSize: 10, fontWeight: 600, background: '#f1f5f9', color: '#475569', borderRadius: 20, padding: '2px 8px' }}>{n.status}</span>
            </div>
          ))}
          {data.export_nominations.length > 5 && (
            <div style={{ textAlign: 'center', fontSize: 11, color: '#94a3b8' }}>+{data.export_nominations.length - 5} more rows in CSV</div>
          )}
        </div>
      </div>
    );
  }

  // My profile
  if (data.profile) {
    const p = data.profile;
    const profileRows = [
      { label: 'Email',        value: p.email },
      { label: 'Role',         value: p.role },
      { label: 'Job Title',    value: p.job_title && p.job_title !== 'N/A' ? p.job_title : null },
      { label: 'Department',   value: p.department },
      { label: 'Status',       value: p.status && p.status !== 'N/A' ? p.status : null },
      { label: 'Member Since', value: p.member_since && p.member_since !== 'N/A' ? p.member_since : null },
      { label: 'Manager',      value: p.manager && p.manager !== 'N/A' ? p.manager : null },
      { label: 'Manager Email',value: p.manager_email && p.manager_email !== 'N/A' ? p.manager_email : null },
    ].filter(r => r.value);
    return (
      <div style={{ marginTop: 10, background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, padding: '12px 16px', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
        <div style={{ fontWeight: 700, fontSize: 15, color: '#1e293b', marginBottom: 8 }}>{p.name}</div>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <tbody>
            {profileRows.map(r => (
              <tr key={r.label} style={{ borderBottom: '1px solid #f1f5f9' }}>
                <td style={{ fontSize: 10, fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', padding: '4px 10px 4px 0', whiteSpace: 'nowrap', width: '35%' }}>{r.label}</td>
                <td style={{ fontSize: 12, color: '#334155', padding: '4px 0' }}>{r.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  // My manager
  if (data.manager) {
    const m = data.manager;
    return (
      <div style={{ marginTop: 10, background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, padding: '12px 16px', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>Your Manager</div>
        <div style={{ fontWeight: 700, fontSize: 14, color: '#1e293b', marginBottom: 6 }}>{m.name}</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <div style={{ fontSize: 12, color: '#64748b' }}>📧 {m.email}</div>
          {m.job_title && m.job_title !== 'N/A' && <div style={{ fontSize: 12, color: '#64748b' }}>💼 {m.job_title}</div>}
          <div style={{ fontSize: 12, color: '#64748b' }}>🏢 {m.department}</div>
        </div>
      </div>
    );
  }

  // Direct reports (show my team)
  if (data.direct_reports?.length) {
    return (
      <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {data.direct_reports.map((m, i) => (
          <div key={i} style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, padding: '10px 14px', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{m.name}</div>
                <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{m.email}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 11, color: '#94a3b8' }}>{m.job_title}</div>
                <div style={{ fontSize: 10, fontWeight: 600, color: '#6366f1', marginTop: 2 }}>{m.role}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  // Next review deadline
  if (data.next_deadline) {
    const nd = data.next_deadline;
    return (
      <div style={{ marginTop: 10, background: '#fff', border: '1px solid #fbbf24', borderRadius: 10, padding: '12px 16px', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: '#92400e', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Next Review Deadline</div>
        <div style={{ fontWeight: 700, fontSize: 14, color: '#1e293b', marginBottom: 4 }}>{nd.cycle_name}</div>
        <div style={{ fontSize: 13, color: '#d97706', fontWeight: 600 }}>📅 {nd.deadline_date}</div>
      </div>
    );
  }

  // Who has not submitted (pending tasks)
  if (data.pending?.length) {
    return (
      <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {data.pending.map((p, i) => (
          <div key={i} style={{ background: '#fff', border: '1px solid #fecaca', borderRadius: 10, padding: '10px 14px', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{p.reviewer}</div>
                <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>reviewing {p.reviewee}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 11, color: '#94a3b8' }}>{p.cycle}</div>
                <span style={{ fontSize: 10, fontWeight: 600, background: '#fef2f2', color: '#dc2626', border: '1px solid #fecaca', borderRadius: 20, padding: '1px 7px', marginTop: 2, display: 'inline-block' }}>{p.task_status}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  // Help commands list
  if (data.commands?.length) {
    return (
      <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {data.commands.map((cmd, i) => (
          <button
            key={i}
            onClick={() => onSuggest?.(cmd)}
            style={{
              fontSize: 12, fontWeight: 500, padding: '5px 12px', borderRadius: 20,
              border: '1px solid #e2e8f0', background: '#f8fafc', color: '#334155',
              cursor: 'pointer', transition: 'background 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.background = '#eef2ff'}
            onMouseLeave={e => e.currentTarget.style.background = '#f8fafc'}
          >
            {cmd}
          </button>
        ))}
      </div>
    );
  }

  return null;
}

/* ─── Smart timestamp helpers ───────────────────────────────────────────────── */
function fmtIso(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString([], { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}
function _dayOf(ts) {
  const d = new Date(ts);
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}
function formatMsgTime(ts) {
  if (!ts) return '';
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
function formatDateLabel(ts) {
  if (!ts) return '';
  const now = new Date();
  const today     = _dayOf(now.toISOString());
  const yesterday = new Date(today); yesterday.setDate(yesterday.getDate() - 1);
  const msgDay    = _dayOf(ts);
  if (msgDay.getTime() === today.getTime())     return 'Today';
  if (msgDay.getTime() === yesterday.getTime()) return 'Yesterday';
  return new Date(ts).toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' });
}

/* ─── Date separator ────────────────────────────────────────────────────────── */
function DateSeparator({ label }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '6px 0' }}>
      <div style={{ flex: 1, height: 1, background: '#f1f5f9' }} />
      <span style={{
        fontSize: 10.5, color: '#94a3b8', fontWeight: 600,
        letterSpacing: '0.05em', whiteSpace: 'nowrap',
        background: '#fafbfc', padding: '2px 10px',
        borderRadius: 20, border: '1px solid #f1f5f9',
      }}>
        {label}
      </span>
      <div style={{ flex: 1, height: 1, background: '#f1f5f9' }} />
    </div>
  );
}

/* ─── Copy button ───────────────────────────────────────────────────────────── */
function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const handle = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <Tooltip title={copied ? 'Copied!' : 'Copy'}>
      <button onClick={handle} style={{
        background: 'none', border: 'none', cursor: 'pointer',
        color: '#94a3b8', padding: 4, borderRadius: 4,
        display: 'flex', alignItems: 'center',
      }}>
        {copied ? <CheckOutlined style={{ fontSize: 12 }} /> : <CopyOutlined style={{ fontSize: 12 }} />}
      </button>
    </Tooltip>
  );
}

/* ─── Message bubble ────────────────────────────────────────────────────────── */
function MessageBubble({ msg, onSuggest, onDirectAction, role, onNavigate }) {
  const isUser = msg.role === 'user';
  const isError = msg.status === 'failed' || msg.status === 'rejected';
  const isClarify = !isUser && msg.status === 'clarify';
  const isNeedsInput = !isUser && msg.status === 'needs_input';
  const clarifyChips = isClarify ? (ROLE_SUGGESTIONS[role] || DEFAULT_SUGGESTIONS) : [];

  return (
    <div style={{
      display: 'flex', gap: 10, animation: 'fadeSlideIn 0.25s ease',
      justifyContent: isUser ? 'flex-end' : 'flex-start',
      alignItems: 'flex-start',
    }}>
      {!isUser && (
        <Avatar size={32} style={{
          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
          flexShrink: 0, marginTop: 2,
        }}>
          <RobotOutlined style={{ fontSize: 14 }} />
        </Avatar>
      )}

      <div style={{ maxWidth: '75%', minWidth: 60 }}>
        {isUser ? (
          <div style={{
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            color: '#fff', borderRadius: '18px 18px 4px 18px',
            padding: '10px 16px', fontSize: 14, lineHeight: 1.6,
            boxShadow: '0 2px 8px rgba(102,126,234,0.3)',
          }}>
            {msg.text}
          </div>
        ) : (
          <div>
            <div style={{
              background: isError ? '#fff5f5' : isNeedsInput ? '#fffbeb' : '#fff',
              border: `1px solid ${isError ? '#fed7d7' : isNeedsInput ? '#fcd34d' : '#e2e8f0'}`,
              borderRadius: '4px 18px 18px 18px',
              padding: '12px 16px', fontSize: 14, lineHeight: 1.7,
              boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
              color: isError ? '#c53030' : '#1e293b',
            }}>
              <span style={{ whiteSpace: 'pre-wrap' }}>
                {isClarify ? "I didn't quite understand that. Here are some things I can help with:" : msg.text}
                {msg.status === 'streaming' && (
                  <span style={{ display: 'inline-block', width: 2, height: '0.85em', background: '#667eea', animation: 'wblink 0.8s infinite', verticalAlign: 'text-bottom', marginLeft: 1, borderRadius: 1 }} />
                )}
              </span>
              {isClarify && (
                <div style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {clarifyChips.map((s) => (
                    <button
                      key={s.label}
                      onClick={() => onSuggest?.(s.label)}
                      style={{
                        background: '#fff', border: '1px solid #e2e8f0', borderRadius: 20,
                        padding: '7px 14px', cursor: 'pointer', fontSize: 13, color: '#374151',
                        display: 'flex', alignItems: 'center', gap: 7, fontWeight: 500,
                        boxShadow: '0 1px 3px rgba(0,0,0,0.06)', transition: 'all 0.15s',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.borderColor = '#667eea';
                        e.currentTarget.style.color = '#667eea';
                        e.currentTarget.style.background = '#eef2ff';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.borderColor = '#e2e8f0';
                        e.currentTarget.style.color = '#374151';
                        e.currentTarget.style.background = '#fff';
                      }}
                    >
                      <span>{s.icon}</span>{s.label}
                    </button>
                  ))}
                </div>
              )}
              {!isClarify && <DataCard data={msg.data} onPick={onSuggest} onDirectAction={onDirectAction} />}
              {/* Action buttons for successful commands */}
              {!isClarify && msg.status === 'success' && msg.data?.template_id && (
                <button
                  onClick={() => onNavigate?.('/hr/templates')}
                  style={{
                    marginTop: 10, display: 'inline-flex', alignItems: 'center', gap: 6,
                    background: 'linear-gradient(135deg,#667eea,#764ba2)', color: '#fff',
                    border: 'none', borderRadius: 8, padding: '7px 14px',
                    fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
                    boxShadow: '0 2px 8px rgba(102,126,234,0.3)', transition: 'all 0.2s',
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.opacity = '0.88'}
                  onMouseLeave={(e) => e.currentTarget.style.opacity = '1'}
                >
                  📋 View Template →
                </button>
              )}
              {!isClarify && msg.status === 'success' && msg.data?.cycle_id && (
                <button
                  onClick={() => onNavigate?.('/hr/cycles')}
                  style={{
                    marginTop: 10, display: 'inline-flex', alignItems: 'center', gap: 6,
                    background: 'linear-gradient(135deg,#10b981,#059669)', color: '#fff',
                    border: 'none', borderRadius: 8, padding: '7px 14px',
                    fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
                    boxShadow: '0 2px 8px rgba(16,185,129,0.3)', transition: 'all 0.2s',
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.opacity = '0.88'}
                  onMouseLeave={(e) => e.currentTarget.style.opacity = '1'}
                >
                  🔄 View Cycle →
                </button>
              )}
              {isNeedsInput && (
                <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 6, color: '#92400e', fontSize: 12, fontWeight: 500 }}>
                  <span style={{ animation: 'pulse 1.5s infinite', display: 'inline-block' }}>✏️</span>
                  <span>Type your answer below…</span>
                </div>
              )}
            </div>

            {/* Suggestions chips */}
            {msg.suggestions?.length > 0 && (
              <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {msg.suggestions.map((s) => (
                  <button
                    key={s}
                    onClick={() => onSuggest?.(s)}
                    style={{
                      fontSize: 12, fontWeight: 500, padding: '4px 12px', borderRadius: 20,
                      border: '1px solid #c7d2fe', background: '#eef2ff', color: '#4338ca',
                      cursor: 'pointer', transition: 'all 0.15s',
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.background = '#667eea'; e.currentTarget.style.color = '#fff'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = '#eef2ff'; e.currentTarget.style.color = '#4338ca'; }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}

            {/* Bottom row: status + copy */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4, paddingLeft: 4 }}>
              {msg.status && !['needs_input', 'pending'].includes(msg.status) && (
                <span style={{ fontSize: 11, color: '#94a3b8' }}>
                  {msg.status === 'success' ? '✓' : msg.status === 'awaiting_confirmation' ? '⏳' : msg.status === 'cancelled' ? '✗' : '✗'}&nbsp;
                  {msg.status.replace(/_/g, ' ')}
                </span>
              )}
              {msg.text && <CopyButton text={msg.text} />}
            </div>
          </div>
        )}

        {/* Timestamp */}
        <div style={{
          fontSize: 10, color: '#cbd5e1', marginTop: 3,
          textAlign: isUser ? 'right' : 'left', paddingInline: 4,
        }}>
          {formatMsgTime(msg.ts)}
        </div>
      </div>

      {isUser && (
        <Avatar size={32} style={{ background: '#e2e8f0', flexShrink: 0, marginTop: 2 }}>
          <UserOutlined style={{ color: '#64748b', fontSize: 14 }} />
        </Avatar>
      )}
    </div>
  );
}

/* ─── Relative date helper ──────────────────────────────────────────────────── */
function _relativeDate(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  const diffDays = Math.floor((new Date() - d) / 86400000);
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7)  return `${diffDays} days ago`;
  return d.toLocaleDateString([], { day: 'numeric', month: 'short' });
}

/* ─── Capabilities panel (inline, replaces chat area) ───────────────────────── */
function CapabilitiesPanel({ role, onClose }) {
  const caps = CAPABILITIES[role] || CAPABILITIES.EMPLOYEE;
  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '24px 28px', background: '#fafbfc' }}>
      <div style={{ maxWidth: 640, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <div style={{ fontWeight: 700, fontSize: 16, color: '#1e293b' }}>What can Gamyam AI do?</div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 12, color: '#667eea', fontWeight: 600, padding: '4px 10px', borderRadius: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
            ← Back to chat
          </button>
        </div>

        <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 12, padding: '14px 18px', marginBottom: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12 }}>
            <CheckCircleOutlined style={{ color: '#22c55e', fontSize: 14 }} />
            <span style={{ fontWeight: 700, fontSize: 13, color: '#15803d' }}>I CAN do these for you</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 6 }}>
            {caps.can.map((item, i) => (
              <div key={i} style={{ fontSize: 12.5, display: 'flex', alignItems: 'center', gap: 7, background: 'rgba(255,255,255,0.75)', borderRadius: 8, padding: '6px 10px', border: '1px solid rgba(134,239,172,0.6)', color: '#166534' }}>
                <span>{item.icon}</span><span style={{ fontWeight: 500 }}>{item.text}</span>
              </div>
            ))}
          </div>
        </div>

        <div style={{ background: '#fff5f5', border: '1px solid #fecaca', borderRadius: 12, padding: '14px 18px', marginBottom: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
            <CloseCircleOutlined style={{ color: '#ef4444', fontSize: 14 }} />
            <span style={{ fontWeight: 700, fontSize: 13, color: '#dc2626' }}>Use the UI for these</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {caps.cannot.map((item, i) => (
              <div key={i} style={{ fontSize: 12.5, display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(255,255,255,0.8)', borderRadius: 8, padding: '6px 10px', border: '1px solid rgba(254,202,202,0.8)', color: '#7f1d1d' }}>
                <span>↗</span>
                <span><strong>{item.text}</strong><span style={{ color: '#b91c1c', fontWeight: 400 }}> — go to {item.goto}</span></span>
              </div>
            ))}
          </div>
        </div>

        <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 12, padding: '12px 18px', fontSize: 12.5, color: '#1d4ed8', lineHeight: 1.7 }}>
          <strong>💡 Tip:</strong> Just type naturally! Try <em>"any tasks for me?"</em>, <em>"create a Q1 cycle"</em>, or <em>"who hasn't submitted reviews?"</em>
        </div>
      </div>
    </div>
  );
}

/* ─── getSuggestions helper ─────────────────────────────────────────────────── */
// backendSuggestions: array from the SSE done event (set by backend per-intent or LLM)
// data: the structured data payload — used only as a fallback when backend sends nothing
function getSuggestions(backendSuggestions, data) {
  if (backendSuggestions?.length) return backendSuggestions;
  // Legacy fallback — keeps suggestions working for any edge case not yet covered
  if (!data) return [];
  if (data.profile)     return ['Show my manager', 'Show my cycles', 'Show my tasks'];
  if (data.cycles)      return ['Show cycle deadlines', 'Show participation stats'];
  if (data.nominations) return ['Show my cycles', 'Show pending reviews'];
  if (data.tasks)       return ['Show my feedback', 'Show my report'];
  return [];
}

/* ─── Main chat page ────────────────────────────────────────────────────────── */
export default function ChatPage() {
  const user        = useAuthStore((s) => s.user);
  const suggestions = ROLE_SUGGESTIONS[user?.role] || DEFAULT_SUGGESTIONS;

  const [messages,           setMessages]           = useState([]);
  const [input,              setInput]              = useState('');
  const [loading,            setLoading]            = useState(false);
  const [streaming,          setStreaming]           = useState(false);
  const [sessionId,          setSessionId]          = useState(() => localStorage.getItem('chat_session_id') || '');
  const [awaitConfirm,       setAwaitConfirm]       = useState(false);
  const [pendingConfirmData, setPendingConfirmData]  = useState(null);
  const [sessions,           setSessions]           = useState([]);
  const [sessionsLoading,    setSessionsLoading]    = useState(false);
  const [activeTitle,        setActiveTitle]        = useState('');
  const [showInfo,           setShowInfo]           = useState(false);
  const [isOnline,           setIsOnline]           = useState(navigator.onLine);
  const [sessionSearch,      setSessionSearch]      = useState('');
  const [hoveredSessionId,   setHoveredSessionId]   = useState(null);
  const [editingSessionId,   setEditingSessionId]   = useState(null);
  const [editSessionValue,   setEditSessionValue]   = useState('');
  const [pinnedIds,          setPinnedIds]          = useState(() => {
    try { return JSON.parse(localStorage.getItem('chat_pinned_sessions') || '[]'); } catch { return []; }
  });
  const navigate      = useNavigate();
  const bottomRef     = useRef(null);
  const inputRef      = useRef(null);
  const fileInputRef  = useRef(null);
  const retryCountRef = useRef(0);
  const bcRef         = useRef(null);   // BroadcastChannel for cross-tab sync
  const isSendingRef  = useRef(false);  // Immediate guard against double-send

  // Cross-tab sync: listen for messages sent in ChatWidget and reload if same session
  useEffect(() => {
    if (!window.BroadcastChannel) return;
    const bc = new BroadcastChannel('gamyam_chat_sync');
    bcRef.current = bc;
    bc.onmessage = (e) => {
      if (e.data?.type === 'new_message' && e.data.session_id === sessionId && !loading) {
        getChatHistory(e.data.session_id).then((res) => {
          setMessages(_logsToMessages((res.data.history || []).reverse()));
        }).catch(() => {});
      }
    };
    return () => bc.close();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  // Voice input — auto-send final result when mic stops
  const handleVoiceFinal = useCallback((text) => {
    if (!text.trim() || awaitConfirm || loading) return;
    setInput(text);
    setTimeout(() => handleSend(text), 150);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [awaitConfirm, loading]);
  const { listening: voiceListening, transcript: voiceTranscript, toggleListening } = useSpeechToText({ onFinalResult: handleVoiceFinal });
  useEffect(() => { if (voiceListening) setInput(voiceTranscript); }, [voiceListening, voiceTranscript]);

  // Inject pulse keyframe once
  useEffect(() => {
    if (!document.getElementById('voice-pulse-kf')) {
      const s = document.createElement('style');
      s.id = 'voice-pulse-kf';
      s.textContent = '@keyframes voicePulse{0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,0.5)}50%{box-shadow:0 0 0 7px rgba(239,68,68,0)}}';
      document.head.appendChild(s);
    }
  }, []);

  useEffect(() => { loadInitial(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, loading]);

  // Online/offline detection
  useEffect(() => {
    const handleOnline  = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    window.addEventListener('online',  handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online',  handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  const _logsToMessages = (logs) => {
    const pairs = [];
    logs.forEach((log) => {
      if (log.message === '[user cancelled]' || log.message === '[confirmed]') return;
      pairs.push({ role: 'user', text: log.message, ts: log.created_at });
      if (log.response_message) pairs.push({ role: 'assistant', text: log.response_message, status: log.execution_status, data: log.response_data || {}, ts: log.created_at });
    });
    return pairs;
  };

  const loadInitial = async () => {
    setSessionsLoading(true);
    try {
      const [histRes, sessRes] = await Promise.all([getChatHistory(), getChatSessions()]);
      setMessages(_logsToMessages((histRes.data.history || []).reverse()));
      const sessionList = sessRes.data.sessions || [];
      setSessions(sessionList);
      const cur = localStorage.getItem('chat_session_id');
      if (cur) {
        const match = sessionList.find((s) => s.session_id === cur);
        if (match) setActiveTitle(match.title || match.first_message || '');
      }
    } catch { /* silent */ }
    finally { setSessionsLoading(false); }
  };

  const refreshSessions = async (currentSid) => {
    try {
      const res = await getChatSessions();
      const list = res.data.sessions || [];
      setSessions(list);
      const sid = currentSid || sessionId;
      if (sid) {
        const match = list.find((s) => s.session_id === sid);
        if (match?.title) setActiveTitle(match.title);
      }
    } catch { /* silent */ }
  };

  const addMessage = (role, text, extra = {}) =>
    setMessages((prev) => [...prev, { role, text, ...extra, ts: new Date().toISOString() }]);

  // PDF upload handler
  const handleFileUpload = useCallback(async (e) => {
    const file = e.target.files?.[0];
    if (!fileInputRef.current) return;
    fileInputRef.current.value = '';
    if (!file) return;
    if (!file.name.match(/\.(pdf|txt)$/i)) {
      addMessage('assistant', 'Only PDF and TXT files are supported.', { status: 'error', data: {} });
      return;
    }
    addMessage('user', `📎 ${file.name}`, { status: 'sent', data: {} });
    addMessage('assistant', 'Reading your file…', { status: 'streaming', data: {} });
    try {
      const res = await uploadChatFile(file);
      const { extracted_text, filename } = res.data;
      setMessages((prev) => {
        const upd = [...prev];
        upd[upd.length - 1] = { ...upd[upd.length - 1], text: `Parsing **${filename}**…`, status: 'streaming' };
        return upd;
      });
      await handleSend(`__PDF__:${filename}||${extracted_text}`, `📎 Create template from: ${filename}`);
    } catch (err) {
      const msg = err?.response?.data?.error || 'Could not read the file. Please try again.';
      setMessages((prev) => {
        const upd = [...prev];
        upd[upd.length - 1] = { ...upd[upd.length - 1], text: msg, status: 'error' };
        return upd;
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSend = async (text, displayOverride) => {
    const isPick = text && typeof text === 'object' && text.id;
    const msg    = isPick ? text.id : (text || input).trim();
    const label  = displayOverride || (isPick ? text.label : msg);
    if (!msg || loading || isSendingRef.current) return;
    isSendingRef.current = true;
    setInput('');
    inputRef.current?.focus();
    if (!displayOverride) addMessage('user', label);
    setLoading(true);
    setStreaming(false);
    retryCountRef.current = 0;

    const attemptSend = async () => {
      try {
        await sendMessageStream(
          msg, sessionId, isPick ? label : null,
          (chunk) => {
            setStreaming((was) => {
              if (!was) {
                setMessages((prev) => [...prev, { role: 'assistant', text: chunk, status: 'streaming', data: {}, ts: new Date().toISOString() }]);
              } else {
                setMessages((prev) => {
                  const upd = [...prev];
                  const last = upd[upd.length - 1];
                  if (last?.role === 'assistant') upd[upd.length - 1] = { ...last, text: last.text + chunk };
                  return upd;
                });
              }
              return true;
            });
          },
          (data) => {
            let newSid = sessionId;
            if (data.session_id && data.session_id !== sessionId) {
              newSid = data.session_id;
              setSessionId(newSid);
              localStorage.setItem('chat_session_id', newSid);
            }
            // Notify other tabs (ChatWidget) that a new message arrived
            bcRef.current?.postMessage({ type: 'new_message', session_id: data.session_id || sessionId });
            const isConfirm = data.status === 'awaiting_confirmation';
            setAwaitConfirm(isConfirm);
            if (isConfirm) setPendingConfirmData(data.data || null);
            else setPendingConfirmData(null);
            setStreaming((was) => {
              if (was) {
                setMessages((prev) => {
                  const upd = [...prev];
                  const last = upd[upd.length - 1];
                  if (last?.role === 'assistant') upd[upd.length - 1] = {
                    ...last,
                    text:        data.message || last.text,
                    status:      data.status,
                    data:        data.data || {},
                    suggestions: data.status === 'success' ? getSuggestions(data.suggestions, data.data) : undefined,
                  };
                  return upd;
                });
              } else {
                addMessage('assistant', data.message, {
                  status:      data.status,
                  data:        data.data || {},
                  suggestions: data.status === 'success' ? getSuggestions(data.suggestions, data.data) : undefined,
                });
              }
              return false;
            });
            setTimeout(() => refreshSessions(newSid), 6000);
          },
        );
      } catch (err) {
        // 429 rate limit
        if (err.status === 429) {
          const errMsg = "You've reached the message limit. Please wait a moment before sending again.";
          setMessages((prev) => {
            const upd = [...prev];
            const last = upd[upd.length - 1];
            if (last?.role === 'assistant' && last.status === 'streaming') { upd[upd.length - 1] = { ...last, text: errMsg, status: 'failed' }; return upd; }
            return [...prev, { role: 'assistant', text: errMsg, status: 'failed', data: {}, ts: new Date().toISOString() }];
          });
          return;
        }
        // Network error (no .status) → retry up to 2 times
        if (!err.status && retryCountRef.current < 2) {
          retryCountRef.current += 1;
          setMessages((prev) => {
            const upd = [...prev];
            const last = upd[upd.length - 1];
            const retryMsg = `Connection lost, retrying… (${retryCountRef.current}/2)`;
            if (last?.role === 'assistant') upd[upd.length - 1] = { ...last, text: retryMsg, status: 'streaming' };
            return upd;
          });
          await new Promise((r) => setTimeout(r, 2000));
          return attemptSend();
        }
        const finalMsg = !err.status ? 'Connection lost. Please try again.' : 'Something went wrong.';
        setMessages((prev) => {
          const upd = [...prev];
          const last = upd[upd.length - 1];
          if (last?.role === 'assistant' && last.status === 'streaming') { upd[upd.length - 1] = { ...last, text: finalMsg, status: 'failed' }; return upd; }
          return [...prev, { role: 'assistant', text: finalMsg, status: 'failed', data: {}, ts: new Date().toISOString() }];
        });
      } finally {
        setLoading(false);
        setStreaming(false);
      }
    };

    try {
      await attemptSend();
    } finally {
      isSendingRef.current = false;
    }
  };

  const handleConfirm = async (confirmed) => {
    setAwaitConfirm(false);
    setPendingConfirmData(null);
    setLoading(true);
    try {
      const res  = await confirmAction(sessionId, confirmed);
      const data = res.data;
      addMessage('assistant', data.message, { status: data.status, data: data.data || {} });
      setSessionId('');
      localStorage.removeItem('chat_session_id');
    } catch {
      addMessage('assistant', 'Confirmation failed. Please try again.', { status: 'failed' });
    } finally {
      setLoading(false);
    }
  };

  const handleDirectAction = async (action, nominationId) => {
    if (loading) return;
    const label     = action === 'approve_nomination' ? 'Approve nomination' : 'Reject nomination';
    const intentMsg = action === 'approve_nomination' ? 'approve nomination' : 'reject nomination';
    addMessage('user', label);
    setLoading(true);
    try {
      const res1 = await sendMessage(intentMsg, sessionId);
      const d1 = res1.data;
      let sid = sessionId;
      if (d1.session_id && d1.session_id !== sid) { sid = d1.session_id; setSessionId(sid); localStorage.setItem('chat_session_id', sid); }
      if (d1.missing_field === 'nomination_id') {
        const res2 = await sendMessage(nominationId, sid);
        const d2 = res2.data;
        if (d2.session_id && d2.session_id !== sid) { setSessionId(d2.session_id); localStorage.setItem('chat_session_id', d2.session_id); }
        const isConfirm = d2.status === 'awaiting_confirmation';
        setAwaitConfirm(isConfirm);
        if (isConfirm) setPendingConfirmData(d2.data);
        addMessage('assistant', d2.message, { status: d2.status, data: d2.data || {} });
      } else {
        const isConfirm = d1.status === 'awaiting_confirmation';
        setAwaitConfirm(isConfirm);
        if (isConfirm) setPendingConfirmData(d1.data);
        addMessage('assistant', d1.message, { status: d1.status, data: d1.data || {} });
      }
    } catch {
      addMessage('assistant', 'Action failed. Please try again.', { status: 'failed' });
    } finally {
      setLoading(false);
    }
  };

  const doNewChat = async () => {
    setMessages([]);
    setSessionId('');
    localStorage.removeItem('chat_session_id');
    setAwaitConfirm(false);
    setPendingConfirmData(null);
    setInput('');
    setActiveTitle('');
    setShowInfo(false);
    try { await discardSession(); } catch { /* silent */ }
    inputRef.current?.focus();
  };

  const handleNewChat = () => {
    if (messages.length > 0) {
      Modal.confirm({
        title: 'Start a new chat?',
        content: 'This will clear the current conversation.',
        okText: 'Yes, start fresh',
        okType: 'danger',
        cancelText: 'Cancel',
        onOk: doNewChat,
      });
    } else {
      doNewChat();
    }
  };

  const handleSelectSession = async (session) => {
    try {
      const res = await getChatHistory(session.session_id);
      setMessages(_logsToMessages(res.data.history || []));
      setSessionId(session.session_id);
      localStorage.setItem('chat_session_id', session.session_id);
      setActiveTitle(session.title || session.first_message || '');
      setAwaitConfirm(false);
      setPendingConfirmData(null);
      setShowInfo(false);
    } catch { /* silent */ }
  };

  const handleDeleteAll = async () => {
    try {
      await deleteAllSessions();
      setSessions([]);
      setMessages([]);
      setSessionId('');
      localStorage.removeItem('chat_session_id');
    } catch { /* silent */ }
  };

  const handleDeleteSession = async (sid) => {
    try {
      await deleteSession(sid);
      setSessions((prev) => prev.filter(s => s.session_id !== sid));
      if (sid === sessionId) {
        setMessages([]);
        setSessionId('');
        localStorage.removeItem('chat_session_id');
        setActiveTitle('');
      }
    } catch { /* silent */ }
  };

  const handleRenameSession = async (sid, title) => {
    try {
      await renameSession(sid, title);
      setSessions((prev) => prev.map(s => s.session_id === sid ? { ...s, title } : s));
      if (sid === sessionId) setActiveTitle(title);
    } catch { /* silent */ }
  };

  const togglePin = (sid) => {
    setPinnedIds((prev) => {
      const next = prev.includes(sid) ? prev.filter(id => id !== sid) : [...prev, sid];
      localStorage.setItem('chat_pinned_sessions', JSON.stringify(next));
      return next;
    });
  };

  const isEmpty = messages.length === 0;

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 112px)' }}>

      {/* ── Left Sidebar ────────────────────────────────────────────────── */}
      <div style={{ width: 260, flexShrink: 0, borderRight: '1px solid #e2e8f0', background: '#fafbfc', display: 'flex', flexDirection: 'column' }}>

        {/* Brand + New Chat */}
        <div style={{ padding: '16px 14px 12px', borderBottom: '1px solid #f1f5f9' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, background: 'linear-gradient(135deg,#667eea,#764ba2)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, boxShadow: '0 3px 10px rgba(102,126,234,0.3)' }}>
              <RobotOutlined style={{ fontSize: 17, color: '#fff' }} />
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 13.5, color: '#1e293b', lineHeight: 1.2 }}>Gamyam AI</div>
              <div style={{ fontSize: 10.5, color: '#94a3b8' }}>Your 360° assistant</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              onClick={handleNewChat}
              style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, background: 'linear-gradient(135deg,#667eea,#764ba2)', color: '#fff', border: 'none', borderRadius: 8, padding: '8px 14px', fontSize: 12.5, fontWeight: 600, cursor: 'pointer', boxShadow: '0 2px 8px rgba(102,126,234,0.25)' }}
              onMouseEnter={(e) => e.currentTarget.style.opacity = '0.9'}
              onMouseLeave={(e) => e.currentTarget.style.opacity = '1'}
            >
              <PlusOutlined style={{ fontSize: 11 }} /> New Chat
            </button>
            {sessions.length > 0 && (
              <Popconfirm
                title="Delete all chats?"
                description="This will permanently remove all your chat history."
                okText="Delete All"
                okButtonProps={{ danger: true }}
                cancelText="Cancel"
                onConfirm={handleDeleteAll}
              >
                <button
                  style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'none', border: '1px solid #fca5a5', borderRadius: 8, padding: '8px 10px', fontSize: 12, color: '#ef4444', cursor: 'pointer' }}
                  onMouseEnter={(e) => e.currentTarget.style.background = '#fef2f2'}
                  onMouseLeave={(e) => e.currentTarget.style.background = 'none'}
                >
                  <DeleteOutlined style={{ fontSize: 12 }} />
                </button>
              </Popconfirm>
            )}
          </div>
        </div>

        {/* Search */}
        <div style={{ padding: '6px 12px 8px', borderBottom: '1px solid #f1f5f9' }}>
          <input
            type="text"
            placeholder="Search conversations…"
            value={sessionSearch}
            onChange={(e) => setSessionSearch(e.target.value)}
            style={{
              width: '100%', boxSizing: 'border-box',
              border: 'none', borderBottom: '1.5px solid #e2e8f0',
              outline: 'none', background: 'transparent',
              fontSize: 12, color: '#1e293b', padding: '4px 2px',
              fontFamily: 'inherit',
            }}
            onFocus={(e) => { e.target.style.borderBottomColor = '#667eea'; }}
            onBlur={(e) => { e.target.style.borderBottomColor = '#e2e8f0'; }}
          />
        </div>

        {/* Sessions list */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px' }}>
          {sessionsLoading && <div style={{ textAlign: 'center', padding: '20px 0', color: '#94a3b8', fontSize: 12 }}>Loading…</div>}
          {!sessionsLoading && sessions.length === 0 && (
            <div style={{ textAlign: 'center', padding: '24px 12px', color: '#94a3b8', fontSize: 11.5, lineHeight: 1.6 }}>No past conversations yet.<br />Start chatting to see history here.</div>
          )}
          {!sessionsLoading && (() => {
            const filtered = sessions.filter(s =>
              (s.title || s.first_message || '').toLowerCase().includes(sessionSearch.toLowerCase())
            );
            const sorted = [
              ...filtered.filter(s => pinnedIds.includes(s.session_id)),
              ...filtered.filter(s => !pinnedIds.includes(s.session_id)),
            ];
            if (filtered.length === 0 && sessionSearch) {
              return <div style={{ textAlign: 'center', padding: '24px 12px', color: '#94a3b8', fontSize: 11.5 }}>No matching conversations.</div>;
            }
            return sorted.map((s) => {
              const isActive = s.session_id === sessionId;
              const isPinned = pinnedIds.includes(s.session_id);
              const isHovered = hoveredSessionId === s.session_id;
              const isEditing = editingSessionId === s.session_id;
              const title = s.title || s.first_message || 'Conversation';
              return (
                <div
                  key={s.session_id}
                  style={{ position: 'relative', marginBottom: 2 }}
                  onMouseEnter={() => setHoveredSessionId(s.session_id)}
                  onMouseLeave={() => setHoveredSessionId(null)}
                >
                  <div
                    onClick={() => !isEditing && handleSelectSession(s)}
                    style={{
                      width: '100%', textAlign: 'left',
                      background: isActive ? '#eef2ff' : isHovered ? '#f1f5f9' : 'transparent',
                      border: isActive ? '1px solid #c7d2fe' : isHovered ? '1px solid #e2e8f0' : '1px solid transparent',
                      borderRadius: 8, padding: '8px 10px', cursor: 'pointer', transition: 'all 0.15s',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4, paddingRight: isHovered && !isEditing ? 50 : 0 }}>
                      {isPinned && <span style={{ fontSize: 10, flexShrink: 0 }}>📌</span>}
                      {isEditing ? (
                        <input
                          autoFocus
                          value={editSessionValue}
                          onChange={(e) => setEditSessionValue(e.target.value)}
                          onBlur={() => {
                            const t = editSessionValue.trim();
                            if (t) handleRenameSession(s.session_id, t);
                            setEditingSessionId(null);
                          }}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault();
                              const t = editSessionValue.trim();
                              if (t) handleRenameSession(s.session_id, t);
                              setEditingSessionId(null);
                            }
                            if (e.key === 'Escape') setEditingSessionId(null);
                          }}
                          onClick={(e) => e.stopPropagation()}
                          style={{
                            flex: 1, fontSize: 11.5, fontWeight: 600,
                            color: isActive ? '#4338ca' : '#334155',
                            border: '1px solid #667eea', borderRadius: 4, padding: '1px 5px',
                            outline: 'none', background: '#fff',
                          }}
                        />
                      ) : (
                        <span style={{ fontSize: 12, fontWeight: 600, color: isActive ? '#4338ca' : '#334155', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', flex: 1 }}>
                          {title}
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 2 }}>{_relativeDate(s.last_at)}</div>
                  </div>
                  {/* Action buttons on hover */}
                  {isHovered && !isEditing && (
                    <div style={{ position: 'absolute', top: 8, right: 8, display: 'flex', gap: 2 }}>
                      <button
                        title={isPinned ? 'Unpin' : 'Pin'}
                        onClick={(e) => { e.stopPropagation(); togglePin(s.session_id); }}
                        style={{ background: isPinned ? '#eef2ff' : '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 4, padding: '2px 4px', cursor: 'pointer', color: isPinned ? '#667eea' : '#94a3b8', display: 'flex', alignItems: 'center' }}
                      >
                        <PushpinOutlined style={{ fontSize: 10 }} />
                      </button>
                      <button
                        title="Rename"
                        onClick={(e) => { e.stopPropagation(); setEditingSessionId(s.session_id); setEditSessionValue(s.title || s.first_message || ''); }}
                        style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 4, padding: '2px 4px', cursor: 'pointer', color: '#94a3b8', display: 'flex', alignItems: 'center' }}
                      >
                        <EditOutlined style={{ fontSize: 10 }} />
                      </button>
                      <button
                        title="Delete"
                        onClick={(e) => { e.stopPropagation(); handleDeleteSession(s.session_id); }}
                        style={{ background: '#fff5f5', border: '1px solid #fecaca', borderRadius: 4, padding: '2px 4px', cursor: 'pointer', color: '#ef4444', display: 'flex', alignItems: 'center' }}
                      >
                        <DeleteOutlined style={{ fontSize: 10 }} />
                      </button>
                    </div>
                  )}
                </div>
              );
            });
          })()}
        </div>

        {/* What can I do */}
        <div style={{ borderTop: '1px solid #f1f5f9', padding: '8px 10px' }}>
          <button
            onClick={() => setShowInfo((v) => !v)}
            style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 7, background: showInfo ? '#eef2ff' : 'none', border: 'none', cursor: 'pointer', color: showInfo ? '#667eea' : '#64748b', fontSize: 12, fontWeight: 500, padding: '7px 8px', borderRadius: 6, transition: 'all 0.15s' }}
          >
            <InfoCircleOutlined style={{ fontSize: 13 }} /> What can I do?
          </button>
        </div>
      </div>

      {/* ── Main Area ───────────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#fff' }}>

        {/* Offline banner */}
        {!isOnline && (
          <div style={{ background: '#fef2f2', borderBottom: '1px solid #fecaca', padding: '8px 24px', display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            <span style={{ fontSize: 13, color: '#dc2626', fontWeight: 500 }}>⚠️ You are offline. Check your connection.</span>
          </div>
        )}

        {showInfo ? (
          <CapabilitiesPanel role={user?.role} onClose={() => setShowInfo(false)} />
        ) : (
          <>
            {/* Chat header */}
            <div style={{ padding: '13px 24px', borderBottom: '1px solid #f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 14, color: activeTitle ? '#1e293b' : '#94a3b8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {activeTitle || (isEmpty ? 'New Chat' : 'Current conversation')}
              </div>
              <Tooltip title="Minimize to widget">
                <button
                  onClick={() => navigate(-1)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '4px 8px', borderRadius: 6, color: '#94a3b8', display: 'flex', alignItems: 'center', transition: 'all 0.15s' }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = '#f1f5f9'; e.currentTarget.style.color = '#667eea'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = '#94a3b8'; }}
                >
                  <ShrinkOutlined style={{ fontSize: 16 }} />
                </button>
              </Tooltip>
            </div>

            {/* Messages */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '20px 28px', display: 'flex', flexDirection: 'column', gap: 16 }}>
              {isEmpty && (
                <div style={{ textAlign: 'center', padding: '48px 20px 32px', maxWidth: 560, margin: '0 auto' }}>
                  <div style={{ width: 64, height: 64, borderRadius: 20, margin: '0 auto 16px', background: 'linear-gradient(135deg,#667eea,#764ba2)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 8px 24px rgba(102,126,234,0.35)' }}>
                    <RobotOutlined style={{ fontSize: 32, color: '#fff' }} />
                  </div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: '#1e293b', marginBottom: 8 }}>How can I help you today?</div>
                  <div style={{ fontSize: 14, color: '#64748b', marginBottom: 28 }}>Ask me anything about your 360° feedback cycles, tasks, or reports.</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'center' }}>
                    {suggestions.map((s) => (
                      <button key={s.label} onClick={() => handleSend(s.label)} style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: '10px 16px', cursor: 'pointer', fontSize: 13, color: '#374151', display: 'flex', alignItems: 'center', gap: 8, fontWeight: 500, boxShadow: '0 1px 3px rgba(0,0,0,0.06)', transition: 'all 0.15s' }}
                        onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#667eea'; e.currentTarget.style.color = '#667eea'; }}
                        onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#e2e8f0'; e.currentTarget.style.color = '#374151'; }}
                      >
                        <span>{s.icon}</span>{s.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((msg, i) => {
                const label = formatDateLabel(msg.ts);
                const prevLabel = i > 0 ? formatDateLabel(messages[i - 1].ts) : null;
                return (
                  <div key={`${msg.ts}-${i}`}>
                    {label && label !== prevLabel && <DateSeparator label={label} />}
                    <MessageBubble msg={msg} onSuggest={handleSend} onDirectAction={handleDirectAction} role={user?.role} onNavigate={navigate} />
                  </div>
                );
              })}

              {loading && !streaming && (
                <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                  <Avatar size={32} style={{ background: 'linear-gradient(135deg,#667eea,#764ba2)', flexShrink: 0 }}>
                    <RobotOutlined style={{ fontSize: 14 }} />
                  </Avatar>
                  <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '4px 18px 18px 18px', padding: '10px 16px', boxShadow: '0 1px 4px rgba(0,0,0,0.06)' }}>
                    <TypingDots />
                  </div>
                </div>
              )}

              <div ref={bottomRef} />
            </div>

            {/* Confirm banner */}
            {awaitConfirm && !loading && (
              <div style={{ margin: '0 24px 8px', background: 'linear-gradient(135deg,#eff6ff,#f0fdf4)', border: '1px solid #bfdbfe', borderRadius: 12, padding: '14px 18px', boxShadow: '0 2px 8px rgba(59,130,246,0.1)' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, color: '#1e40af', fontWeight: 700, marginBottom: 4 }}>⚡ Confirm this action?</div>
                    {pendingConfirmData && Object.keys(pendingConfirmData).length > 0 && (
                      <div style={{ fontSize: 12, color: '#1e40af', background: 'rgba(255,255,255,0.6)', borderRadius: 8, padding: '6px 10px', marginTop: 4 }}>
                        {Object.entries(pendingConfirmData).filter(([k]) => !['cycle_id'].includes(k)).map(([k, v]) => (
                          <div key={k}><span style={{ fontWeight: 600 }}>{k.replace(/_/g, ' ')}:</span> {String(v)}</div>
                        ))}
                      </div>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexShrink: 0, alignItems: 'center' }}>
                    <Button type="primary" size="small" onClick={() => handleConfirm(true)} style={{ borderRadius: 8, background: '#22c55e', borderColor: '#22c55e', fontWeight: 600 }}>✓ Confirm</Button>
                    <Button danger size="small" onClick={() => handleConfirm(false)} style={{ borderRadius: 8 }}>✗ Cancel</Button>
                  </div>
                </div>
              </div>
            )}

            {/* Input */}
            <div style={{ padding: '12px 24px 16px' }}>
              <div style={{ background: '#fff', border: '1.5px solid #e2e8f0', borderRadius: 16, padding: '10px 10px 10px 16px', display: 'flex', gap: 8, alignItems: 'center', boxShadow: '0 2px 12px rgba(0,0,0,0.06)', transition: 'border-color 0.2s' }}
                onFocusCapture={(e) => e.currentTarget.style.borderColor = '#667eea'}
                onBlurCapture={(e) => e.currentTarget.style.borderColor = '#e2e8f0'}
              >
                {/* Hidden file input */}
                <input ref={fileInputRef} type="file" accept=".pdf,.txt" style={{ display: 'none' }} onChange={handleFileUpload} />
                <Input.TextArea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !awaitConfirm) { e.preventDefault(); handleSend(); } }}
                  placeholder={awaitConfirm ? 'Please confirm or cancel the action above…' : voiceListening ? 'Listening…' : 'Ask anything… (Enter to send, Shift+Enter for new line)'}
                  autoSize={{ minRows: 1, maxRows: 5 }}
                  disabled={loading || awaitConfirm}
                  bordered={false}
                  style={{ fontSize: 14, resize: 'none', padding: 0, flex: 1, color: awaitConfirm ? '#94a3b8' : undefined }}
                />
                <Tooltip title={voiceListening ? 'Stop (will auto-send)' : 'Voice input — speak then auto-sends'}>
                  <button
                    onClick={toggleListening}
                    disabled={awaitConfirm || loading}
                    style={{
                      width: 36, height: 36, borderRadius: 10, border: 'none', flexShrink: 0,
                      background: voiceListening ? '#fee2e2' : 'transparent',
                      cursor: (awaitConfirm || loading) ? 'default' : 'pointer',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all 0.15s',
                      animation: voiceListening ? 'voicePulse 1.2s ease-in-out infinite' : 'none',
                    }}
                  >
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none"
                      stroke={voiceListening ? '#ef4444' : '#94a3b8'} strokeWidth="2.2"
                      strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
                      <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                      <line x1="12" y1="19" x2="12" y2="23"/>
                      <line x1="8" y1="23" x2="16" y2="23"/>
                    </svg>
                  </button>
                </Tooltip>
                {/* PDF upload button — HR/Super Admin only */}
                {['HR_ADMIN', 'SUPER_ADMIN'].includes(user?.role) && (
                  <Tooltip title="Upload PDF to create template">
                    <button onClick={() => fileInputRef.current?.click()} disabled={loading || awaitConfirm}
                      style={{ width: 36, height: 36, borderRadius: 10, border: 'none', background: 'transparent', cursor: loading ? 'default' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <PaperClipOutlined style={{ fontSize: 17, color: '#94a3b8' }} />
                    </button>
                  </Tooltip>
                )}
                <Tooltip title={awaitConfirm ? 'Confirm or cancel first' : 'Send (Enter)'}>
                  <Button type="primary" shape="circle" icon={<SendOutlined />} onClick={() => handleSend()} disabled={loading || awaitConfirm || !input.trim()}
                    style={{ background: input.trim() ? 'linear-gradient(135deg,#667eea,#764ba2)' : undefined, border: 'none', boxShadow: input.trim() ? '0 2px 8px rgba(102,126,234,0.4)' : undefined, flexShrink: 0 }}
                  />
                </Tooltip>
              </div>
              <div style={{ textAlign: 'center', fontSize: 11, color: '#cbd5e1', marginTop: 8 }}>
                <ThunderboltOutlined style={{ marginRight: 4 }} />Powered by Gamyam 360° AI · Responses may vary
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
