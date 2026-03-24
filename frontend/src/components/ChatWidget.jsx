import { useState, useRef, useEffect, useCallback } from 'react';
import { Input, Button, Avatar, Tooltip } from 'antd';
import {
  SendOutlined, RobotOutlined, UserOutlined,
  CloseOutlined, ExpandAltOutlined,
  InfoCircleOutlined, CheckCircleOutlined, CloseCircleOutlined,
  HistoryOutlined, PlusOutlined, ArrowLeftOutlined,
  CopyOutlined, CheckOutlined, DeleteOutlined, EditOutlined, PushpinOutlined,
  PaperClipOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { sendMessage, sendMessageStream, confirmAction, getChatHistory, getChatSessions, getSessionState, discardSession, deleteSession, renameSession, uploadChatFile } from '../api/chat';
import useAuthStore from '../store/authStore';
import { useSpeechToText } from '../hooks/useSpeechToText';

/* ─── Chat capabilities per role ────────────────────────────────────────────── */
const CAPABILITIES = {
  EMPLOYEE: {
    can: [
      { icon: '✅', text: 'Show my tasks' },
      { icon: '📊', text: 'Show my report' },
      { icon: '💬', text: 'Show my feedback' },
      { icon: '🤝', text: 'Show my nominations' },
      { icon: '👥', text: 'Nominate peers' },
      { icon: '🔄', text: 'Show cycles I am in' },
      { icon: '📅', text: 'Show upcoming deadlines' },
      { icon: '📢', text: 'Show announcements' },
    ],
    cannot: [
      { text: 'Fill feedback form', goto: 'My Tasks page' },
      { text: 'View detailed charts', goto: 'My Report page' },
    ],
  },
  MANAGER: {
    can: [
      { icon: '✅', text: 'Show my tasks' },
      { icon: '💬', text: 'Show my feedback / report' },
      { icon: '🤝', text: 'Show my nominations' },
      { icon: '👥', text: 'Nominate peers' },
      { icon: '🔄', text: 'Show cycles I am in' },
      { icon: '📅', text: 'Show upcoming deadlines' },
      { icon: '📢', text: 'Show announcements' },
      { icon: '👥', text: 'Show team summary' },
      { icon: '📋', text: 'Show team nominations' },
      { icon: '⏳', text: 'Show pending reviews' },
      { icon: '🔔', text: 'Remind team' },
      { icon: '✔️', text: 'Show pending approvals' },
      { icon: '📊', text: 'Show cycle results' },
      { icon: '⬇', text: 'Export nominations' },
    ],
    cannot: [
      { text: 'Approve nominations', goto: 'Nominations page' },
      { text: 'View employee report charts', goto: 'Reports page' },
      { text: 'Fill feedback form', goto: 'My Tasks page' },
    ],
  },
  HR_ADMIN: {
    can: [
      { icon: '📊', text: 'Show cycle status' },
      { icon: '📈', text: 'Show participation stats' },
      { icon: '📝', text: 'Show all templates' },
      { icon: '👤', text: 'Show all employees' },
      { icon: '📅', text: 'Show cycle deadlines' },
      { icon: '📢', text: 'Show announcements' },
      { icon: '➕', text: 'Create a cycle' },
      { icon: '➕', text: 'Create a template' },
      { icon: '▶️', text: 'Activate a cycle' },
      { icon: '🔒', text: 'Finalize a cycle' },
      { icon: '⏹️', text: 'Close a cycle' },
      { icon: '🚀', text: 'Release results' },
      { icon: '❌', text: 'Cancel a cycle' },
      { icon: '✔️', text: 'Show pending approvals' },
      { icon: '📊', text: 'Show cycle results' },
      { icon: '⬇', text: 'Export nominations' },
    ],
    cannot: [
      { text: 'Full cycle configuration', goto: 'Cycles page' },
      { text: 'Edit template sections', goto: 'Templates page' },
      { text: 'Manage announcements', goto: 'Announcements page' },
      { text: 'View detailed report charts', goto: 'Reports page' },
    ],
  },
  SUPER_ADMIN: {
    can: [
      { icon: '📊', text: 'Show cycle status' },
      { icon: '📈', text: 'Show participation stats' },
      { icon: '📝', text: 'Show all templates' },
      { icon: '👤', text: 'Show all employees' },
      { icon: '📅', text: 'Show cycle deadlines' },
      { icon: '📢', text: 'Show announcements' },
      { icon: '➕', text: 'Create a cycle' },
      { icon: '➕', text: 'Create a template' },
      { icon: '▶️', text: 'Activate a cycle' },
      { icon: '🔒', text: 'Finalize a cycle' },
      { icon: '⏹️', text: 'Close a cycle' },
      { icon: '🚀', text: 'Release results' },
      { icon: '❌', text: 'Cancel a cycle' },
      { icon: '🔍', text: 'Show audit logs' },
      { icon: '👥', text: 'Show team summary' },
      { icon: '📋', text: 'Show team nominations' },
      { icon: '✔️', text: 'Show pending approvals' },
      { icon: '📊', text: 'Show cycle results' },
      { icon: '⬇', text: 'Export nominations' },
      { icon: '🔔', text: 'Remind team' },
    ],
    cannot: [
      { text: 'Manage users', goto: 'Admin → Users page' },
      { text: 'View org chart', goto: 'Admin → Org page' },
      { text: 'Full cycle configuration', goto: 'Cycles page' },
      { text: 'Edit template sections', goto: 'Templates page' },
    ],
  },
};

/* ─── Info Panel (shown inside widget when "i" is clicked) ──────────────────── */
function InfoPanel({ role, onClose }) {
  const caps = CAPABILITIES[role] || CAPABILITIES.EMPLOYEE;
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: '#fafbfc', padding: '14px 12px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 }}>
        <div style={{ fontWeight: 700, fontSize: 13, color: '#1e293b' }}>What can I help with?</div>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 11, color: '#667eea', fontWeight: 600, padding: '2px 6px' }}>
          ← Back to chat
        </button>
      </div>

      {/* Can do */}
      <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 10, padding: '10px 12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 8 }}>
          <CheckCircleOutlined style={{ color: '#22c55e', fontSize: 12 }} />
          <span style={{ fontSize: 11, fontWeight: 700, color: '#15803d' }}>I CAN do these for you</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {caps.can.map((item, i) => (
            <div key={i} style={{
              fontSize: 11, color: '#166534',
              display: 'flex', alignItems: 'center', gap: 6,
              background: 'rgba(255,255,255,0.75)', borderRadius: 7,
              padding: '4px 8px', border: '1px solid rgba(134,239,172,0.6)',
            }}>
              <span>{item.icon}</span>
              <span style={{ fontWeight: 500 }}>{item.text}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Cannot do */}
      <div style={{ background: '#fff5f5', border: '1px solid #fecaca', borderRadius: 10, padding: '10px 12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 8 }}>
          <CloseCircleOutlined style={{ color: '#ef4444', fontSize: 12 }} />
          <span style={{ fontSize: 11, fontWeight: 700, color: '#dc2626' }}>Use the UI for these</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {caps.cannot.map((item, i) => (
            <div key={i} style={{
              fontSize: 11,
              display: 'flex', alignItems: 'center', gap: 6,
              background: 'rgba(255,255,255,0.75)', borderRadius: 7,
              padding: '4px 8px', border: '1px solid rgba(254,202,202,0.8)',
              color: '#7f1d1d',
            }}>
              <span>↗</span>
              <span><span style={{ fontWeight: 600 }}>{item.text}</span>
              <span style={{ color: '#b91c1c', fontWeight: 400 }}> → {item.goto}</span></span>
            </div>
          ))}
        </div>
      </div>

      <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 10, padding: '8px 12px', fontSize: 10.5, color: '#1d4ed8', lineHeight: 1.6 }}>
        💡 <strong>Tip:</strong> Just type naturally! Try <em>"show my tasks"</em>, <em>"any deadlines?"</em>, or <em>"create a cycle"</em>
      </div>
    </div>
  );
}

/* ─── State badge colors ────────────────────────────────────────────────────── */
const STATE_COLORS = {
  ACTIVE:           { bg: '#f0fdf4', text: '#15803d', dot: '#22c55e' },
  NOMINATION:       { bg: '#eff6ff', text: '#1d4ed8', dot: '#3b82f6' },
  DRAFT:            { bg: '#f9fafb', text: '#374151', dot: '#9ca3af' },
  FINALIZED:        { bg: '#fdf4ff', text: '#7e22ce', dot: '#a855f7' },
  CLOSED:           { bg: '#fef3c7', text: '#92400e', dot: '#f59e0b' },
  RESULTS_RELEASED: { bg: '#ecfeff', text: '#0e7490', dot: '#06b6d4' },
  ARCHIVED:         { bg: '#f1f5f9', text: '#475569', dot: '#94a3b8' },
};

function StateBadge({ state }) {
  const c = STATE_COLORS[state] || STATE_COLORS.DRAFT;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      background: c.bg, color: c.text, borderRadius: 20,
      padding: '1px 8px', fontSize: 10, fontWeight: 600,
    }}>
      <span style={{ width: 5, height: 5, borderRadius: '50%', background: c.dot, display: 'inline-block' }} />
      {state?.replace(/_/g, ' ')}
    </span>
  );
}

/* ─── Smart timestamp helpers ───────────────────────────────────────────────── */
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
  return new Date(ts).toLocaleDateString([], { day: 'numeric', month: 'short' });
}

/* ─── Date separator ────────────────────────────────────────────────────────── */
function DateSeparator({ label }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '4px 0' }}>
      <div style={{ flex: 1, height: 1, background: '#f1f5f9' }} />
      <span style={{
        fontSize: 9.5, color: '#94a3b8', fontWeight: 600,
        letterSpacing: '0.05em', whiteSpace: 'nowrap',
        background: '#fafbfc', padding: '2px 8px',
        borderRadius: 20, border: '1px solid #f1f5f9',
      }}>
        {label}
      </span>
      <div style={{ flex: 1, height: 1, background: '#f1f5f9' }} />
    </div>
  );
}

/* ─── Typing dots ───────────────────────────────────────────────────────────── */
function TypingDots() {
  return (
    <div style={{ display: 'flex', gap: 3, alignItems: 'center', padding: '2px 0' }}>
      {[0, 1, 2].map((i) => (
        <div key={i} style={{
          width: 6, height: 6, borderRadius: '50%', background: '#94a3b8',
          animation: 'wbounce 1.2s infinite', animationDelay: `${i * 0.2}s`,
        }} />
      ))}
      <style>{`
        @keyframes wbounce {
          0%,80%,100%{transform:translateY(0);opacity:.4}
          40%{transform:translateY(-5px);opacity:1}
        }
        @keyframes widgetSlide {
          from{opacity:0;transform:translateY(20px) scale(0.95)}
          to{opacity:1;transform:translateY(0) scale(1)}
        }
        @keyframes pulse {
          0%,100%{box-shadow:0 0 0 0 rgba(102,126,234,0.4)}
          50%{box-shadow:0 0 0 8px rgba(102,126,234,0)}
        }
        @keyframes wblink {
          0%,100%{opacity:1} 50%{opacity:0}
        }
      `}</style>
    </div>
  );
}

/* ─── Mini data display ─────────────────────────────────────────────────────── */
function MiniData({ data, onPick, onDirectAction, onNavigate }) {
  if (!data) return null;

  const card = { background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.04)' };

  if (data.results?.length) {
    return (
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 5 }}>
        {data.results.map((r, i) => (
          <div key={i} style={{ ...card, overflow: 'hidden' }}>
            <div style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', padding: '5px 10px' }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: '#1e293b' }}>{r.cycle}</span>
            </div>
            <div style={{ padding: '6px 10px', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {r.overall_score != null && (
                <span style={{ fontSize: 10, fontWeight: 600, color: '#6366f1', background: '#eef2ff', borderRadius: 20, padding: '2px 8px' }}>
                  Overall {r.overall_score}
                </span>
              )}
              {r.peer_score != null && (
                <span style={{ fontSize: 10, fontWeight: 600, color: '#0891b2', background: '#ecfeff', borderRadius: 20, padding: '2px 8px' }}>
                  Peer {r.peer_score}
                </span>
              )}
              {r.self_score != null && (
                <span style={{ fontSize: 10, fontWeight: 600, color: '#059669', background: '#ecfdf5', borderRadius: 20, padding: '2px 8px' }}>
                  Self {r.self_score}
                </span>
              )}
              {r.manager_score != null && (
                <span style={{ fontSize: 10, fontWeight: 600, color: '#d97706', background: '#fffbeb', borderRadius: 20, padding: '2px 8px' }}>
                  Manager {r.manager_score}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (data.cycles?.length) {
    return (
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 5 }}>
        {data.cycles.slice(0, 3).map((c, i) => (
          <div key={i} style={{ ...card, padding: '6px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: '#1e293b', flex: 1 }}>{c.name}</span>
            <StateBadge state={c.state} />
          </div>
        ))}
        {data.cycles.length > 3 && (
          <div style={{ fontSize: 10, color: '#94a3b8', textAlign: 'center' }}>+{data.cycles.length - 3} more</div>
        )}
      </div>
    );
  }

  if (data.deadlines?.length) {
    return (
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 5 }}>
        {data.deadlines.slice(0, 3).map((d, i) => (
          <div key={i} style={{ ...card, padding: '6px 10px' }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: '#1e293b' }}>{d.cycle}</div>
            <div style={{ fontSize: 10, color: '#f59e0b', marginTop: 2, fontWeight: 500 }}>⏰ {d.deadline}</div>
          </div>
        ))}
      </div>
    );
  }

  if (data.grouped_tasks?.length) {
    const STATUS_COLOR = { SUBMITTED: '#22c55e', IN_PROGRESS: '#3b82f6', PENDING: '#f59e0b', CREATED: '#94a3b8' };
    return (
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {data.grouped_tasks.map((g, gi) => (
          <div key={gi} style={{ ...card, overflow: 'hidden' }}>
            <div style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', padding: '5px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: '#1e293b' }}>{g.cycle}</span>
              <StateBadge state={g.state} />
            </div>
            {g.tasks.slice(0, 4).map((t, ti) => (
              <div key={ti} style={{ padding: '5px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: ti < g.tasks.length - 1 ? '1px solid #f1f5f9' : 'none' }}>
                <span style={{ fontSize: 11, color: '#334155' }}>{t.reviewee}</span>
                <span style={{ fontSize: 10, fontWeight: 600, color: STATUS_COLOR[t.status] || '#64748b', background: `${STATUS_COLOR[t.status] || '#64748b'}15`, borderRadius: 20, padding: '1px 7px' }}>{t.status}</span>
              </div>
            ))}
            {g.tasks.length > 4 && <div style={{ fontSize: 10, color: '#94a3b8', textAlign: 'center', padding: '3px 0' }}>+{g.tasks.length - 4} more</div>}
          </div>
        ))}
      </div>
    );
  }

  if (data.tasks?.length) {
    const STATUS_COLOR = { SUBMITTED: '#22c55e', IN_PROGRESS: '#3b82f6', PENDING: '#f59e0b', CREATED: '#94a3b8' };
    // Group flat tasks by cycle name for consistent display
    const grouped = {};
    data.tasks.forEach(t => {
      const key = t.cycle || 'Unknown Cycle';
      if (!grouped[key]) grouped[key] = { cycle: key, tasks: [] };
      grouped[key].tasks.push(t);
    });
    const groupedList = Object.values(grouped);
    return (
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {groupedList.map((g, gi) => (
          <div key={gi} style={{ ...card, overflow: 'hidden' }}>
            <div style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', padding: '5px 10px' }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: '#1e293b' }}>{g.cycle}</span>
            </div>
            {g.tasks.slice(0, 4).map((t, ti) => (
              <div key={ti} style={{ padding: '5px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: ti < g.tasks.length - 1 ? '1px solid #f1f5f9' : 'none' }}>
                <span style={{ fontSize: 11, color: '#334155' }}>{t.reviewee || t.name}</span>
                <span style={{ fontSize: 10, fontWeight: 600, color: STATUS_COLOR[t.status] || '#64748b', background: `${STATUS_COLOR[t.status] || '#64748b'}15`, borderRadius: 20, padding: '1px 7px' }}>{t.status}</span>
              </div>
            ))}
            {g.tasks.length > 4 && <div style={{ fontSize: 10, color: '#94a3b8', textAlign: 'center', padding: '3px 0' }}>+{g.tasks.length - 4} more</div>}
          </div>
        ))}
      </div>
    );
  }

  if (data.team?.length) {
    return (
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 5 }}>
        {data.team.map((m, i) => {
          const pct = m.total_tasks > 0 ? Math.round((m.submitted / m.total_tasks) * 100) : 0;
          return (
            <div key={i} style={{ ...card, padding: '6px 10px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: '#1e293b' }}>{m.name}</span>
                <span style={{ fontSize: 10, color: '#64748b' }}>{m.submitted}/{m.total_tasks}</span>
              </div>
              <div style={{ background: '#f1f5f9', borderRadius: 4, height: 4 }}>
                <div style={{ background: '#22c55e', borderRadius: 4, height: 4, width: `${pct}%`, transition: 'width 0.5s ease' }} />
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  if (data.participation?.length) {
    return (
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {data.participation.slice(0, 3).map((p, i) => (
          <div key={i} style={{ ...card, padding: '6px 10px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: '#1e293b' }}>{p.cycle}</span>
              <span style={{ fontSize: 10, color: '#64748b' }}>{p.completion_pct}%</span>
            </div>
            <div style={{ background: '#f1f5f9', borderRadius: 4, height: 4 }}>
              <div style={{ background: '#3b82f6', borderRadius: 4, height: 4, width: `${p.completion_pct}%`, transition: 'width 0.5s ease' }} />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (data.available_cycles?.length) {
    return (
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {data.available_cycles.map((c, i) => (
          <div
            key={`${c.id}-${i}`}
            onClick={() => onPick?.({ id: c.id, label: c.name })}
            style={{ ...card, padding: '6px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: onPick ? 'pointer' : 'default', transition: 'background 0.15s' }}
            onMouseEnter={(e) => { if (onPick) e.currentTarget.style.background = '#eef2ff'; }}
            onMouseLeave={(e) => { if (onPick) e.currentTarget.style.background = '#fff'; }}
          >
            <span style={{ fontSize: 11, color: '#64748b', marginRight: 6 }}>{i + 1}.</span>
            <span style={{ fontSize: 11, fontWeight: 600, color: '#1e293b', flex: 1 }}>{c.name}</span>
            <StateBadge state={c.state} />
          </div>
        ))}
      </div>
    );
  }

  if (data.available_nominations?.length) {
    return (
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {data.available_nominations.map((n, i) => (
          <div
            key={`${n.nomination_id}-${i}`}
            onClick={() => onPick?.({ id: n.nomination_id, label: `${n.peer} reviewing ${n.reviewee}` })}
            style={{ ...card, padding: '6px 10px', cursor: onPick ? 'pointer' : 'default', transition: 'background 0.15s' }}
            onMouseEnter={(e) => { if (onPick) e.currentTarget.style.background = '#eef2ff'; }}
            onMouseLeave={(e) => { if (onPick) e.currentTarget.style.background = '#fff'; }}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6 }}>
              <span style={{ fontSize: 11, color: '#64748b', marginTop: 1 }}>{i + 1}.</span>
              <div>
                <div style={{ fontSize: 11, fontWeight: 600, color: '#1e293b' }}>{n.peer}</div>
                <div style={{ fontSize: 10, color: '#64748b' }}>reviewing {n.reviewee} · {n.cycle}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (data.grouped_nominations?.length) {
    const NOM_COLORS = { PENDING: '#f59e0b', APPROVED: '#22c55e', REJECTED: '#ef4444' };
    return (
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {data.grouped_nominations.map((g, gi) => (
          <div key={gi} style={{ ...card, overflow: 'hidden' }}>
            <div style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', padding: '5px 10px' }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: '#1e293b' }}>{g.cycle}</span>
            </div>
            {g.nominations.slice(0, 4).map((n, ni) => (
              <div key={ni} style={{ padding: '5px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: ni < g.nominations.length - 1 ? '1px solid #f1f5f9' : 'none' }}>
                <span style={{ fontSize: 11, color: '#334155' }}>{n.peer}</span>
                <span style={{ fontSize: 10, fontWeight: 600, background: `${NOM_COLORS[n.status] || '#94a3b8'}15`, color: NOM_COLORS[n.status] || '#94a3b8', borderRadius: 20, padding: '1px 7px' }}>{n.status}</span>
              </div>
            ))}
            {g.nominations.length > 4 && <div style={{ fontSize: 10, color: '#94a3b8', textAlign: 'center', padding: '3px 0' }}>+{g.nominations.length - 4} more</div>}
          </div>
        ))}
      </div>
    );
  }

  if (data.nominations?.length) {
    const NOM_COLORS = { PENDING: '#f59e0b', APPROVED: '#22c55e', REJECTED: '#ef4444' };
    // Group flat nominations by cycle for consistent display
    const grouped = {};
    data.nominations.forEach(n => {
      const key = n.cycle || 'Unknown Cycle';
      if (!grouped[key]) grouped[key] = { cycle: key, nominations: [] };
      grouped[key].nominations.push(n);
    });
    const groupedList = Object.values(grouped);
    return (
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {groupedList.map((g, gi) => (
          <div key={gi} style={{ ...card, overflow: 'hidden' }}>
            <div style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', padding: '5px 10px' }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: '#1e293b' }}>{g.cycle}</span>
            </div>
            {g.nominations.slice(0, 4).map((n, ni) => (
              <div key={ni} style={{ padding: '5px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: ni < g.nominations.length - 1 ? '1px solid #f1f5f9' : 'none' }}>
                <span style={{ fontSize: 11, color: '#334155' }}>{n.peer}</span>
                <span style={{ fontSize: 10, fontWeight: 600, background: `${NOM_COLORS[n.status] || '#94a3b8'}15`, color: NOM_COLORS[n.status] || '#94a3b8', borderRadius: 20, padding: '1px 7px' }}>{n.status}</span>
              </div>
            ))}
            {g.nominations.length > 4 && <div style={{ fontSize: 10, color: '#94a3b8', textAlign: 'center', padding: '3px 0' }}>+{g.nominations.length - 4} more</div>}
          </div>
        ))}
      </div>
    );
  }

  if (data.grouped_team_nominations?.length) {
    const NOM_COLORS = { PENDING: '#f59e0b', APPROVED: '#22c55e', REJECTED: '#ef4444' };
    return (
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {data.grouped_team_nominations.map((g, gi) => (
          <div key={gi} style={{ ...card, overflow: 'hidden' }}>
            <div style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', padding: '5px 10px' }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: '#1e293b' }}>{g.reviewee}</span>
            </div>
            {g.nominations.slice(0, 4).map((n, ni) => (
              <div key={ni} style={{ padding: '5px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: ni < g.nominations.length - 1 ? '1px solid #f1f5f9' : 'none' }}>
                <div>
                  <div style={{ fontSize: 11, color: '#334155' }}>{n.peer}</div>
                  <div style={{ fontSize: 10, color: '#94a3b8' }}>{n.cycle}</div>
                </div>
                {n.status === 'PENDING' && onDirectAction ? (
                  <div style={{ display: 'flex', gap: 3 }}>
                    <button onClick={() => onDirectAction('approve_nomination', n.nomination_id)} style={{ fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 5, border: 'none', background: '#22c55e20', color: '#16a34a', cursor: 'pointer' }}>✓</button>
                    <button onClick={() => onDirectAction('reject_nomination', n.nomination_id)} style={{ fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 5, border: 'none', background: '#ef444420', color: '#dc2626', cursor: 'pointer' }}>✗</button>
                  </div>
                ) : (
                  <span style={{ fontSize: 10, fontWeight: 600, background: `${NOM_COLORS[n.status] || '#94a3b8'}15`, color: NOM_COLORS[n.status] || '#94a3b8', borderRadius: 20, padding: '1px 7px' }}>{n.status}</span>
                )}
              </div>
            ))}
            {g.nominations.length > 4 && <div style={{ fontSize: 10, color: '#94a3b8', textAlign: 'center', padding: '3px 0' }}>+{g.nominations.length - 4} more</div>}
          </div>
        ))}
      </div>
    );
  }

  if (data.team_nominations?.length) {
    const NOM_COLORS = { PENDING: '#f59e0b', APPROVED: '#22c55e', REJECTED: '#ef4444' };
    return (
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {data.team_nominations.slice(0, 3).map((n, i) => (
          <div key={i} style={{ ...card, padding: '6px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#1e293b' }}>{n.reviewee}</div>
              <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 1 }}>← {n.peer}</div>
            </div>
            <span style={{ fontSize: 10, fontWeight: 600, background: `${NOM_COLORS[n.status]}20`, color: NOM_COLORS[n.status], borderRadius: 20, padding: '1px 7px' }}>{n.status}</span>
          </div>
        ))}
      </div>
    );
  }

  if (data.templates?.length) {
    return (
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {data.templates.slice(0, 3).map((t, i) => (
          <div key={i} style={{ ...card, padding: '6px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: '#1e293b' }}>{t.name}</span>
            <span style={{ fontSize: 10, background: '#eff6ff', color: '#1d4ed8', borderRadius: 20, padding: '1px 7px', fontWeight: 600 }}>{t.cycle_count} cycles</span>
          </div>
        ))}
      </div>
    );
  }

  if (data.employees?.length) {
    return (
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {data.employees.slice(0, 3).map((e, i) => (
          <div key={i} style={{ ...card, padding: '6px 10px' }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: '#1e293b' }}>{e.name}</div>
            <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 1 }}>{e.role?.replace('_', ' ')} · {e.department}</div>
          </div>
        ))}
        {data.employees.length > 3 && (
          <div style={{ fontSize: 10, color: '#94a3b8', textAlign: 'center' }}>+{data.employees.length - 3} more</div>
        )}
      </div>
    );
  }

  if (data.announcements?.length) {
    return (
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {data.announcements.slice(0, 2).map((a, i) => (
          <div key={i} style={{
            background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 8,
            padding: '6px 10px', fontSize: 11, color: '#1d4ed8', lineHeight: 1.5,
          }}>
            {a.message.length > 80 ? `${a.message.slice(0, 80)}…` : a.message}
          </div>
        ))}
      </div>
    );
  }

  if (data.audit_logs?.length) {
    return (
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {data.audit_logs.slice(0, 3).map((l, i) => (
          <div key={i} style={{ ...card, padding: '5px 10px' }}>
            <div style={{ fontSize: 10, color: '#374151' }}>
              <span style={{ fontWeight: 600 }}>{l.actor}</span>
              {' · '}<span style={{ color: '#7c3aed' }}>{l.action}</span>
            </div>
            <div style={{ fontSize: 9, color: '#94a3b8', marginTop: 1 }}>{l.at}</div>
          </div>
        ))}
      </div>
    );
  }

  // Pending approvals
  if (data.pending_approvals?.length) {
    return (
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {data.pending_approvals.slice(0, 5).map((a, i) => (
          <div key={i} style={{ ...card, padding: '6px 10px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: 11, fontWeight: 600, color: '#1e293b' }}>{a.reviewee} → {a.peer}</div>
                <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 1 }}>{a.cycle}</div>
              </div>
              <span style={{ fontSize: 9, fontWeight: 600, background: '#fef9c3', color: '#92400e', borderRadius: 20, padding: '1px 7px' }}>PENDING</span>
            </div>
          </div>
        ))}
        {data.pending_approvals.length > 5 && (
          <div style={{ fontSize: 10, color: '#94a3b8', textAlign: 'center' }}>+{data.pending_approvals.length - 5} more</div>
        )}
      </div>
    );
  }

  // Cycle results
  if (data.cycle_results?.length) {
    return (
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {data.cycle_results.slice(0, 6).map((r, i) => (
          <div key={i} style={{ ...card, padding: '6px 10px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#1e293b', flex: 1 }}>{r.name}</div>
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                {r.overall_score != null && <span style={{ fontSize: 9, fontWeight: 700, background: '#f0fdf4', color: '#15803d', border: '1px solid #86efac', borderRadius: 20, padding: '1px 6px' }}>⭐ {r.overall_score}</span>}
                {r.peer_score != null && <span style={{ fontSize: 9, background: '#eff6ff', color: '#1d4ed8', borderRadius: 20, padding: '1px 6px' }}>Peer {r.peer_score}</span>}
                {r.self_score != null && <span style={{ fontSize: 9, background: '#fdf4ff', color: '#7e22ce', borderRadius: 20, padding: '1px 6px' }}>Self {r.self_score}</span>}
              </div>
            </div>
          </div>
        ))}
        {data.cycle_results.length > 6 && (
          <div style={{ fontSize: 10, color: '#94a3b8', textAlign: 'center' }}>+{data.cycle_results.length - 6} more</div>
        )}
      </div>
    );
  }

  // Export nominations
  if (data.export_nominations?.length) {
    const NOM_COLORS = { PENDING: '#f59e0b', APPROVED: '#22c55e', REJECTED: '#ef4444' };
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
      <div style={{ marginTop: 8 }}>
        <button onClick={downloadCsv} style={{
          marginBottom: 8, background: '#4f46e5', color: '#fff', border: 'none',
          borderRadius: 7, padding: '5px 12px', cursor: 'pointer', fontSize: 11, fontWeight: 600,
        }}>⬇ Download CSV ({data.export_nominations.length} rows)</button>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          {data.export_nominations.slice(0, 4).map((n, i) => (
            <div key={i} style={{ ...card, padding: '5px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: 11, fontWeight: 600, color: '#1e293b' }}>{n.reviewee} → {n.peer}</div>
                <div style={{ fontSize: 9, color: '#94a3b8' }}>{n.nominated_on}</div>
              </div>
              <span style={{ fontSize: 9, fontWeight: 600, background: `${NOM_COLORS[n.status] || '#94a3b8'}20`, color: NOM_COLORS[n.status] || '#94a3b8', borderRadius: 20, padding: '1px 6px' }}>{n.status}</span>
            </div>
          ))}
          {data.export_nominations.length > 4 && (
            <div style={{ fontSize: 10, color: '#94a3b8', textAlign: 'center' }}>+{data.export_nominations.length - 4} more (in CSV)</div>
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
      <div style={{ marginTop: 8, background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, padding: '10px 12px' }}>
        <div style={{ fontWeight: 700, fontSize: 13, color: '#1e293b', marginBottom: 8 }}>{p.name}</div>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <tbody>
            {profileRows.map(r => (
              <tr key={r.label} style={{ borderBottom: '1px solid #f1f5f9' }}>
                <td style={{ fontSize: 10, fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', padding: '3px 8px 3px 0', whiteSpace: 'nowrap', width: '35%' }}>{r.label}</td>
                <td style={{ fontSize: 11, color: '#334155', padding: '3px 0' }}>{r.value}</td>
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
      <div style={{ marginTop: 8, background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, padding: '10px 12px' }}>
        <div style={{ fontSize: 10, fontWeight: 600, color: '#64748b', textTransform: 'uppercase', marginBottom: 4 }}>Your Manager</div>
        <div style={{ fontWeight: 700, fontSize: 13, color: '#1e293b', marginBottom: 4 }}>{m.name}</div>
        <div style={{ fontSize: 11, color: '#64748b' }}>📧 {m.email}</div>
        {m.job_title && m.job_title !== 'N/A' && <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>💼 {m.job_title}</div>}
        <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>🏢 {m.department}</div>
      </div>
    );
  }

  // Direct reports (show my team)
  if (data.direct_reports?.length) {
    return (
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 5 }}>
        {data.direct_reports.map((m, i) => (
          <div key={i} style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, padding: '8px 10px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontWeight: 600, fontSize: 12, color: '#1e293b' }}>{m.name}</div>
                <div style={{ fontSize: 10, color: '#64748b', marginTop: 1 }}>{m.email}</div>
              </div>
              <div style={{ fontSize: 10, color: '#6366f1', fontWeight: 600 }}>{m.role}</div>
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
      <div style={{ marginTop: 8, background: '#fff', border: '1px solid #fbbf24', borderRadius: 8, padding: '10px 12px' }}>
        <div style={{ fontSize: 10, fontWeight: 600, color: '#92400e', textTransform: 'uppercase', marginBottom: 4 }}>Next Review</div>
        <div style={{ fontWeight: 600, fontSize: 12, color: '#1e293b', marginBottom: 3 }}>{nd.cycle_name}</div>
        <div style={{ fontSize: 11, color: '#d97706', fontWeight: 600 }}>📅 {nd.deadline_date}</div>
      </div>
    );
  }

  // Who has not submitted
  if (data.pending?.length) {
    return (
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 5 }}>
        {data.pending.map((p, i) => (
          <div key={i} style={{ background: '#fff', border: '1px solid #fecaca', borderRadius: 8, padding: '8px 10px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontWeight: 600, fontSize: 12, color: '#1e293b' }}>{p.reviewer}</div>
                <div style={{ fontSize: 10, color: '#64748b', marginTop: 1 }}>reviewing {p.reviewee}</div>
              </div>
              <span style={{ fontSize: 9, fontWeight: 600, background: '#fef2f2', color: '#dc2626', border: '1px solid #fecaca', borderRadius: 20, padding: '1px 6px' }}>{p.task_status}</span>
            </div>
            <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 3 }}>{p.cycle}</div>
          </div>
        ))}
      </div>
    );
  }

  // Help commands list
  if (data.commands?.length) {
    return (
      <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 5 }}>
        {data.commands.map((cmd, i) => (
          <button
            key={i}
            onClick={() => onSuggest?.(cmd)}
            style={{
              fontSize: 11, fontWeight: 500, padding: '4px 10px', borderRadius: 20,
              border: '1px solid #e2e8f0', background: '#f8fafc', color: '#334155',
              cursor: 'pointer',
            }}
          >
            {cmd}
          </button>
        ))}
      </div>
    );
  }

  return null;
}

function ReportLink({ url, onNavigate }) {
  if (!url || !onNavigate) return null;
  return (
    <button
      onClick={() => onNavigate(url)}
      style={{
        marginTop: 8, display: 'flex', alignItems: 'center', gap: 5,
        fontSize: 11, fontWeight: 600, color: '#667eea',
        background: '#eef2ff', border: '1px solid #c7d2fe',
        borderRadius: 8, padding: '5px 12px', cursor: 'pointer',
        transition: 'all 0.15s', width: 'fit-content',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.background = '#667eea'; e.currentTarget.style.color = '#fff'; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = '#eef2ff'; e.currentTarget.style.color = '#667eea'; }}
    >
      ↗ View Full Report
    </button>
  );
}

/* ─── Widget bubble ─────────────────────────────────────────────────────────── */
function WidgetBubble({ msg, onSuggest, onDirectAction, onNavigate, role }) {
  const isUser = msg.role === 'user';
  const isError = msg.status === 'failed' || msg.status === 'rejected';
  const isClarify = !isUser && msg.status === 'clarify';
  const isNeedsInput = !isUser && msg.status === 'needs_input';
  const isStreaming = !isUser && msg.status === 'streaming';
  const clarifyChips = isClarify ? (QUICK_BY_ROLE[role] || QUICK_DEFAULT) : [];
  const [hovered, setHovered] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(msg.text || '');
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div
      style={{
        display: 'flex', gap: 7, alignItems: 'flex-start',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        animation: 'widgetSlide 0.2s ease',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {!isUser && (
        <Avatar size={24} style={{
          background: 'linear-gradient(135deg,#667eea,#764ba2)',
          flexShrink: 0, marginTop: 2,
        }}>
          <RobotOutlined style={{ fontSize: 11 }} />
        </Avatar>
      )}
      <div style={{ maxWidth: '82%' }}>
        <div style={{
          padding: '8px 12px',
          borderRadius: isUser ? '14px 14px 3px 14px' : '3px 14px 14px 14px',
          background: isUser
            ? 'linear-gradient(135deg,#667eea,#764ba2)'
            : isError ? '#fff5f5' : isNeedsInput ? '#fffbeb' : '#fff',
          color: isUser ? '#fff' : isError ? '#c53030' : '#1e293b',
          fontSize: 12.5, lineHeight: 1.6,
          border: isUser ? 'none' : `1px solid ${isError ? '#fed7d7' : isNeedsInput ? '#fcd34d' : '#e2e8f0'}`,
          boxShadow: isUser ? '0 2px 8px rgba(102,126,234,0.25)' : '0 1px 3px rgba(0,0,0,0.05)',
        }}>
          <span style={{ whiteSpace: 'pre-wrap' }}>
            {isClarify ? "Didn't catch that. Try one of these:" : msg.text}
            {isStreaming && (
              <span style={{
                display: 'inline-block', width: 2, height: '0.85em',
                background: '#667eea', animation: 'wblink 0.8s infinite',
                verticalAlign: 'text-bottom', marginLeft: 1, borderRadius: 1,
              }} />
            )}
          </span>
          {isClarify && (
            <div style={{ marginTop: 9, display: 'flex', flexWrap: 'wrap', gap: 5 }}>
              {clarifyChips.map((s) => (
                <button
                  key={s}
                  onClick={() => onSuggest?.(s)}
                  style={{
                    background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 20,
                    padding: '4px 10px', cursor: 'pointer', fontSize: 11,
                    color: '#374151', fontWeight: 500,
                    boxShadow: '0 1px 2px rgba(0,0,0,0.04)', transition: 'all 0.15s',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = '#667eea';
                    e.currentTarget.style.color = '#667eea';
                    e.currentTarget.style.background = '#eef2ff';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = '#e2e8f0';
                    e.currentTarget.style.color = '#374151';
                    e.currentTarget.style.background = '#f8fafc';
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          )}
            {!isClarify && <MiniData data={msg.data} onPick={onSuggest} onDirectAction={onDirectAction} onNavigate={onNavigate} />}
            {!isClarify && msg.data?.report_url && <ReportLink url={msg.data.report_url} onNavigate={onNavigate} />}
            {/* Action buttons for successful commands */}
            {!isClarify && msg.status === 'success' && msg.data?.template_id && (
              <button
                onClick={() => onNavigate?.('/hr/templates')}
                style={{
                  marginTop: 8, display: 'inline-flex', alignItems: 'center', gap: 5,
                  background: 'linear-gradient(135deg,#667eea,#764ba2)', color: '#fff',
                  border: 'none', borderRadius: 7, padding: '5px 11px',
                  fontSize: 11, fontWeight: 600, cursor: 'pointer',
                  boxShadow: '0 2px 6px rgba(102,126,234,0.3)', transition: 'opacity 0.15s',
                }}
                onMouseEnter={(e) => e.currentTarget.style.opacity = '0.85'}
                onMouseLeave={(e) => e.currentTarget.style.opacity = '1'}
              >
                📋 View Template →
              </button>
            )}
            {!isClarify && msg.status === 'success' && msg.data?.cycle_id && (
              <button
                onClick={() => onNavigate?.('/hr/cycles')}
                style={{
                  marginTop: 8, display: 'inline-flex', alignItems: 'center', gap: 5,
                  background: 'linear-gradient(135deg,#10b981,#059669)', color: '#fff',
                  border: 'none', borderRadius: 7, padding: '5px 11px',
                  fontSize: 11, fontWeight: 600, cursor: 'pointer',
                  boxShadow: '0 2px 6px rgba(16,185,129,0.3)', transition: 'opacity 0.15s',
                }}
                onMouseEnter={(e) => e.currentTarget.style.opacity = '0.85'}
                onMouseLeave={(e) => e.currentTarget.style.opacity = '1'}
              >
                🔄 View Cycle →
              </button>
            )}
            {isNeedsInput && (
              <div style={{ marginTop: 8, fontSize: 11, color: '#92400e', fontWeight: 500 }}>
                ✏️ Type your answer…
              </div>
            )}
          </div>
          {/* Suggestions chips */}
          {msg.suggestions?.length > 0 && (
            <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {msg.suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => onSuggest?.(s)}
                  style={{
                    fontSize: 10.5, fontWeight: 500, padding: '3px 9px', borderRadius: 20,
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
        <div style={{ fontSize: 9.5, color: '#cbd5e1', marginTop: 2, paddingInline: 2, textAlign: isUser ? 'right' : 'left' }}>
          {formatMsgTime(msg.ts)}
        </div>
        {!isUser && msg.text && (
          <div style={{ height: 20, marginTop: 2, paddingInline: 2 }}>
            {hovered && (
              <button
                onClick={handleCopy}
                title={copied ? 'Copied!' : 'Copy message'}
                style={{
                  background: 'none', border: '1px solid #e2e8f0', borderRadius: 4,
                  cursor: 'pointer', padding: '1px 5px', fontSize: 10,
                  color: copied ? '#22c55e' : '#94a3b8',
                  display: 'inline-flex', alignItems: 'center', gap: 3,
                  transition: 'all 0.15s',
                }}
              >
                {copied ? <CheckOutlined style={{ fontSize: 10 }} /> : <CopyOutlined style={{ fontSize: 10 }} />}
                {copied ? 'Copied' : 'Copy'}
              </button>
            )}
          </div>
        )}
      </div>
      {isUser && (
        <Avatar size={24} style={{ background: '#e2e8f0', flexShrink: 0, marginTop: 2 }}>
          <UserOutlined style={{ color: '#64748b', fontSize: 11 }} />
        </Avatar>
      )}
    </div>
  );
}

const QUICK_BY_ROLE = {
  EMPLOYEE:    ['Show my tasks',        'Catch me up on everything', 'Show my nominations'],
  MANAGER:     ['Show team summary',    'Show team nominations',     'Catch me up on everything'],
  HR_ADMIN:    ['Who are the top performers?', 'Show participation stats', 'Which department scores highest?'],
  SUPER_ADMIN: ['Give me an org overview',     'Who are the top performers?', 'Show audit logs'],
};
const QUICK_DEFAULT = ['Show my tasks', 'Show cycle status', 'Show announcements'];

/* ─── History Panel ─────────────────────────────────────────────────────────── */
function HistoryPanel({ sessions, loading, onSelectSession, onClose, onDeleteSession, onRenameSession }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [hoveredId, setHoveredId] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [editValue, setEditValue] = useState('');
  const [pinnedIds, setPinnedIds] = useState(() => {
    try { return JSON.parse(localStorage.getItem('chat_pinned_sessions') || '[]'); } catch { return []; }
  });

  const togglePin = (sessionId) => {
    setPinnedIds((prev) => {
      const next = prev.includes(sessionId) ? prev.filter(id => id !== sessionId) : [...prev, sessionId];
      localStorage.setItem('chat_pinned_sessions', JSON.stringify(next));
      return next;
    });
  };

  const startEdit = (s) => {
    setEditingId(s.session_id);
    setEditValue(s.title || s.first_message || '');
  };

  const commitEdit = (sessionId) => {
    const trimmed = editValue.trim();
    if (trimmed) onRenameSession(sessionId, trimmed);
    setEditingId(null);
  };

  function _relativeDate(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr);
    const diffDays = Math.floor((new Date() - d) / 86400000);
    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7)  return `${diffDays} days ago`;
    return d.toLocaleDateString([], { day: 'numeric', month: 'short' });
  }

  const filtered = sessions.filter(s =>
    (s.title || s.first_message || '').toLowerCase().includes(searchQuery.toLowerCase())
  );
  const sorted = [
    ...filtered.filter(s => pinnedIds.includes(s.session_id)),
    ...filtered.filter(s => !pinnedIds.includes(s.session_id)),
  ];

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: '#fafbfc', display: 'flex', flexDirection: 'column' }}>
      {/* Panel header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '12px 14px', borderBottom: '1px solid #e2e8f0',
        background: '#fff', flexShrink: 0,
      }}>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, borderRadius: 6, display: 'flex', alignItems: 'center', color: '#64748b' }}>
          <ArrowLeftOutlined style={{ fontSize: 14 }} />
        </button>
        <span style={{ fontWeight: 700, fontSize: 13, color: '#1e293b' }}>Conversation History</span>
      </div>

      {/* Search */}
      <div style={{ padding: '8px 10px', borderBottom: '1px solid #f1f5f9', background: '#fff', flexShrink: 0 }}>
        <input
          type="text"
          placeholder="Search conversations…"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
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
      <div style={{ flex: 1, overflowY: 'auto', padding: '10px 10px' }}>
        {loading && (
          <div style={{ textAlign: 'center', padding: '32px 0', color: '#94a3b8', fontSize: 12 }}>Loading…</div>
        )}
        {!loading && sorted.length === 0 && (
          <div style={{ textAlign: 'center', padding: '32px 0', color: '#94a3b8', fontSize: 12 }}>
            {searchQuery ? 'No matching conversations.' : 'No past conversations yet.'}
          </div>
        )}
        {!loading && sorted.map((s) => {
          const isPinned = pinnedIds.includes(s.session_id);
          const isHovered = hoveredId === s.session_id;
          const isEditing = editingId === s.session_id;
          return (
            <div
              key={s.session_id}
              style={{ position: 'relative', marginBottom: 6 }}
              onMouseEnter={() => setHoveredId(s.session_id)}
              onMouseLeave={() => setHoveredId(null)}
            >
              <div
                onClick={() => !isEditing && onSelectSession(s)}
                style={{
                  width: '100%', textAlign: 'left', background: '#fff',
                  border: `1px solid ${isHovered ? '#667eea' : '#e2e8f0'}`, borderRadius: 10,
                  padding: '8px 10px', cursor: 'pointer',
                  transition: 'all 0.15s',
                  background: isHovered ? '#f5f3ff' : '#fff',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 2 }}>
                  {isPinned && <span style={{ fontSize: 10 }}>📌</span>}
                  {isEditing ? (
                    <input
                      autoFocus
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      onBlur={() => commitEdit(s.session_id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') { e.preventDefault(); commitEdit(s.session_id); }
                        if (e.key === 'Escape') setEditingId(null);
                      }}
                      onClick={(e) => e.stopPropagation()}
                      style={{
                        flex: 1, fontSize: 12, fontWeight: 600, color: '#1e293b',
                        border: '1px solid #667eea', borderRadius: 4, padding: '1px 5px',
                        outline: 'none', background: '#fff',
                      }}
                    />
                  ) : (
                    <span style={{ fontWeight: 600, fontSize: 12, color: '#1e293b', flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {s.title || s.first_message || 'Conversation'}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 10, color: '#94a3b8' }}>{_relativeDate(s.last_at)}</div>
              </div>
              {/* Action icons on hover */}
              {isHovered && !isEditing && (
                <div style={{ position: 'absolute', top: 6, right: 7, display: 'flex', gap: 3 }}>
                  <button
                    title={isPinned ? 'Unpin' : 'Pin'}
                    onClick={(e) => { e.stopPropagation(); togglePin(s.session_id); }}
                    style={{ background: isPinned ? '#eef2ff' : '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 4, padding: '1px 4px', cursor: 'pointer', fontSize: 10, color: isPinned ? '#667eea' : '#94a3b8' }}
                  >
                    <PushpinOutlined style={{ fontSize: 10 }} />
                  </button>
                  <button
                    title="Rename"
                    onClick={(e) => { e.stopPropagation(); startEdit(s); }}
                    style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 4, padding: '1px 4px', cursor: 'pointer', fontSize: 10, color: '#94a3b8' }}
                  >
                    <EditOutlined style={{ fontSize: 10 }} />
                  </button>
                  <button
                    title="Delete"
                    onClick={(e) => { e.stopPropagation(); onDeleteSession(s.session_id); }}
                    style={{ background: '#fff5f5', border: '1px solid #fecaca', borderRadius: 4, padding: '1px 4px', cursor: 'pointer', fontSize: 10, color: '#ef4444' }}
                  >
                    <DeleteOutlined style={{ fontSize: 10 }} />
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── getSuggestions helper ─────────────────────────────────────────────────── */
function getSuggestions(data) {
  if (!data) return ['Show announcements', 'Show my tasks'];
  if (data.profile)    return ['Show my manager', 'Show my cycles', 'Show my tasks'];
  if (data.cycles)     return ['Show cycle deadlines', 'Show participation stats'];
  if (data.nominations) return ['Show my cycles', 'Show pending reviews'];
  if (data.tasks)      return ['Show my feedback', 'Show my report'];
  return ['Show announcements', 'Show my tasks'];
}

/* ─── Chat Widget ───────────────────────────────────────────────────────────── */
export default function ChatWidget({ open, onClose, onNewUnread }) {
  const user   = useAuthStore((s) => s.user);
  const quickSuggestions = QUICK_BY_ROLE[user?.role] || QUICK_DEFAULT;

  const [messages,          setMessages]          = useState([]);
  const [input,             setInput]             = useState('');
  const [loading,           setLoading]           = useState(false);
  const [streaming,         setStreaming]          = useState(false);
  const [sessionId,         setSessionId]         = useState(() => localStorage.getItem('chat_session_id') || '');
  const [awaitConfirm,      setAwaitConfirm]      = useState(false);
  const [pendingConfirmData, setPendingConfirmData] = useState(null);
  const [showInfo,          setShowInfo]          = useState(false);
  const [historyLoaded,     setHistoryLoaded]     = useState(false);
  const [recoveryBanner,    setRecoveryBanner]    = useState(null); // {intent_label, awaiting_confirm}
  const [showHistory,       setShowHistory]       = useState(false);
  const [sessions,          setSessions]          = useState([]);
  const [sessionsLoading,   setSessionsLoading]   = useState(false);
  const [confirmNewChat,    setConfirmNewChat]    = useState(false);
  const [isOnline,          setIsOnline]          = useState(navigator.onLine);
  const bottomRef  = useRef(null);
  const inputRef   = useRef(null);
  const navigate   = useNavigate();
  const retryCountRef  = useRef(0);
  const bcRef          = useRef(null);   // BroadcastChannel for cross-tab sync
  const fileInputRef   = useRef(null);   // Hidden file input for PDF upload

  // Cross-tab sync: listen for messages sent in ChatPage and reload if same session
  useEffect(() => {
    if (!window.BroadcastChannel) return;
    const bc = new BroadcastChannel('gamyam_chat_sync');
    bcRef.current = bc;
    bc.onmessage = (e) => {
      if (e.data?.type === 'new_message' && e.data.session_id === sessionId && !loading) {
        getChatHistory(e.data.session_id).then((res) => {
          setMessages(_logsToMessages(res.data.history || [], true));
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

  // PDF upload handler
  const handleFileUpload = useCallback(async (e) => {
    const file = e.target.files?.[0];
    if (!fileInputRef.current) return;
    fileInputRef.current.value = '';
    if (!file) return;
    const allowed = ['application/pdf', 'text/plain'];
    if (!allowed.includes(file.type) && !file.name.match(/\.(pdf|txt)$/i)) {
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
      const pdfMessage = `__PDF__:${filename}||${extracted_text}`;
      const displayMsg = `📎 Create template from: ${filename}`;
      await handleSend(pdfMessage, displayMsg);
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

  // Inject pulse keyframe once
  useEffect(() => {
    if (!document.getElementById('voice-pulse-kf')) {
      const s = document.createElement('style');
      s.id = 'voice-pulse-kf';
      s.textContent = '@keyframes voicePulse{0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,0.5)}50%{box-shadow:0 0 0 7px rgba(239,68,68,0)}}';
      document.head.appendChild(s);
    }
  }, []);

  // Load shared history when widget is opened for the first time
  useEffect(() => {
    if (open && !historyLoaded) {
      loadHistory();
      setHistoryLoaded(true);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (open) { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); inputRef.current?.focus(); }
  }, [messages, open, loading]);

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

  const _logsToMessages = (logs, reversed = false) => {
    const history = reversed ? [...logs].reverse() : logs;
    const pairs = [];
    history.forEach((log) => {
      if (log.message === '[user cancelled]' || log.message === '[confirmed]') return;
      pairs.push({ role: 'user', text: log.message, ts: log.created_at });
      if (log.response_message) {
        pairs.push({
          role: 'assistant',
          text: log.response_message,
          status: log.execution_status,
          data: log.response_data || {},
          ts: log.created_at,
        });
      }
    });
    return pairs;
  };

  const loadHistory = async () => {
    try {
      const [histRes, sessRes] = await Promise.all([getChatHistory(), getSessionState()]);
      setMessages(_logsToMessages(histRes.data.history || [], true));
      if (sessRes.data.has_active_session) {
        setRecoveryBanner({
          intent_label:     sessRes.data.intent_label,
          awaiting_confirm: sessRes.data.awaiting_confirm,
        });
      }
    } catch { /* silent */ }
  };

  const openHistoryPanel = async () => {
    setShowHistory(true);
    setSessionsLoading(true);
    try {
      const res = await getChatSessions();
      setSessions(res.data.sessions || []);
    } catch { setSessions([]); }
    finally { setSessionsLoading(false); }
  };

  const handleDeleteSession = async (sessionId) => {
    try {
      await deleteSession(sessionId);
      setSessions((prev) => prev.filter(s => s.session_id !== sessionId));
    } catch { /* silent */ }
  };

  const handleRenameSession = async (sid, title) => {
    try {
      await renameSession(sid, title);
      setSessions((prev) => prev.map(s => s.session_id === sid ? { ...s, title } : s));
    } catch { /* silent */ }
  };

  const handleSelectSession = async (session) => {
    setShowHistory(false);
    setShowInfo(false);
    try {
      const res = await getChatHistory(session.session_id);
      const msgs = _logsToMessages(res.data.history || [], false);
      setMessages(msgs);
      setSessionId(session.session_id);
      localStorage.setItem('chat_session_id', session.session_id);
      setRecoveryBanner(null);
    } catch { /* silent */ }
  };

  const doNewChat = async () => {
    setConfirmNewChat(false);
    setMessages([]);
    setSessionId('');
    localStorage.removeItem('chat_session_id');
    setRecoveryBanner(null);
    setShowHistory(false);
    setAwaitConfirm(false);
    setPendingConfirmData(null);
    try { await discardSession(); } catch { /* silent */ }
  };

  const handleNewChat = () => {
    if (messages.length > 0) {
      setConfirmNewChat(true);
    } else {
      doNewChat();
    }
  };

  const addMessage = (role, text, extra = {}) => {
    setMessages((prev) => [...prev, { role, text, ...extra, ts: new Date().toISOString() }]);
    if (!open && role === 'assistant') onNewUnread?.();
  };

  const handleSend = async (text, displayOverride) => {
    // text can be a string (typed/suggested) or {id, label} (picker click)
    const isPick = text && typeof text === 'object' && text.id;
    const msg    = isPick ? text.id : (text || input).trim();
    const label  = displayOverride || (isPick ? text.label : msg);
    if (!msg || loading) return;
    setInput('');
    setRecoveryBanner(null); // hide banner once user engages
    if (!displayOverride) addMessage('user', label);
    setLoading(true);
    setStreaming(false);
    retryCountRef.current = 0;

    const attemptSend = async () => {
      try {
        await sendMessageStream(
          msg,
          sessionId,
          isPick ? label : null,
          // onChunk — first chunk: add placeholder bubble and start streaming
          (chunk) => {
            setStreaming((wasStreaming) => {
              if (!wasStreaming) {
                setMessages((prev) => [
                  ...prev,
                  { role: 'assistant', text: chunk, status: 'streaming', data: {}, ts: new Date().toISOString() },
                ]);
              } else {
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last?.role === 'assistant') {
                    updated[updated.length - 1] = { ...last, text: last.text + chunk };
                  }
                  return updated;
                });
              }
              return true;
            });
          },
          // onDone — finalise the streaming bubble with the complete payload
          (data) => {
            if (data.session_id && data.session_id !== sessionId) {
              setSessionId(data.session_id);
              localStorage.setItem('chat_session_id', data.session_id);
            }
            // Notify other tabs (ChatPage) that a new message arrived
            bcRef.current?.postMessage({ type: 'new_message', session_id: data.session_id || sessionId });
            const isConfirmPending = data.status === 'awaiting_confirmation';
            setAwaitConfirm(isConfirmPending);
            if (isConfirmPending) setPendingConfirmData(data.data || null);
            else setPendingConfirmData(null);

            setStreaming((wasStreaming) => {
              if (wasStreaming) {
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last?.role === 'assistant') {
                    updated[updated.length - 1] = {
                      ...last,
                      text:        data.message || last.text,
                      status:      data.status,
                      data:        data.data || {},
                      ts:          new Date().toISOString(),
                      suggestions: data.status === 'success' ? getSuggestions(data.data) : undefined,
                    };
                  }
                  return updated;
                });
              } else {
                addMessage('assistant', data.message, {
                  status:      data.status,
                  data:        data.data || {},
                  suggestions: data.status === 'success' ? getSuggestions(data.data) : undefined,
                });
              }
              return false;
            });
          },
        );
      } catch (err) {
        // 429 rate limit
        if (err.status === 429) {
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            const errMsg = "You've reached the message limit. Please wait a moment before sending again.";
            if (last?.role === 'assistant' && last.status === 'streaming') {
              updated[updated.length - 1] = { ...last, text: errMsg, status: 'failed' };
              return updated;
            }
            return [...prev, { role: 'assistant', text: errMsg, status: 'failed', data: {}, ts: new Date().toISOString() }];
          });
          return;
        }
        // Network error (no .status) → retry up to 2 times
        if (!err.status && retryCountRef.current < 2) {
          retryCountRef.current += 1;
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            const retryMsg = `Connection lost, retrying… (${retryCountRef.current}/2)`;
            if (last?.role === 'assistant') {
              updated[updated.length - 1] = { ...last, text: retryMsg, status: 'streaming' };
            }
            return updated;
          });
          await new Promise((r) => setTimeout(r, 2000));
          return attemptSend();
        }
        // Final failure
        const finalMsg = !err.status ? 'Connection lost. Please try again.' : 'Something went wrong.';
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last?.role === 'assistant' && last.status === 'streaming') {
            updated[updated.length - 1] = { ...last, text: finalMsg, status: 'failed' };
            return updated;
          }
          return [...prev, { role: 'assistant', text: finalMsg, status: 'failed', data: {}, ts: new Date().toISOString() }];
        });
      } finally {
        setLoading(false);
        setStreaming(false);
      }
    };

    await attemptSend();
  };

  const handleDirectAction = async (action, nominationId) => {
    if (loading) return;
    const label = action === 'approve_nomination' ? 'Approve nomination' : 'Reject nomination';
    const intentMsg = action === 'approve_nomination' ? 'approve nomination' : 'reject nomination';
    addMessage('user', label);
    setLoading(true);
    try {
      const res1 = await sendMessage(intentMsg, sessionId);
      const d1 = res1.data;
      let sid = sessionId;
      if (d1.session_id && d1.session_id !== sid) {
        sid = d1.session_id;
        setSessionId(sid);
        localStorage.setItem('chat_session_id', sid);
      }
      if (d1.missing_field === 'nomination_id') {
        const res2 = await sendMessage(nominationId, sid);
        const d2 = res2.data;
        if (d2.session_id && d2.session_id !== sid) {
          setSessionId(d2.session_id);
          localStorage.setItem('chat_session_id', d2.session_id);
        }
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

  const handleDiscardSession = async () => {
    setRecoveryBanner(null);
    setSessionId('');
    localStorage.removeItem('chat_session_id');
    try { await discardSession(); } catch { /* silent */ }
  };

  const handleConfirm = async (confirmed) => {
    setAwaitConfirm(false);
    setPendingConfirmData(null);
    setLoading(true);
    try {
      const res  = await confirmAction(sessionId, confirmed);
      const data = res.data;
      addMessage('assistant', data.message, { status: data.status, data: data.data || {} });
      // Clear session after confirm or cancel — the confirmed action is complete
      setSessionId('');
      localStorage.removeItem('chat_session_id');
    } catch {
      addMessage('assistant', 'Confirmation failed.', { status: 'failed' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <style>{`
        @keyframes drawerSlideIn {
          from { transform: translateX(100%); }
          to   { transform: translateX(0); }
        }
      `}</style>

      {/* Drawer panel */}
      {open && (
        <div style={{
          position: 'fixed', top: 64, right: 0, bottom: 0, zIndex: 1050,
          width: 554, background: '#fff',
          boxShadow: '-6px 0 32px rgba(0,0,0,0.14)',
          borderRadius: '16px 0 0 16px',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
          animation: 'drawerSlideIn 0.25s cubic-bezier(0.4,0,0.2,1)',
        }}>

          {/* Header */}
          <div style={{
            background: 'linear-gradient(135deg,#667eea 0%,#764ba2 100%)',
            padding: '16px 18px',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            flexShrink: 0,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <Avatar size={38} style={{ background: 'rgba(255,255,255,0.2)', flexShrink: 0 }}>
                <RobotOutlined style={{ fontSize: 18, color: '#fff' }} />
              </Avatar>
              <div>
                <div style={{ color: '#fff', fontWeight: 700, fontSize: 14, lineHeight: 1.3 }}>Gamyam AI</div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <Tooltip title="Conversation history">
                <button onClick={openHistoryPanel} style={{
                  background: showHistory ? 'rgba(255,255,255,0.35)' : 'rgba(255,255,255,0.15)',
                  border: 'none', cursor: 'pointer',
                  width: 30, height: 30, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  transition: 'background 0.15s',
                }}>
                  <HistoryOutlined style={{ color: '#fff', fontSize: 14 }} />
                </button>
              </Tooltip>
              <Tooltip title="New chat">
                <button onClick={handleNewChat} style={{
                  background: 'rgba(255,255,255,0.15)', border: 'none', cursor: 'pointer',
                  width: 30, height: 30, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  transition: 'background 0.15s',
                }}>
                  <PlusOutlined style={{ color: '#fff', fontSize: 14 }} />
                </button>
              </Tooltip>
              <Tooltip title={showInfo ? 'Back to chat' : 'What can I do?'}>
                <button onClick={() => { setShowInfo((v) => !v); setShowHistory(false); }} style={{
                  background: showInfo ? 'rgba(255,255,255,0.35)' : 'rgba(255,255,255,0.15)',
                  border: 'none', cursor: 'pointer',
                  width: 30, height: 30, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  transition: 'background 0.15s',
                }}>
                  <InfoCircleOutlined style={{ color: '#fff', fontSize: 14 }} />
                </button>
              </Tooltip>
              <Tooltip title="Open full page">
                <button onClick={() => { onClose(); navigate('/chat'); }} style={{
                  background: 'rgba(255,255,255,0.15)', border: 'none', cursor: 'pointer',
                  width: 30, height: 30, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  transition: 'background 0.15s',
                }}>
                  <ExpandAltOutlined style={{ color: '#fff', fontSize: 14 }} />
                </button>
              </Tooltip>
              <button onClick={onClose} style={{
                background: 'rgba(255,255,255,0.15)', border: 'none', cursor: 'pointer',
                width: 30, height: 30, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'background 0.15s',
              }}>
                <CloseOutlined style={{ color: '#fff', fontSize: 14 }} />
              </button>
            </div>
          </div>

          {/* Offline banner */}
          {!isOnline && (
            <div style={{ background: '#fef2f2', borderBottom: '1px solid #fecaca', padding: '7px 14px', display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
              <span style={{ fontSize: 11.5, color: '#dc2626', fontWeight: 500 }}>⚠️ You are offline. Check your connection.</span>
            </div>
          )}

          {/* New chat confirmation */}
          {confirmNewChat && (
            <div style={{ background: '#fffbeb', borderBottom: '1px solid #fcd34d', padding: '10px 14px', flexShrink: 0 }}>
              <div style={{ fontSize: 12, color: '#92400e', fontWeight: 600, marginBottom: 8 }}>Start a new chat? This will clear the current conversation.</div>
              <div style={{ display: 'flex', gap: 6 }}>
                <button
                  onClick={doNewChat}
                  style={{ fontSize: 11.5, fontWeight: 600, padding: '4px 12px', borderRadius: 8, border: 'none', background: '#dc2626', color: '#fff', cursor: 'pointer' }}
                >
                  Yes, start fresh
                </button>
                <button
                  onClick={() => setConfirmNewChat(false)}
                  style={{ fontSize: 11.5, fontWeight: 600, padding: '4px 12px', borderRadius: 8, border: '1px solid #e2e8f0', background: '#fff', color: '#374151', cursor: 'pointer' }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* History Panel */}
          {showHistory && (
            <HistoryPanel
              sessions={sessions}
              loading={sessionsLoading}
              onSelectSession={handleSelectSession}
              onClose={() => setShowHistory(false)}
              onDeleteSession={handleDeleteSession}
              onRenameSession={handleRenameSession}
            />
          )}

          {/* Info Panel */}
          {!showHistory && showInfo && <InfoPanel role={user?.role} onClose={() => setShowInfo(false)} />}

          {/* Messages */}
          {!showHistory && !showInfo && (
            <div style={{ flex: 1, overflowY: 'auto', padding: '16px 16px 8px', display: 'flex', flexDirection: 'column', gap: 12, background: '#fafbfc' }}>
              {messages.length === 0 && (
                <div style={{ textAlign: 'center', padding: '32px 16px' }}>
                  <div style={{
                    width: 56, height: 56, borderRadius: 16, margin: '0 auto 14px',
                    background: 'linear-gradient(135deg,#667eea,#764ba2)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    boxShadow: '0 6px 20px rgba(102,126,234,0.35)',
                  }}>
                    <RobotOutlined style={{ fontSize: 26, color: '#fff' }} />
                  </div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: '#1e293b', marginBottom: 6 }}>How can I help you?</div>
                  <div style={{ fontSize: 12, color: '#64748b', marginBottom: 20 }}>
                    Ask about cycles, tasks, feedback, or more.
                  </div>
                  <div style={{ fontWeight: 600, fontSize: 11, color: '#94a3b8', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                    Suggested
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {quickSuggestions.map((s) => (
                      <button key={s} onClick={() => handleSend(s)} style={{
                        background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10,
                        padding: '9px 14px', fontSize: 12.5, cursor: 'pointer', color: '#374151', fontWeight: 500,
                        textAlign: 'left', boxShadow: '0 1px 3px rgba(0,0,0,0.05)', transition: 'all 0.15s',
                      }}
                        onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#667eea'; e.currentTarget.style.color = '#667eea'; }}
                        onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#e2e8f0'; e.currentTarget.style.color = '#374151'; }}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((msg, i) => {
                const label = formatDateLabel(msg.ts);
                const prevLabel = i > 0 ? formatDateLabel(messages[i - 1].ts) : null;
                const showSep = label && label !== prevLabel;
                return (
                  <div key={`${msg.ts}-${i}`}>
                    {showSep && <DateSeparator label={label} />}
                    <WidgetBubble msg={msg} onSuggest={handleSend} onDirectAction={handleDirectAction} onNavigate={(url) => { onClose(); navigate(url); }} role={user?.role} />
                  </div>
                );
              })}

              {loading && !streaming && (
                <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                  <Avatar size={28} style={{ background: 'linear-gradient(135deg,#667eea,#764ba2)', flexShrink: 0 }}>
                    <RobotOutlined style={{ fontSize: 13 }} />
                  </Avatar>
                  <div style={{
                    background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '3px 14px 14px 14px',
                    padding: '10px 14px', boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
                  }}>
                    <TypingDots />
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          )}

          {/* Confirm */}
          {awaitConfirm && !loading && (
            <div style={{
              background: 'linear-gradient(135deg,#eff6ff,#f0fdf4)', borderTop: '1px solid #bfdbfe',
              padding: '10px 14px', flexShrink: 0,
            }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: pendingConfirmData && Object.keys(pendingConfirmData).length ? 6 : 0 }}>
                <span style={{ fontSize: 12, color: '#1d4ed8', flex: 1, fontWeight: 700 }}>⚡ Confirm action?</span>
                <Button type="primary" size="small" onClick={() => handleConfirm(true)}
                  style={{ borderRadius: 8, background: '#22c55e', borderColor: '#22c55e', fontWeight: 600 }}>
                  ✓ Yes
                </Button>
                <Button danger size="small" onClick={() => handleConfirm(false)} style={{ borderRadius: 8, fontWeight: 600 }}>
                  ✗ No
                </Button>
              </div>
              {pendingConfirmData && Object.keys(pendingConfirmData).length > 0 && (
                <div style={{ fontSize: 10.5, color: '#1e40af', background: 'rgba(255,255,255,0.7)', borderRadius: 6, padding: '5px 8px', lineHeight: 1.6 }}>
                  {Object.entries(pendingConfirmData)
                    .filter(([k]) => k !== 'cycle_id')
                    .map(([k, v]) => (
                      <div key={k}><b>{k.replace(/_/g, ' ')}:</b> {String(v)}</div>
                    ))
                  }
                </div>
              )}
            </div>
          )}

          {/* B5: Session recovery banner */}
          {recoveryBanner && !loading && !awaitConfirm && !showInfo && (
            <div style={{
              background: 'linear-gradient(135deg,#fffbeb,#fef3c7)',
              borderTop: '1px solid #fcd34d',
              padding: '9px 14px',
              flexShrink: 0,
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <span style={{ fontSize: 11.5, color: '#92400e', flex: 1, lineHeight: 1.4 }}>
                ⏸ Paused: <strong>{recoveryBanner.intent_label}</strong>
                {recoveryBanner.awaiting_confirm ? ' — waiting for confirmation' : ' — waiting for your input'}
              </span>
              <button
                onClick={() => setRecoveryBanner(null)}
                style={{
                  fontSize: 11, fontWeight: 600, padding: '3px 10px', borderRadius: 8,
                  border: '1.5px solid #d97706', background: '#fff',
                  color: '#b45309', cursor: 'pointer', flexShrink: 0,
                  transition: 'all 0.15s',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = '#d97706'; e.currentTarget.style.color = '#fff'; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = '#fff'; e.currentTarget.style.color = '#b45309'; }}
              >
                Continue
              </button>
              <button
                onClick={handleDiscardSession}
                style={{
                  fontSize: 11, fontWeight: 600, padding: '3px 10px', borderRadius: 8,
                  border: '1.5px solid #fca5a5', background: '#fff',
                  color: '#dc2626', cursor: 'pointer', flexShrink: 0,
                  transition: 'all 0.15s',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = '#dc2626'; e.currentTarget.style.color = '#fff'; e.currentTarget.style.borderColor = '#dc2626'; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = '#fff'; e.currentTarget.style.color = '#dc2626'; e.currentTarget.style.borderColor = '#fca5a5'; }}
              >
                Discard
              </button>
            </div>
          )}

          {/* Quick command chips — visible once conversation has started */}
          {messages.length > 0 && !loading && !awaitConfirm && !showInfo && (
            <div style={{
              padding: '8px 14px 0',
              borderTop: '1px solid #f1f5f9',
              background: '#fff',
              flexShrink: 0,
            }}>
              <div style={{ display: 'flex', gap: 5, overflowX: 'auto', scrollbarWidth: 'none' }}>
                <style>{`div.chat-chips::-webkit-scrollbar{display:none}`}</style>
                {quickSuggestions.map((s) => (
                  <button
                    key={s}
                    onClick={() => handleSend(s)}
                    style={{
                      whiteSpace: 'nowrap', fontSize: 11, fontWeight: 500,
                      padding: '4px 11px', borderRadius: 20,
                      border: '1px solid #e2e8f0', background: '#f8fafc',
                      color: '#374151', cursor: 'pointer', flexShrink: 0,
                      transition: 'all 0.15s',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = '#667eea';
                      e.currentTarget.style.color = '#667eea';
                      e.currentTarget.style.background = '#eef2ff';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = '#e2e8f0';
                      e.currentTarget.style.color = '#374151';
                      e.currentTarget.style.background = '#f8fafc';
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Input — hidden when history or info panel is showing */}
          <div style={{ padding: '10px 14px 14px', borderTop: messages.length > 0 && !loading && !awaitConfirm && !showInfo && !showHistory ? 'none' : '1px solid #f1f5f9', background: '#fff', flexShrink: 0, display: showHistory ? 'none' : undefined }}>
            <div style={{
              display: 'flex', gap: 8, alignItems: 'center',
              background: '#f8fafc', border: '1.5px solid #e2e8f0', borderRadius: 14,
              padding: '6px 8px 6px 14px', transition: 'border-color 0.2s',
            }}
              onFocusCapture={(e) => e.currentTarget.style.borderColor = '#667eea'}
              onBlurCapture={(e) => e.currentTarget.style.borderColor = '#e2e8f0'}
            >
              {/* Hidden file input */}
              <input ref={fileInputRef} type="file" accept=".pdf,.txt" style={{ display: 'none' }} onChange={handleFileUpload} />
              <Input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onPressEnter={() => !awaitConfirm && handleSend()}
                placeholder={awaitConfirm ? 'Confirm or cancel the action above…' : voiceListening ? 'Listening…' : 'Ask anything…'}
                disabled={loading || awaitConfirm}
                bordered={false}
                style={{ fontSize: 13.5, background: 'transparent', flex: 1, padding: 0, color: awaitConfirm ? '#94a3b8' : undefined }}
              />
              {/* PDF upload button — HR/Super Admin only */}
              {['HR_ADMIN', 'SUPER_ADMIN'].includes(user?.role) && (
                <Tooltip title="Upload PDF to create template">
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    disabled={loading || awaitConfirm}
                    style={{ width: 32, height: 32, borderRadius: 8, border: 'none', background: 'transparent', cursor: loading ? 'default' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}
                  >
                    <PaperClipOutlined style={{ fontSize: 15, color: '#94a3b8' }} />
                  </button>
                </Tooltip>
              )}
              <Tooltip title={voiceListening ? 'Stop (will auto-send)' : 'Voice input — speak then auto-sends'}>
                <button
                  onClick={toggleListening}
                  disabled={awaitConfirm || loading}
                  style={{
                    width: 32, height: 32, borderRadius: 8, border: 'none', flexShrink: 0,
                    background: voiceListening ? '#fee2e2' : 'transparent',
                    cursor: (awaitConfirm || loading) ? 'default' : 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all 0.15s',
                    animation: voiceListening ? 'voicePulse 1.2s ease-in-out infinite' : 'none',
                  }}
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
                    stroke={voiceListening ? '#ef4444' : '#94a3b8'} strokeWidth="2.2"
                    strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
                    <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                    <line x1="12" y1="19" x2="12" y2="23"/>
                    <line x1="8" y1="23" x2="16" y2="23"/>
                  </svg>
                </button>
              </Tooltip>
              <button onClick={() => handleSend()} disabled={loading || awaitConfirm || !input.trim()} style={{
                width: 34, height: 34, borderRadius: 10, border: 'none', cursor: (input.trim() && !awaitConfirm) ? 'pointer' : 'default',
                background: (input.trim() && !awaitConfirm) ? 'linear-gradient(135deg,#667eea,#764ba2)' : '#e2e8f0',
                display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                transition: 'all 0.15s', boxShadow: (input.trim() && !awaitConfirm) ? '0 2px 8px rgba(102,126,234,0.3)' : 'none',
              }}>
                <SendOutlined style={{ color: (input.trim() && !awaitConfirm) ? '#fff' : '#94a3b8', fontSize: 13 }} />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
