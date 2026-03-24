import { useEffect, useState } from 'react';
import {
  Card, Row, Col, Statistic, Select, Space, Typography, Tag, Spin, message,
} from 'antd';
import {
  MessageOutlined, UserOutlined, RobotOutlined,
  CheckCircleOutlined, ReloadOutlined,
} from '@ant-design/icons';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import { getChatAnalytics } from '../../api/chat';
import usePageTitle from '../../hooks/usePageTitle';

const { Title, Text } = Typography;

const INTENT_LABELS = {
  create_cycle:       'Create Cycle',
  create_template:    'Create Template',
  nominate_peers:     'Nominate Peers',
  cancel_cycle:       'Cancel Cycle',
  activate_cycle:     'Activate Cycle',
  close_cycle:        'Close Cycle',
  finalize_cycle:     'Finalize Cycle',
  release_results:    'Release Results',
  approve_nomination: 'Approve Nomination',
  reject_nomination:  'Reject Nomination',
  add_participant:    'Add Participant',
  remove_participant: 'Remove Participant',
  list_cycles:        'List Cycles',
  list_templates:     'List Templates',
  list_nominations:   'List Nominations',
  check_status:       'Check Status',
  help:               'Help',
};

const STATUS_COLORS = {
  success:          '#10b981',
  failed:           '#ef4444',
  needs_input:      '#f59e0b',
  awaiting_confirm: '#6366f1',
  rejected:         '#f43f5e',
  clarify:          '#0ea5e9',
  cancelled:        '#9ca3af',
};

const BAR_COLORS = [
  '#6366f1','#8b5cf6','#a78bfa','#c4b5fd',
  '#818cf8','#7c3aed','#4f46e5','#4338ca',
  '#3730a3','#312e81','#1e1b4b','#0f172a',
];

function StatCard({ title, value, suffix, icon, color, subtitle }) {
  return (
    <Card size="small" bodyStyle={{ padding: '14px 16px' }}>
      <Statistic
        title={<Text style={{ fontSize: 11, color: '#6b7280' }}>{title}</Text>}
        value={value}
        suffix={suffix && <Text style={{ fontSize: 13, color: '#9ca3af' }}>{suffix}</Text>}
        valueStyle={{ fontSize: 24, fontWeight: 700, color }}
        prefix={<span style={{ color, marginRight: 6, fontSize: 16 }}>{icon}</span>}
      />
      {subtitle && <Text type="secondary" style={{ fontSize: 11 }}>{subtitle}</Text>}
    </Card>
  );
}

export default function ChatAnalyticsPage() {
  usePageTitle('Chat Analytics');
  const [data,    setData]    = useState(null);
  const [days,    setDays]    = useState(30);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await getChatAnalytics(days);
      setData(res.data);
    } catch {
      message.error('Failed to load analytics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [days]);

  const intentChartData = (data?.intent_breakdown || []).map((d) => ({
    name:  INTENT_LABELS[d.intent] || d.intent?.replace(/_/g, ' ') || 'Unknown',
    count: d.count,
  }));

  const statusChartData = (data?.status_breakdown || []).map((d) => ({
    name:  d.execution_status?.replace(/_/g, ' ') || 'unknown',
    count: d.count,
    color: STATUS_COLORS[d.execution_status] || '#9ca3af',
  }));

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <Title level={4} style={{ margin: 0 }}>Chat Analytics</Title>
        <Space>
          <Select
            value={days}
            onChange={setDays}
            style={{ width: 130 }}
            options={[
              { value: 7,   label: 'Last 7 days' },
              { value: 30,  label: 'Last 30 days' },
              { value: 90,  label: 'Last 90 days' },
              { value: 365, label: 'Last 365 days' },
            ]}
          />
          <button
            onClick={load}
            style={{
              background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 6,
              padding: '5px 12px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
              fontSize: 13,
            }}
          >
            <ReloadOutlined /> Refresh
          </button>
        </Space>
      </div>

      <Spin spinning={loading}>

        {/* Stats row */}
        <Row gutter={[12, 12]}>
          <Col xs={12} sm={8} md={4}>
            <StatCard
              title="Total Messages"
              value={data?.total_messages ?? '—'}
              icon={<MessageOutlined />}
              color="#4f46e5"
              subtitle={`Last ${days} days`}
            />
          </Col>
          <Col xs={12} sm={8} md={4}>
            <StatCard
              title="Unique Users"
              value={data?.unique_users ?? '—'}
              icon={<UserOutlined />}
              color="#0891b2"
            />
          </Col>
          <Col xs={12} sm={8} md={4}>
            <StatCard
              title="LLM Fallbacks"
              value={data?.llm_fallback_count ?? '—'}
              suffix={data ? `(${data.llm_fallback_rate}%)` : ''}
              icon={<RobotOutlined />}
              color="#7c3aed"
            />
          </Col>
          <Col xs={12} sm={8} md={4}>
            <StatCard
              title="Successful"
              value={data?.success_count ?? '—'}
              suffix={data ? `(${data.success_rate}%)` : ''}
              icon={<CheckCircleOutlined />}
              color="#10b981"
            />
          </Col>
        </Row>

        {/* Charts row */}
        <Row gutter={[12, 12]} style={{ marginTop: 4 }}>

          {/* Daily volume */}
          <Col xs={24} lg={14}>
            <Card
              title={<span style={{ fontWeight: 600 }}>Message Volume</span>}
              size="small"
              bodyStyle={{ padding: '12px 4px 8px' }}
            >
              {data?.daily_volume?.length ? (
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={data.daily_volume} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis
                      dataKey="date"
                      tick={{ fontSize: 11 }}
                      tickFormatter={(v) => v.slice(5)}
                      interval="preserveStartEnd"
                    />
                    <YAxis tick={{ fontSize: 11 }} allowDecimals={false} width={28} />
                    <Tooltip
                      formatter={(v) => [v, 'Messages']}
                      labelFormatter={(l) => `Date: ${l}`}
                    />
                    <Bar dataKey="count" fill="#6366f1" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Text type="secondary">No data for this period</Text>
                </div>
              )}
            </Card>
          </Col>

          {/* Status breakdown */}
          <Col xs={24} lg={10}>
            <Card
              title={<span style={{ fontWeight: 600 }}>Outcome Breakdown</span>}
              size="small"
              bodyStyle={{ padding: '12px 4px 8px' }}
            >
              {statusChartData.length ? (
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart
                    data={statusChartData}
                    layout="vertical"
                    margin={{ top: 4, right: 16, left: 0, bottom: 4 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                    <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={110} />
                    <Tooltip formatter={(v) => [v, 'Messages']} />
                    <Bar dataKey="count" radius={[0, 3, 3, 0]}>
                      {statusChartData.map((entry, i) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Text type="secondary">No data for this period</Text>
                </div>
              )}
            </Card>
          </Col>

        </Row>

        {/* Top intents */}
        <Row gutter={[12, 12]} style={{ marginTop: 4 }}>
          <Col xs={24}>
            <Card
              title={<span style={{ fontWeight: 600 }}>Top Commands</span>}
              size="small"
              bodyStyle={{ padding: '12px 4px 8px' }}
            >
              {intentChartData.length ? (
                <ResponsiveContainer width="100%" height={230}>
                  <BarChart data={intentChartData} margin={{ top: 4, right: 16, left: 0, bottom: 50 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis
                      dataKey="name"
                      tick={{ fontSize: 11 }}
                      interval={0}
                      angle={-30}
                      textAnchor="end"
                    />
                    <YAxis tick={{ fontSize: 11 }} allowDecimals={false} width={28} />
                    <Tooltip formatter={(v) => [v, 'Times used']} />
                    <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                      {intentChartData.map((_, i) => (
                        <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ height: 230, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Text type="secondary">No commands used in this period</Text>
                </div>
              )}
            </Card>
          </Col>
        </Row>

        {/* Per-user activity + Failed intents */}
        <Row gutter={[12, 12]} style={{ marginTop: 4 }}>
          <Col xs={24} lg={14}>
            <Card title={<span style={{ fontWeight: 600 }}>Most Active Users</span>} size="small">
              {data?.per_user_activity?.length ? (
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <th style={{ textAlign: 'left', padding: '6px 8px', color: '#94a3b8', fontWeight: 600, fontSize: 11 }}>#</th>
                      <th style={{ textAlign: 'left', padding: '6px 8px', color: '#94a3b8', fontWeight: 600, fontSize: 11 }}>Name</th>
                      <th style={{ textAlign: 'left', padding: '6px 8px', color: '#94a3b8', fontWeight: 600, fontSize: 11 }}>Email</th>
                      <th style={{ textAlign: 'right', padding: '6px 8px', color: '#94a3b8', fontWeight: 600, fontSize: 11 }}>Messages</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.per_user_activity.map((u, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid #f8fafc' }}>
                        <td style={{ padding: '6px 8px', color: '#94a3b8', fontSize: 11 }}>{i + 1}</td>
                        <td style={{ padding: '6px 8px', fontWeight: 600, color: '#1e293b' }}>{u.name || '—'}</td>
                        <td style={{ padding: '6px 8px', color: '#64748b' }}>{u.email}</td>
                        <td style={{ padding: '6px 8px', textAlign: 'right' }}>
                          <Tag color="purple" style={{ fontSize: 11 }}>{u.count}</Tag>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <Text type="secondary" style={{ fontSize: 12 }}>No user data for this period</Text>
              )}
            </Card>
          </Col>

          <Col xs={24} lg={10}>
            <Card title={<span style={{ fontWeight: 600 }}>Failed / Unrecognized Intents</span>} size="small">
              {data?.failed_intents?.length ? (
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <th style={{ textAlign: 'left', padding: '6px 8px', color: '#94a3b8', fontWeight: 600, fontSize: 11 }}>Intent</th>
                      <th style={{ textAlign: 'right', padding: '6px 8px', color: '#94a3b8', fontWeight: 600, fontSize: 11 }}>Count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.failed_intents.map((f, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid #f8fafc' }}>
                        <td style={{ padding: '6px 8px', color: '#1e293b' }}>{f.intent?.replace(/_/g, ' ') || 'unknown'}</td>
                        <td style={{ padding: '6px 8px', textAlign: 'right' }}>
                          <Tag color="red" style={{ fontSize: 11 }}>{f.count}</Tag>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <Text type="secondary" style={{ fontSize: 12 }}>No failed intents in this period</Text>
              )}
            </Card>
          </Col>
        </Row>

      </Spin>
    </Space>
  );
}
