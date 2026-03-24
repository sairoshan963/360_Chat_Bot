import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Select, Button, Space, Typography, Table, Tag, message, Empty } from 'antd';
import { EyeOutlined, FileExcelOutlined } from '@ant-design/icons';
import { listCycles, getParticipants } from '../../api/cycles';
import usePageTitle from '../../hooks/usePageTitle';
import API from '../../api/client';

const { Title } = Typography;
const { Option } = Select;

const STATE_COLOR = { RESULTS_RELEASED: 'purple', ARCHIVED: 'red' };

export default function ViewReportsPage() {
  usePageTitle('View Reports');
  const navigate = useNavigate();
  const [cycles,        setCycles]       = useState([]);
  const [cycleId,       setCycleId]      = useState('');
  const [participants,  setParticipants] = useState([]);
  const [loading,       setLoading]      = useState(false);
  const [exporting,     setExporting]    = useState(false);

  const handleExportAll = async () => {
    if (!cycleId) return;
    setExporting(true);
    try {
      const res = await API.get(`/feedback/cycles/${cycleId}/reports/export-all/`, { responseType: 'blob' });
      const url  = URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      const cd   = res.headers['content-disposition'] || '';
      const match = cd.match(/filename="([^"]+)"/);
      link.href     = url;
      link.download = match ? match[1] : `360_all_reports_${cycleId}.xlsx`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      message.error('Failed to export reports');
    } finally { setExporting(false); }
  };

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
            {cycleId && (
              <Button icon={<FileExcelOutlined />} loading={exporting} onClick={handleExportAll} style={{ background: '#217346', borderColor: '#217346', color: '#fff' }}>
                Export All to Excel
              </Button>
            )}
          </Space>
        </Space>
      </Card>

      {!cycleId && <Card><Empty description="Select a cycle to view employee reports" /></Card>}
      {cycleId && (
        <Card title={`Participants (${participants.length})`}>
          <Table rowKey="id" columns={columns} dataSource={participants} loading={loading} pagination={{ pageSize: 10 }} />
        </Card>
      )}
    </Space>
  );
}
