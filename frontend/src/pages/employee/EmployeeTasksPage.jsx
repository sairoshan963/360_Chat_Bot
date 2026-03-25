import { useEffect, useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Table, Tag, Button, Typography, Space, Badge, Skeleton, Empty, Select } from 'antd';
import { ClockCircleOutlined, CheckCircleOutlined, UnorderedListOutlined } from '@ant-design/icons';
import { getMyTasks } from '../../api/tasks';
import usePageTitle from '../../hooks/usePageTitle';
import ErrorCard from '../../components/shared/ErrorCard';

const { Title, Text } = Typography;

const STATUS_COLOR = { CREATED: 'default', PENDING: 'default', IN_PROGRESS: 'blue', DRAFT: 'blue', SUBMITTED: 'green', LOCKED: 'orange' };
const TYPE_COLOR   = { SELF: 'purple', MANAGER: 'blue', PEER: 'cyan' };

function deadlineTag(dateStr) {
  if (!dateStr) return null;
  const days = Math.ceil((new Date(dateStr) - new Date()) / (1000*60*60*24));
  if (days < 0)  return <Tag color="error"   icon={<ClockCircleOutlined />}>Overdue</Tag>;
  if (days === 0) return <Tag color="error"  icon={<ClockCircleOutlined />}>Due today</Tag>;
  if (days === 1) return <Tag color="error"  icon={<ClockCircleOutlined />}>Due tomorrow</Tag>;
  if (days <= 5)  return <Tag color="warning" icon={<ClockCircleOutlined />}>Due in {days} days</Tag>;
  return null;
}

export default function EmployeeTasksPage() {
  usePageTitle('My Tasks');
  const navigate = useNavigate();
  const [tasks,   setTasks]   = useState([]);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(false);
  const [cycleFilter, setCycleFilter] = useState('ALL');

  const load = useCallback(() => {
    setLoading(true);
    setError(false);
    getMyTasks().then((r) => setTasks(r.data.tasks || [])).catch(() => setError(true)).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const cycleOptions = useMemo(() => {
    const seen = new Map();
    for (const t of tasks) { if (t.cycle && !seen.has(t.cycle)) seen.set(t.cycle, t.cycle_name); }
    return [...seen.entries()].map(([id, name]) => ({ value: id, label: name }));
  }, [tasks]);

  const visibleTasks = useMemo(() => (cycleFilter === 'ALL' ? tasks : tasks.filter((t) => t.cycle === cycleFilter)), [tasks, cycleFilter]);

  const columns = [
    { title: 'Reviewee',     render: (_, r) => `${r.reviewee_first} ${r.reviewee_last}` },
    { title: 'Type',         dataIndex: 'reviewer_type', render: (v) => <Tag color={TYPE_COLOR[v]||'default'}>{v}</Tag> },
    { title: 'Cycle',        dataIndex: 'cycle_name' },
    { title: 'Due', dataIndex: 'review_deadline', render: (v, r) => {
      if (!v) return '—';
      const tag = !['SUBMITTED','LOCKED'].includes(r.status) ? deadlineTag(v) : null;
      return <Space size={6}><span>{new Date(v).toLocaleDateString()}</span>{tag}</Space>;
    }},
    { title: 'Status', dataIndex: 'status', render: (v, r) => {
      const effectiveStatus = r.cycle_state !== 'ACTIVE' && !['SUBMITTED','LOCKED'].includes(v) ? 'LOCKED' : v;
      return <Tag color={STATUS_COLOR[effectiveStatus]||'default'}>{effectiveStatus}</Tag>;
    }},
    { title: 'Action', render: (_, r) => {
      const isLocked = ['SUBMITTED','LOCKED'].includes(r.status) || (r.cycle_state !== 'ACTIVE' && r.status !== 'SUBMITTED');
      if (isLocked) return <Button size="small" onClick={() => navigate(`/employee/tasks/${r.id}`)}>View</Button>;
      return <Button type="primary" size="small" onClick={() => navigate(`/employee/tasks/${r.id}`)}>{['IN_PROGRESS','DRAFT'].includes(r.status)?'Continue':'Start'}</Button>;
    }},
  ];

  const isActionable = (t) => ['CREATED','PENDING','IN_PROGRESS','DRAFT'].includes(t.status) && t.cycle_state === 'ACTIVE';
  const pending   = visibleTasks.filter(isActionable);
  const completed = visibleTasks.filter((t) => !isActionable(t));

  if (loading) return <Space direction="vertical" size={16} style={{ width: '100%' }}><Card><Skeleton active paragraph={{ rows: 1 }} /></Card><Card><Skeleton active paragraph={{ rows: 5 }} /></Card></Space>;
  if (error) return <Space direction="vertical" size={16} style={{ width: '100%' }}><Card><Title level={4} style={{ margin: 0 }}>My Feedback Tasks</Title></Card><ErrorCard message="Could not load your tasks." onRetry={load} /></Space>;

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card>
        <Space style={{ width: '100%', justifyContent: 'space-between' }} wrap>
          <Space>
            <Title level={4} style={{ margin: 0 }}>My Feedback Tasks</Title>
            {pending.length > 0 && <Badge count={pending.length} />}
          </Space>
          {cycleOptions.length > 1 && (
            <Select value={cycleFilter} onChange={setCycleFilter} style={{ minWidth: 260 }} showSearch filterOption={(input, opt) => (opt?.label ?? '').toLowerCase().includes(input.toLowerCase())}
              options={[{ value: 'ALL', label: `All Cycles (${tasks.length} tasks)` }, ...cycleOptions]} />
          )}
        </Space>
      </Card>

      <Card title={<Space><ClockCircleOutlined style={{ color: pending.length > 0 ? '#faad14' : '#94a3b8' }} /><span>Pending ({pending.length})</span></Space>}>
        {pending.length === 0 ? (
          <Empty image={<CheckCircleOutlined style={{ fontSize: 48, color: '#52c41a' }} />} imageStyle={{ height: 56 }} description={<Space direction="vertical" size={2}><Text strong>All caught up!</Text><Text type="secondary">You have no pending feedback tasks.</Text></Space>} />
        ) : (
          <Table rowKey="id" columns={columns} dataSource={pending} pagination={{ pageSize: 10 }} size="small" />
        )}
      </Card>

      {completed.length > 0 && (
        <Card title={<Space><CheckCircleOutlined style={{ color: '#52c41a' }} /><span>Completed ({completed.length})</span></Space>}>
          <Table rowKey="id" columns={columns} dataSource={completed} pagination={{ pageSize: 5 }} size="small" />
        </Card>
      )}

      {visibleTasks.length === 0 && tasks.length === 0 && (
        <Card>
          <Empty image={<UnorderedListOutlined style={{ fontSize: 48, color: '#cbd5e1' }} />} imageStyle={{ height: 56 }}
            description={<Space direction="vertical" size={2}><Text strong>No tasks assigned yet</Text><Text type="secondary">Tasks appear once a review cycle is activated and you are added as a participant.</Text></Space>} />
        </Card>
      )}
    </Space>
  );
}
