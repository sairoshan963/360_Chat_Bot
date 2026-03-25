import { useEffect, useState } from 'react';
import {
  Table, Card, Typography, Select, DatePicker, Button, Space,
  Tag, message, Badge, Tooltip, Avatar, Statistic, Row, Col,
} from 'antd';
import {
  ReloadOutlined, UserOutlined, ClockCircleOutlined,
  FileTextOutlined, TeamOutlined, AuditOutlined,
} from '@ant-design/icons';
import { getAuditLogs } from '../../api/reports';
import usePageTitle from '../../hooks/usePageTitle';

const { Title, Text } = Typography;
const { Option } = Select;
const { RangePicker } = DatePicker;

const ACTION_META = {
  CREATE_CYCLE:        { color: 'blue',     label: 'Create Cycle',        badge: 'processing' },
  CLOSE_CYCLE:         { color: 'orange',   label: 'Close Cycle',         badge: 'warning' },
  RELEASE_RESULTS:     { color: 'green',    label: 'Release Results',     badge: 'success' },
  SUBMIT_FEEDBACK:     { color: 'cyan',     label: 'Submit Feedback',     badge: 'processing' },
  SUBMIT_DRAFT:        { color: 'geekblue', label: 'Save Draft',          badge: 'default' },
  IDENTITY_ACCESS:     { color: 'red',      label: 'Identity Access',     badge: 'error' },
  OVERRIDE_ACTION:     { color: 'volcano',  label: 'Override',            badge: 'error' },
  CREATE_USER:         { color: 'purple',   label: 'Create User',         badge: 'processing' },
  USER_CREATED:        { color: 'purple',   label: 'User Created',        badge: 'processing' },
  USER_UPDATED:        { color: 'blue',     label: 'User Updated',        badge: 'processing' },
  USER_DEACTIVATED:    { color: 'orange',   label: 'User Deactivated',    badge: 'warning' },
  ADMIN_PASSWORD_RESET:{ color: 'gold',     label: 'Password Reset',      badge: 'warning' },
  IMPORT_ORG:          { color: 'geekblue', label: 'Import Org',          badge: 'processing' },
  EXPORT_REPORT:       { color: 'gold',     label: 'Export Report',       badge: 'default' },
  VIEW_REPORT:         { color: 'lime',     label: 'View Report',         badge: 'default' },
  APPROVE_NOMINATION:  { color: 'green',    label: 'Approve Nomination',  badge: 'success' },
  REJECT_NOMINATION:   { color: 'red',      label: 'Reject Nomination',   badge: 'error' },
  FINALIZE_CYCLE:      { color: 'blue',     label: 'Finalize Cycle',      badge: 'processing' },
};

const ALL_ACTIONS = Object.keys(ACTION_META);

function relativeTime(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins  = Math.floor(diff / 60000);
  const hours = Math.floor(mins / 60);
  const days  = Math.floor(hours / 24);
  if (days  > 0) return `${days}d ago`;
  if (hours > 0) return `${hours}h ago`;
  if (mins  > 0) return `${mins}m ago`;
  return 'just now';
}

function formatDetails(newVal) {
  if (!newVal) return <Text type="secondary">—</Text>;
  const entries = Object.entries(newVal);
  if (!entries.length) return <Text type="secondary">—</Text>;
  return (
    <Space direction="vertical" size={0}>
      {entries.slice(0, 3).map(([k, v]) => (
        <Text key={k} style={{ fontSize: 12 }}>
          <Text type="secondary" style={{ fontSize: 11 }}>{k}: </Text>
          <Text code style={{ fontSize: 11 }}>
            {typeof v === 'object' ? JSON.stringify(v).slice(0, 40) : String(v).slice(0, 60)}
          </Text>
        </Text>
      ))}
      {entries.length > 3 && <Text type="secondary" style={{ fontSize: 11 }}>+{entries.length - 3} more</Text>}
    </Space>
  );
}

export default function AuditPage() {
  usePageTitle('Audit Logs');
  const [logs,    setLogs]    = useState([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({ action_type: '', limit: 200 });

  const load = async () => {
    if (filters.from && filters.to && filters.from > filters.to) {
      message.error('Start date must be before end date');
      return;
    }
    setLoading(true);
    try {
      const params = { limit: filters.limit };
      if (filters.action_type) params.action_type = filters.action_type;
      if (filters.from)        params.from         = filters.from;
      if (filters.to)          params.to           = filters.to;
      const res = await getAuditLogs(params);
      setLogs(res.data.logs || []);
    } catch { message.error('Failed to load audit logs'); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  /* ---- stats ---- */
  const totalToday = logs.filter((l) => {
    const d = new Date(l.created_at);
    const now = new Date();
    return d.getDate() === now.getDate() && d.getMonth() === now.getMonth();
  }).length;

  const uniqueActors = new Set(logs.map((l) => l.actor_email).filter(Boolean)).size;
  const overrides    = logs.filter((l) => l.action_type === 'OVERRIDE_ACTION').length;
  const submissions  = logs.filter((l) => l.action_type === 'SUBMIT_FEEDBACK').length;

  /* ---- columns ---- */
  const columns = [
    {
      title: 'Time',
      dataIndex: 'created_at',
      width: 160,
      render: (v) => (
        <Tooltip title={new Date(v).toLocaleString()}>
          <Space direction="vertical" size={0}>
            <Text style={{ fontSize: 12 }}>{new Date(v).toLocaleDateString()}</Text>
            <Text type="secondary" style={{ fontSize: 11 }}>
              <ClockCircleOutlined style={{ marginRight: 4 }} />
              {new Date(v).toLocaleTimeString()} · {relativeTime(v)}
            </Text>
          </Space>
        </Tooltip>
      ),
    },
    {
      title: 'Action',
      dataIndex: 'action_type',
      width: 180,
      render: (v) => {
        const meta = ACTION_META[v] || { color: 'default', label: v?.replace(/_/g, ' ') || v };
        return (
          <Tag color={meta.color} style={{ fontWeight: 600, letterSpacing: 0.3 }}>
            {meta.label || v?.replace(/_/g, ' ')}
          </Tag>
        );
      },
    },
    {
      title: 'Entity',
      width: 180,
      render: (_, r) => (
        <Space direction="vertical" size={0}>
          <Tag style={{ fontSize: 11 }}>{r.entity_type}</Tag>
          {r.entity_name && <Text style={{ fontSize: 12, fontWeight: 500 }}>{r.entity_name}</Text>}
        </Space>
      ),
    },
    {
      title: 'Actor',
      width: 220,
      render: (_, r) => {
        const name  = r.actor_name  || 'System';
        const email = r.actor_email || '';
        const isSystem = !r.actor_email;
        return (
          <Space>
            <Avatar
              size="small"
              icon={isSystem ? <AuditOutlined /> : <UserOutlined />}
              style={{ backgroundColor: isSystem ? '#aaa' : '#4f46e5', flexShrink: 0 }}
            >
              {!isSystem && name.charAt(0).toUpperCase()}
            </Avatar>
            <Space direction="vertical" size={0}>
              <Text style={{ fontSize: 13, fontWeight: 500 }}>{name}</Text>
              {email && <Text type="secondary" style={{ fontSize: 11 }}>{email}</Text>}
            </Space>
          </Space>
        );
      },
    },
    {
      title: 'Details',
      render: (_, r) => formatDetails(r.new_value),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>

      {/* ── Stats row ── */}
      <Row gutter={16}>
        {[
          { title: 'Total Events',  value: logs.length,   icon: <FileTextOutlined />, color: '#4f46e5' },
          { title: "Today's Events", value: totalToday,   icon: <ClockCircleOutlined />, color: '#0891b2' },
          { title: 'Active Users',  value: uniqueActors,  icon: <TeamOutlined />,     color: '#059669' },
          { title: 'Overrides',     value: overrides,     icon: <AuditOutlined />,    color: overrides ? '#dc2626' : '#6b7280' },
          { title: 'Submissions',   value: submissions,   icon: <FileTextOutlined />, color: '#7c3aed' },
        ].map((s) => (
          <Col key={s.title} xs={12} sm={8} md={4} lg={4} xl={4} style={{ marginBottom: 8 }}>
            <Card size="small" bodyStyle={{ padding: '12px 16px' }}>
              <Statistic
                title={<Text style={{ fontSize: 11, color: '#6b7280' }}>{s.title}</Text>}
                value={s.value}
                valueStyle={{ fontSize: 22, fontWeight: 700, color: s.color }}
                prefix={<span style={{ color: s.color, marginRight: 4, fontSize: 14 }}>{s.icon}</span>}
              />
            </Card>
          </Col>
        ))}
      </Row>

      {/* ── Main table ── */}
      <Card
        title={
          <Space>
            <Badge status="processing" />
            <span style={{ fontWeight: 600 }}>Activity Monitor</span>
            <Tag color="default">{logs.length} events</Tag>
          </Space>
        }
        extra={
          <Space wrap>
            <Select
              placeholder="Filter by action"
              allowClear
              style={{ width: 200 }}
              value={filters.action_type || undefined}
              onChange={(v) => setFilters((f) => ({ ...f, action_type: v || '' }))}
            >
              {ALL_ACTIONS.map((a) => (
                <Option key={a} value={a}>
                  <Tag color={ACTION_META[a]?.color || 'default'} style={{ marginRight: 6 }}>
                    {ACTION_META[a]?.label || a.replace(/_/g, ' ')}
                  </Tag>
                </Option>
              ))}
            </Select>
            <RangePicker
              onChange={(_, strs) => setFilters((f) => ({ ...f, from: strs[0] || '', to: strs[1] || '' }))}
            />
            <Button type="primary" icon={<ReloadOutlined />} onClick={load} loading={loading}>
              Refresh
            </Button>
          </Space>
        }
      >
        <Table
          rowKey="id"
          columns={columns}
          dataSource={logs}
          loading={loading}
          size="small"
          pagination={{ pageSize: 25, showSizeChanger: true, pageSizeOptions: ['25','50','100'] }}
          scroll={{ x: 900 }}
          rowClassName={(r) => r.action_type === 'OVERRIDE_ACTION' || r.action_type === 'IDENTITY_ACCESS'
            ? 'ant-table-row-danger'
            : ''}
        />
      </Card>

      <style>{`
        .ant-table-row-danger td { background: #fff5f5 !important; }
        .ant-table-row-danger:hover td { background: #fee2e2 !important; }
      `}</style>
    </Space>
  );
}
