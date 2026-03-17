import { useEffect, useState, useCallback } from 'react';
import {
  Card, Select, Row, Col, Statistic, Typography, Space, Tag, Table,
  Collapse, Empty, message, Alert, Skeleton,
} from 'antd';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine, LabelList,
} from 'recharts';
import { TrophyOutlined } from '@ant-design/icons';
import { getMyCycles } from '../../api/cycles';
import usePageTitle from '../../hooks/usePageTitle';
import { getMyReport } from '../../api/reports';
import ErrorCard from '../../components/shared/ErrorCard';
import { formatRatingTableCell } from '../../utils/ratingLabels';

const { Title, Text } = Typography;
const { Option } = Select;
const { Panel } = Collapse;

const SCORE_BG = {
  Self: 'linear-gradient(135deg,#3b0764 0%,#581c87 100%)',
  Manager: 'linear-gradient(135deg,#1e3a8a 0%,#1d4ed8 100%)',
  Peer: 'linear-gradient(135deg,#164e63 0%,#0369a1 100%)',
  'Direct Report': 'linear-gradient(135deg,#064e3b 0%,#047857 100%)',
};
const SCORE_GRAD = { Self: 'selfGrad', Manager: 'managerGrad', Peer: 'peerGrad', 'Direct Report': 'drGrad' };
const TYPE_COLOR = { SELF: 'purple', MANAGER: 'blue', PEER: 'cyan', DIRECT_REPORT: 'green' };

const ScoreTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  const bg = SCORE_BG[label] || 'linear-gradient(135deg,#1e1b4b,#312e81)';
  return (
    <div style={{ background: bg, borderRadius: 10, padding: '12px 18px', boxShadow: '0 8px 24px rgba(0,0,0,0.25)', color: '#fff', minWidth: 130 }}>
      <p style={{ margin: 0, fontSize: 12, opacity: 0.75, fontWeight: 500 }}>{label}</p>
      <p style={{ margin: '4px 0 0', fontSize: 22, fontWeight: 700, lineHeight: 1.2 }}>{payload[0].value}<span style={{ fontSize: 12, fontWeight: 400, opacity: 0.65 }}> / 5.00</span></p>
    </div>
  );
};

export default function MyReportPage() {
  usePageTitle('My Report');
  const [cycles,      setCycles]      = useState([]);
  const [cycleId,     setCycleId]     = useState('');
  const [report,      setReport]      = useState(null);
  const [loading,     setLoading]     = useState(false);
  const [cyclesError, setCyclesError] = useState(false);
  const [reportError, setReportError] = useState(false);

  const loadCycles = useCallback(() => {
    setCyclesError(false);
    getMyCycles().then((r) => {
      const released = (r.data.cycles || []).filter((c) => ['RESULTS_RELEASED','ARCHIVED'].includes(c.state));
      setCycles(released);
      if (released.length > 0) setCycleId(String(released[0].id));
    }).catch(() => setCyclesError(true));
  }, []);

  const loadReport = useCallback(() => {
    if (!cycleId) return;
    setLoading(true);
    setReportError(false);
    getMyReport(cycleId).then((r) => setReport(r.data.report))
      .catch((err) => {
        const msg = err.response?.data?.message || err.response?.data?.detail;
        if (msg) message.warning(msg);
        setReport(null);
        setReportError(true);
      }).finally(() => setLoading(false));
  }, [cycleId]);

  useEffect(() => { loadCycles(); }, [loadCycles]);
  useEffect(() => { loadReport(); }, [loadReport]);

  if (cyclesError) return <ErrorCard message="Could not load your cycles. Please try again." onRetry={loadCycles} />;

  if (cycles.length === 0 && !loading) {
    return (
      <Card style={{ textAlign: 'center', padding: '40px 0' }}>
        <Empty image={<TrophyOutlined style={{ fontSize: 52, color: '#cbd5e1' }} />} imageStyle={{ height: 60 }}
          description={<Space direction="vertical" size={2}><Text strong>No results released yet</Text><Text type="secondary">Your 360 report will appear here once HR releases the results for a cycle you participated in.</Text></Space>} />
      </Card>
    );
  }

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
    { title: 'Response', dataIndex: 'text_value',     render: (v) => v || '—' },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card>
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Title level={4} style={{ margin: 0 }}>My 360 Report</Title>
          <Select style={{ width: 320 }} placeholder="Search or select a cycle…" value={cycleId || undefined} onChange={(v) => setCycleId(v)} loading={loading} showSearch optionFilterProp="children" filterOption={(input, option) => option?.children?.toLowerCase().includes(input.toLowerCase())}>
            {cycles.map((c) => <Option key={c.id} value={String(c.id)}>{c.name}</Option>)}
          </Select>
        </Space>
      </Card>

      {loading && <Card><Skeleton active paragraph={{ rows: 6 }} /></Card>}

      {!loading && reportError && <ErrorCard message="Could not load your report. Please try again." onRetry={loadReport} />}

      {!loading && !reportError && !report && cycleId && (
        <Card>
          <Alert type="info" message="Report Unavailable" description="Your report is not available yet. Results may not have been released, or you are not a participant." showIcon />
        </Card>
      )}

      {report && !loading && !reportError && (
        <>
          <Row gutter={16}>
            {[
              { title: 'Overall Score', val: report.overall_score },
              { title: 'Self Score',    val: report.self_score },
              { title: 'Manager Score', val: report.manager_score },
              { title: 'Peer Score',    val: report.peer_score },
            ].map(({ title, val }) => (
              <Col span={6} key={title}>
                <Card><Statistic title={title} value={val != null ? parseFloat(val).toFixed(2) : '—'} /></Card>
              </Col>
            ))}
          </Row>

          {report.sections?.some((s) => s.hidden) && (
            <Alert type="warning" showIcon message="Peer Feedback Hidden" description="Peer responses are not shown because fewer than 3 peers submitted (privacy threshold)." />
          )}

          {scoreData.length > 0 && (
            <Card title="Score by Reviewer Type" style={{ borderRadius: 12 }} styles={{ body: { background: '#f8fafc', borderRadius: '0 0 12px 12px', padding: '24px 16px 16px' } }}>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={scoreData} margin={{ top: 32, right: 100, left: 0, bottom: 10 }} barSize={72}>
                  <defs>
                    <linearGradient id="selfGrad"    x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#a78bfa" /><stop offset="100%" stopColor="#7c3aed" stopOpacity={0.9} /></linearGradient>
                    <linearGradient id="managerGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#60a5fa" /><stop offset="100%" stopColor="#2563eb" stopOpacity={0.9} /></linearGradient>
                    <linearGradient id="peerGrad"    x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#38bdf8" /><stop offset="100%" stopColor="#0891b2" stopOpacity={0.9} /></linearGradient>
                    <linearGradient id="drGrad"      x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#34d399" /><stop offset="100%" stopColor="#059669" stopOpacity={0.9} /></linearGradient>
                  </defs>
                  <CartesianGrid stroke="#e2e8f0" strokeDasharray="4 4" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 13, fill: '#374151', fontWeight: 600 }} axisLine={false} tickLine={false} />
                  <YAxis domain={[0,5]} tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} tickFormatter={(v) => v.toFixed(1)} width={36} />
                  <Tooltip content={<ScoreTooltip />} cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
                  <ReferenceLine y={3} stroke="#cbd5e1" strokeDasharray="5 4" label={{ value: 'Mid (3.0)', position: 'insideTopRight', fontSize: 11, fill: '#94a3b8' }} />
                  {report.overall_score != null && (
                    <ReferenceLine y={parseFloat(report.overall_score).toFixed(2)} stroke="#f59e0b" strokeDasharray="5 4" label={{ value: `Overall ${parseFloat(report.overall_score).toFixed(2)}`, position: 'insideTopRight', fontSize: 11, fill: '#d97706' }} />
                  )}
                  <Bar dataKey="score" name="Score" radius={[8,8,0,0]}>
                    <LabelList dataKey="score" position="top" style={{ fontSize: 14, fontWeight: 700, fill: '#1e293b' }} />
                    {scoreData.map((d, i) => <Cell key={i} fill={`url(#${SCORE_GRAD[d.name] || 'selfGrad'})`} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Card>
          )}

          <Card title="Feedback Details">
            {Object.keys(sectionsByType).length === 0 ? (
              <Empty description="No detailed feedback available yet" />
            ) : (
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
