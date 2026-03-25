import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card, Row, Col, Statistic, Typography, Space, Tag, Table,
  Collapse, Empty, message, Alert, Spin, Button,
} from 'antd';
import { ArrowLeftOutlined, DownloadOutlined } from '@ant-design/icons';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine, LabelList,
} from 'recharts';
import { getEmployeeReport, exportEmployeeReport } from '../../api/reports';
import { getParticipants } from '../../api/cycles';
import useAuthStore from '../../store/authStore';
import usePageTitle from '../../hooks/usePageTitle';
import { formatRatingTableCell } from '../../utils/ratingLabels';

const { Title, Text } = Typography;
const { Panel } = Collapse;

const SCORE_BG = {
  Self: 'linear-gradient(135deg,#3b0764 0%,#581c87 100%)',
  Manager: 'linear-gradient(135deg,#1e3a8a 0%,#1d4ed8 100%)',
  Peer: 'linear-gradient(135deg,#164e63 0%,#0369a1 100%)',
};
const SCORE_GRAD = { Self: 'selfGrad2', Manager: 'managerGrad2', Peer: 'peerGrad2' };
const TYPE_COLOR = { SELF: 'purple', MANAGER: 'blue', PEER: 'cyan', DIRECT_REPORT: 'green' };

const ScoreTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  const bg = SCORE_BG[label] || 'linear-gradient(135deg,#1e1b4b,#312e81)';
  return (
    <div style={{ background: bg, borderRadius: 10, padding: '12px 18px', boxShadow: '0 8px 24px rgba(0,0,0,0.25)', color: '#fff', minWidth: 130 }}>
      <p style={{ margin: 0, fontSize: 12, opacity: 0.75, fontWeight: 500 }}>{label}</p>
      <p style={{ margin: '4px 0 0', fontSize: 22, fontWeight: 700, lineHeight: 1.2 }}>
        {payload[0].value}<span style={{ fontSize: 12, fontWeight: 400, opacity: 0.65 }}> / 5.00</span>
      </p>
    </div>
  );
};

const answerCols = [
  { title: 'Question', dataIndex: 'question_text', width: '50%' },
  {
    title: 'Rating',
    dataIndex: 'rating_value',
    render: (v) => {
      const text = formatRatingTableCell(v);
      return text != null ? <Tag color="blue">{text}</Tag> : '—';
    },
  },
  { title: 'Response', dataIndex: 'text_value',   render: (v) => v || '—' },
];

export default function EmployeeReportPage() {
  usePageTitle('Employee Report');
  const { cycleId, employeeId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuthStore();

  const [report,    setReport]    = useState(null);
  const [empName,   setEmpName]   = useState('');
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState(null);
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    setExporting(true);
    try {
      const res = await exportEmployeeReport(cycleId, employeeId);
      const url = URL.createObjectURL(res.data);
      Object.assign(document.createElement('a'), { href: url, download: `report-${cycleId}-${employeeId}.xlsx` }).click();
      URL.revokeObjectURL(url);
    } catch { message.error('Export failed'); }
    finally { setExporting(false); }
  };

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([getEmployeeReport(cycleId, employeeId), getParticipants(cycleId)])
      .then(([repRes, parRes]) => {
        setReport(repRes.data.report);
        const p = parRes.data.participants.find((p) => String(p.id) === String(employeeId));
        if (p) setEmpName(`${p.first_name} ${p.last_name}`);
      })
      .catch((err) => {
        const msg = err.response?.data?.message || err.response?.data?.detail;
        setError(msg || 'Failed to load the report. Please try again.');
      })
      .finally(() => setLoading(false));
  }, [cycleId, employeeId]);

  const scoreData = [];
  if (report) {
    if (report.self_score    != null) scoreData.push({ name: 'Self',    score: parseFloat(report.self_score).toFixed(2) });
    if (report.manager_score != null) scoreData.push({ name: 'Manager', score: parseFloat(report.manager_score).toFixed(2) });
    if (report.peer_score    != null) scoreData.push({ name: 'Peer',    score: parseFloat(report.peer_score).toFixed(2) });
  }

  const sectionsByType = {};
  for (const sec of report?.sections || []) {
    if (!sectionsByType[sec.reviewer_type]) sectionsByType[sec.reviewer_type] = [];
    sectionsByType[sec.reviewer_type].push(sec);
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card>
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Space>
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>Back</Button>
            <Title level={4} style={{ margin: 0 }}>360 Report{empName ? ` — ${empName}` : ''}</Title>
          </Space>
          {['SUPER_ADMIN','HR_ADMIN'].includes(user?.role) && (
            <Button icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>Export Excel</Button>
          )}
        </Space>
      </Card>

      {loading && <Spin style={{ display: 'block', marginTop: 60 }} />}
      {!loading && error && <Card><Alert type="error" message="Report Unavailable" description={error} showIcon /></Card>}
      {!loading && !error && !report && <Card><Alert type="info" message="Report Unavailable" description="Results may not have been released yet, or this employee is not a participant in this cycle." /></Card>}

      {!loading && !error && report && (
        <>
          <Row gutter={16}>
            <Col span={6}><Card><Statistic title="Overall Score" value={report.overall_score != null ? parseFloat(report.overall_score).toFixed(2) : '—'} /></Card></Col>
            <Col span={6}><Card><Statistic title="Self Score"    value={report.self_score    != null ? parseFloat(report.self_score).toFixed(2)    : '—'} /></Card></Col>
            <Col span={6}><Card><Statistic title="Manager Score" value={report.manager_score != null ? parseFloat(report.manager_score).toFixed(2) : '—'} /></Card></Col>
            <Col span={6}><Card><Statistic title="Peer Score"    value={report.peer_score    != null ? parseFloat(report.peer_score).toFixed(2)    : '—'} /></Card></Col>
          </Row>

          {scoreData.length > 0 && (
            <Card title="Score by Reviewer Type" style={{ borderRadius: 12 }} styles={{ body: { background: '#f8fafc', borderRadius: '0 0 12px 12px', padding: '24px 16px 16px' } }}>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={scoreData} margin={{ top: 32, right: 100, left: 0, bottom: 10 }} barSize={72}>
                  <defs>
                    <linearGradient id="selfGrad2"    x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#a78bfa" /><stop offset="100%" stopColor="#7c3aed" /></linearGradient>
                    <linearGradient id="managerGrad2" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#60a5fa" /><stop offset="100%" stopColor="#2563eb" /></linearGradient>
                    <linearGradient id="peerGrad2"    x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#38bdf8" /><stop offset="100%" stopColor="#0891b2" /></linearGradient>
                  </defs>
                  <CartesianGrid stroke="#e2e8f0" strokeDasharray="4 4" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 13, fill: '#374151', fontWeight: 600 }} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 5]} tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} tickFormatter={(v) => v.toFixed(1)} width={36} />
                  <Tooltip content={<ScoreTooltip />} cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
                  <ReferenceLine y={3} stroke="#cbd5e1" strokeDasharray="5 4" label={{ value: 'Mid (3.0)', position: 'insideTopRight', fontSize: 11, fill: '#94a3b8' }} />
                  {report.overall_score != null && (
                    <ReferenceLine y={parseFloat(report.overall_score).toFixed(2)} stroke="#f59e0b" strokeDasharray="5 4"
                      label={{ value: `Overall ${parseFloat(report.overall_score).toFixed(2)}`, position: 'insideTopRight', fontSize: 11, fill: '#d97706' }} />
                  )}
                  <Bar dataKey="score" name="Score" radius={[8, 8, 0, 0]}>
                    <LabelList dataKey="score" position="top" style={{ fontSize: 14, fontWeight: 700, fill: '#1e293b' }} />
                    {scoreData.map((d, i) => <Cell key={i} fill={`url(#${SCORE_GRAD[d.name] || 'selfGrad2'})`} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Card>
          )}

          <Card title="Feedback Details">
            {Object.keys(sectionsByType).length === 0 ? <Empty description="No detailed feedback available" /> : (
              <Collapse accordion>
                {Object.entries(sectionsByType).map(([rType, typeSections]) => (
                  <Panel key={rType} header={<Space><Tag color={TYPE_COLOR[rType]||'default'}>{rType}</Tag><Text type="secondary">{typeSections.filter((s) => !s.hidden).length} response(s)</Text></Space>}>
                    {typeSections.map((sec, i) =>
                      sec.hidden ? (
                        <Alert key={i} type="warning" message={`${rType} feedback hidden — below threshold`} style={{ marginBottom: 8 }} />
                      ) : (
                        <Card key={i} size="small" style={{ marginBottom: 12 }} title={sec.identity ? `${sec.identity.first_name} ${sec.identity.last_name}` : 'Anonymous'}>
                          <Table rowKey="question_id" size="small" pagination={false} dataSource={sec.answers || []} columns={answerCols} />
                        </Card>
                      )
                    )}
                  </Panel>
                ))}
              </Collapse>
            )}
          </Card>
        </>
      )}
    </Space>
  );
}
