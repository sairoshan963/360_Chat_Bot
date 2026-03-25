import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Select, Button, Space, Typography, Table, Tag, message, Empty } from 'antd';
import { EyeOutlined, FileExcelOutlined } from '@ant-design/icons';
import { listCycles, getParticipants } from '../../api/cycles';
import { exportAllReports } from '../../api/reports';
import usePageTitle from '../../hooks/usePageTitle';

const { Title } = Typography;
const { Option } = Select;

const STATE_COLOR = { RESULTS_RELEASED: 'purple', ARCHIVED: 'red' };

export default function ViewReportsPage() {
  usePageTitle('View Reports');
  const navigate = useNavigate();
  const [cycles,       setCycles]       = useState([]);
  const [cycleId,      setCycleId]      = useState('');
  const [participants, setParticipants] = useState([]);
  const [loading,      setLoading]      = useState(false);
  const [exporting,    setExporting]    = useState(false);

  useEffect(() => {
    listCycles().then((r) => {
      const released = (r.data.cycles || []).filter((c) => ['RESULTS_RELEASED','ARCHIVED'].includes(c.state));
      setCycles(released);
      if (released.length > 0) setCycleId(String(released[0].id));
    }).catch(() => message.error('Failed to load cycles'));
  }, []);

  useEffect(() => {
    if (!cycleId) return;
    setLoading(true);
    getParticipants(cycleId).then((r) => setParticipants(r.data.participants || [])).catch(() => message.error('Failed to load participants')).finally(() => setLoading(false));
  }, [cycleId]);

  const columns = [
    { title: 'Name',       render: (_, r) => `${r.first_name} ${r.last_name}` },
    { title: 'Email',      dataIndex: 'email' },
    { title: 'Department', dataIndex: 'department', render: (v) => v || '—' },
    { title: 'Role',       dataIndex: 'role', render: (v) => <Tag>{v.replace('_',' ')}</Tag> },
    { title: 'Actions',    render: (_, r) => <Button size="small" type="primary" icon={<EyeOutlined />} onClick={() => navigate(`/reports/${cycleId}/${r.id}`)}>View Report</Button> },
  ];

  const selectedCycle = cycles.find((c) => String(c.id) === String(cycleId));

  const handleExportAll = async () => {
    if (!cycleId) return;
    setExporting(true);
    try {
      const res = await exportAllReports(cycleId);
      const url  = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href  = url;
      link.setAttribute('download', `360_all_reports_${selectedCycle?.name || cycleId}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      message.error('Failed to export reports');
    } finally {
      setExporting(false);
    }
  };

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card>
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Title level={4} style={{ margin: 0 }}>View Employee Reports</Title>
          <Space>
            {selectedCycle && <Tag color={STATE_COLOR[selectedCycle.state]}>{selectedCycle.state.replace('_',' ')}</Tag>}
            <Select style={{ width: 320 }} placeholder="Select a cycle" value={cycleId || undefined} onChange={setCycleId} showSearch optionFilterProp="children" filterOption={(i, o) => o?.children?.toLowerCase().includes(i.toLowerCase())}>
              {cycles.map((c) => <Option key={c.id} value={String(c.id)}>{c.name}{c.quarter && c.quarter_year ? ` (${c.quarter} ${c.quarter_year})` : ''}</Option>)}
            </Select>
          </Space>
        </Space>
      </Card>

      {!cycleId && <Card><Empty description="Select a cycle to view employee reports" /></Card>}
      {cycleId && (
        <Card
          title={`Participants (${participants.length})`}
          extra={
            <Button
              icon={<FileExcelOutlined />}
              onClick={handleExportAll}
              loading={exporting}
              disabled={participants.length === 0}
            >
              Export All to Excel
            </Button>
          }
        >
          <Table rowKey="id" columns={columns} dataSource={participants} loading={loading} pagination={{ pageSize: 10 }} />
        </Card>
      )}
    </Space>
  );
}
