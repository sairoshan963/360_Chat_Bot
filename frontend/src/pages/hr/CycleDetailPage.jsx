import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card, Descriptions, Tag, Button, Space, Typography, Table,
  Progress, Statistic, Row, Col, message, Popconfirm, Steps, Modal, Input,
  Form, InputNumber, Tooltip, Select, DatePicker, Transfer,
} from 'antd';
import { EyeOutlined, LockOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import {
  getCycle, getCycleProgress, getParticipants,
  activateCycle, finalizeCycle, closeCycle, releaseCycle, archiveCycle, overrideCycle,
  getAllNominations, updateCycle, approveNomination, rejectNomination,
  getParticipantStatus, downloadParticipantExcel, getNominationStatus, downloadNominationExcel,
  addParticipants, removeParticipant,
} from '../../api/cycles';
import { listUsers } from '../../api/users';
import useAuthStore from '../../store/authStore';
import usePageTitle from '../../hooks/usePageTitle';

const { Title } = Typography;

const STATE_COLOR = {
  DRAFT:'default', NOMINATION:'processing', FINALIZED:'blue',
  ACTIVE:'green', CLOSED:'orange', RESULTS_RELEASED:'purple', ARCHIVED:'red',
};

const STATE_STEP_WITH_NOMINATION    = { DRAFT:0, NOMINATION:1, FINALIZED:2, ACTIVE:3, CLOSED:4, RESULTS_RELEASED:5, ARCHIVED:6 };
const STATE_STEP_WITHOUT_NOMINATION = { DRAFT:0, FINALIZED:1, ACTIVE:2, CLOSED:3, RESULTS_RELEASED:4, ARCHIVED:5 };

export default function CycleDetailPage() {
  usePageTitle('Cycle Details');
  const { id }   = useParams();
  const navigate = useNavigate();
  const user     = useAuthStore((s) => s.user);

  const [cycle,             setCycle]             = useState(null);
  const [progress,          setProgress]          = useState([]);
  const [participants,      setParticipants]      = useState([]);
  const [participantStatus, setParticipantStatus] = useState([]);
  const [nominationStatus,  setNominationStatus]  = useState([]);
  const [nominations,       setNominations]       = useState([]);
  const [loading,           setLoading]           = useState(false);
  const [downloading,       setDownloading]       = useState({ pending: false, done: false });
  const [downloadingNom,    setDownloadingNom]    = useState(false);
  const [overrideModal,     setOverrideModal]     = useState(false);
  const [overrideReason,    setOverrideReason]    = useState('');
  const [overrideState,     setOverrideState]     = useState('');
  const [editModal,         setEditModal]         = useState(false);
  const [participantSearch, setParticipantSearch] = useState('');
  const [statusSearch,      setStatusSearch]      = useState('');
  const [editForm]          = Form.useForm();
  const [nomActionLoading,  setNomActionLoading]  = useState({});
  const [rejectNote,        setRejectNote]        = useState({});
  const [addParticipantModal, setAddParticipantModal] = useState(false);
  const [allUsers,            setAllUsers]            = useState([]);
  const [selectedUserIds,     setSelectedUserIds]     = useState([]);
  const [userSearch,          setUserSearch]          = useState('');
  const [addingParticipants,  setAddingParticipants]  = useState(false);

  const handleNomApprove = async (nom) => {
    setNomActionLoading((p) => ({ ...p, [nom.id]: 'approve' }));
    try {
      await approveNomination(nom.cycle_id, nom.id);
      message.success('Nomination approved');
      setNominations((prev) => prev.map((n) => n.id === nom.id ? { ...n, status: 'APPROVED' } : n));
    } catch (err) {
      message.error(err.response?.data?.message || 'Failed to approve');
    } finally {
      setNomActionLoading((p) => ({ ...p, [nom.id]: null }));
    }
  };

  const handleNomReject = async (nom) => {
    setNomActionLoading((p) => ({ ...p, [nom.id]: 'reject' }));
    try {
      await rejectNomination(nom.cycle_id, nom.id, rejectNote[nom.id] || '');
      message.success('Nomination rejected');
      setNominations((prev) => prev.map((n) => n.id === nom.id ? { ...n, status: 'REJECTED' } : n));
    } catch (err) {
      message.error(err.response?.data?.message || 'Failed to reject');
    } finally {
      setNomActionLoading((p) => ({ ...p, [nom.id]: null }));
    }
  };

  const openAddParticipantModal = async () => {
    try {
      const res = await listUsers({ status: 'ACTIVE', page_size: 500 });
      const existingIds = new Set(participants.map((p) => p.id));
      setAllUsers((res.data.users || res.data.results || []).filter((u) => !existingIds.has(u.id)));
    } catch {
      message.error('Could not load employees');
      return;
    }
    setSelectedUserIds([]);
    setUserSearch('');
    setAddParticipantModal(true);
  };

  const handleAddParticipants = async () => {
    if (!selectedUserIds.length) return;
    setAddingParticipants(true);
    try {
      await addParticipants(id, selectedUserIds);
      message.success(`${selectedUserIds.length} participant(s) added`);
      setAddParticipantModal(false);
      const res = await getParticipants(id);
      setParticipants(res.data.participants || []);
    } catch (err) {
      message.error(err.response?.data?.message || 'Failed to add participants');
    } finally {
      setAddingParticipants(false);
    }
  };

  const load = async () => {
    setLoading(true);
    try {
      const [cRes, pRes, parRes] = await Promise.all([
        getCycle(id), getCycleProgress(id), getParticipants(id),
      ]);
      const cycleData = cRes.data.cycle;
      setCycle(cycleData);
      setProgress(pRes.data.progress || []);
      setParticipants(parRes.data.participants || []);

      if (['SUPER_ADMIN', 'HR_ADMIN'].includes(user?.role) &&
          cycleData.peer_enabled && cycleData.state === 'NOMINATION') {
        try {
          const r = await getNominationStatus(id);
          setNominationStatus(r.data.participants || []);
        } catch { /* silently ignore */ }
      } else {
        setNominationStatus([]);
      }

      if (['SUPER_ADMIN', 'HR_ADMIN'].includes(user?.role) &&
          !['DRAFT', 'NOMINATION', 'FINALIZED'].includes(cycleData.state)) {
        try {
          const r = await getParticipantStatus(id);
          setParticipantStatus(r.data.participants || []);
        } catch { /* silently ignore */ }
      }

      if (['SUPER_ADMIN', 'HR_ADMIN'].includes(user?.role)) {
        const NOMINATION_STATES = ['NOMINATION', 'FINALIZED', 'ACTIVE', 'CLOSED', 'RESULTS_RELEASED', 'ARCHIVED'];
        if (NOMINATION_STATES.includes(cycleData.state)) {
          try {
            const r = await getAllNominations(id);
            setNominations(r.data.nominations || []);
          } catch { /* silently ignore */ }
        }
      }
    } catch { message.error('Failed to load cycle'); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [id]);

  const transition = async (fn, label) => {
    try { await fn(id); message.success(`${label} successful`); load(); }
    catch (err) { message.error(err.response?.data?.message || `${label} failed`); }
  };

  const handleOverride = async () => {
    if (!overrideReason.trim()) { message.error('Reason required'); return; }
    try {
      await overrideCycle(id, { target_state: overrideState, reason: overrideReason });
      message.success('Override applied');
      setOverrideModal(false);
      load();
    } catch (err) { message.error(err.response?.data?.message || 'Override failed'); }
  };

  const openEditModal = () => {
    editForm.setFieldsValue({
      name:                cycle.name,
      review_deadline:     cycle.review_deadline ? dayjs(cycle.review_deadline) : null,
      nomination_deadline: cycle.nomination_deadline ? dayjs(cycle.nomination_deadline) : null,
      peer_min_count:      cycle.peer_min_count,
      peer_max_count:      cycle.peer_max_count,
      peer_threshold:      cycle.peer_threshold ?? 3,
      quarter:             cycle.quarter || undefined,
      quarter_year:        cycle.quarter_year || undefined,
    });
    setEditModal(true);
  };

  const handleEditSave = async () => {
    try {
      const values = await editForm.validateFields();
      if (values.review_deadline)     values.review_deadline     = values.review_deadline.toISOString();
      if (values.nomination_deadline) values.nomination_deadline = values.nomination_deadline.toISOString();
      else delete values.nomination_deadline;
      await updateCycle(id, values);
      message.success('Cycle updated');
      setEditModal(false);
      load();
    } catch (err) {
      if (err?.errorFields) return;
      message.error(err.response?.data?.message || 'Update failed');
    }
  };

  const handleDownloadNominations = async () => {
    setDownloadingNom(true);
    try {
      const res = await downloadNominationExcel(id);
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a   = document.createElement('a');
      a.href     = url;
      a.download = `nominations-${cycle.name.replace(/\s+/g, '_')}.xlsx`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch { message.error('Failed to download'); }
    finally { setDownloadingNom(false); }
  };

  const handleDownload = async (type) => {
    setDownloading((d) => ({ ...d, [type]: true }));
    try {
      const res   = await downloadParticipantExcel(id, type);
      const label = type === 'done' ? 'completed' : 'pending';
      const url   = window.URL.createObjectURL(new Blob([res.data]));
      const a     = document.createElement('a');
      a.href     = url;
      a.download = `${label}-${cycle.name.replace(/\s+/g, '_')}.xlsx`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch { message.error('Failed to download'); }
    finally { setDownloading((d) => ({ ...d, [type]: false })); }
  };

  if (!cycle) return null;

  const totalTasks     = progress.reduce((s, r) => s + parseInt(r.total,     10), 0);
  const submittedTasks = progress.reduce((s, r) => s + parseInt(r.submitted, 10) + parseInt(r.locked, 10), 0);
  const pct            = totalTasks ? Math.round((submittedTasks / totalTasks) * 100) : 0;

  const progressCols = [
    { title: 'Reviewer Type', dataIndex: 'reviewer_type' },
    { title: 'Total',     dataIndex: 'total',     width: 80 },
    { title: 'Submitted', dataIndex: 'submitted', width: 90,
      render: (v) => <Tag color={parseInt(v,10) > 0 ? 'success' : 'default'}>{v}</Tag> },
    { title: 'Locked',    dataIndex: 'locked',    width: 80,
      render: (v) => <Tag color={parseInt(v,10) > 0 ? 'warning' : 'default'}>{v}</Tag> },
    { title: 'Pending',   width: 80,
      render: (_, r) => {
        const p = parseInt(r.total,10) - parseInt(r.submitted,10) - parseInt(r.locked,10);
        return <Tag color={p > 0 ? 'error' : 'default'}>{p}</Tag>;
      }},
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      {/* Header */}
      <Card loading={loading}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <div>
            <Title level={4} style={{ margin: 0 }}>{cycle.name}</Title>
            <Tag color={STATE_COLOR[cycle.state]} style={{ marginTop: 4 }}>
              {cycle.state.replace('_', ' ')}
            </Tag>
          </div>
          <Space wrap>
            {cycle.state === 'DRAFT' && (
              <Button onClick={openEditModal}>Edit</Button>
            )}
            {cycle.state === 'DRAFT' && (
              <Popconfirm title="Activate this cycle?" onConfirm={() => transition(activateCycle, 'Activate')}>
                <Button type="primary">Activate</Button>
              </Popconfirm>
            )}
            {cycle.state === 'NOMINATION' && (() => {
              const hasPending = nominations.some((n) => n.status === 'PENDING');
              return hasPending ? (
                <Tooltip title="All pending nominations must be approved or rejected before the cycle can be finalized">
                  <Button type="primary" disabled>Finalize</Button>
                </Tooltip>
              ) : (
                <Popconfirm title="Finalize and start collecting feedback?" onConfirm={() => transition(finalizeCycle, 'Finalize')}>
                  <Button type="primary">Finalize</Button>
                </Popconfirm>
              );
            })()}
            {cycle.state === 'ACTIVE' && (
              <Popconfirm
                title="Close this cycle? All pending tasks will be locked and no further submissions accepted."
                onConfirm={() => transition(closeCycle, 'Close')}
              >
                <Button danger>Close Cycle</Button>
              </Popconfirm>
            )}
            {cycle.state === 'CLOSED' && (
              <Popconfirm title="Release results to participants?" onConfirm={() => transition(releaseCycle, 'Release')}>
                <Button type="primary">Release Results</Button>
              </Popconfirm>
            )}
            {cycle.state === 'RESULTS_RELEASED' && (
              <Popconfirm title="Archive this cycle?" onConfirm={() => transition(archiveCycle, 'Archive')}>
                <Button>Archive</Button>
              </Popconfirm>
            )}
            {user?.role === 'SUPER_ADMIN' && (
              <Button danger onClick={() => setOverrideModal(true)}>Override State</Button>
            )}
          </Space>
        </Space>

        {(() => {
          const hasPeer    = cycle.peer_enabled;
          const stepMap    = hasPeer ? STATE_STEP_WITH_NOMINATION : STATE_STEP_WITHOUT_NOMINATION;
          const stepLabels = hasPeer
            ? ['DRAFT', 'NOMINATION', 'FINALIZED', 'ACTIVE', 'CLOSED', 'RELEASED', 'ARCHIVED']
            : ['DRAFT', 'FINALIZED', 'ACTIVE', 'CLOSED', 'RELEASED', 'ARCHIVED'];
          return (
            <Steps
              current={stepMap[cycle.state] ?? 0}
              size="small"
              style={{ marginTop: 24 }}
              items={stepLabels.map((s) => ({ title: s }))}
            />
          );
        })()}
      </Card>

      {/* Stats */}
      <Row gutter={16}>
        <Col span={6}>
          <Card><Statistic title="Participants" value={participants.length} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="Total Tasks" value={totalTasks} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="Submitted" value={submittedTasks} /></Card>
        </Col>
        <Col span={6}>
          <Card>
            <div style={{ textAlign: 'center' }}>
              <div style={{ color: '#666', marginBottom: 4 }}>Completion</div>
              <Progress type="circle" percent={pct} size={80} />
            </div>
          </Card>
        </Col>
      </Row>

      {/* Cycle details */}
      <Card title="Cycle Details">
        <Descriptions column={2} size="small">
          {cycle.quarter && cycle.quarter_year && (
            <Descriptions.Item label="Quarter">
              <Tag color="blue">{cycle.quarter} {cycle.quarter_year}</Tag>
            </Descriptions.Item>
          )}
          <Descriptions.Item label="Template">{cycle.template_name}</Descriptions.Item>
          <Descriptions.Item label="Peer Enabled">{cycle.peer_enabled ? 'Yes' : 'No'}</Descriptions.Item>
          {cycle.peer_enabled && <>
            <Descriptions.Item label="Peer Min">{cycle.peer_min_count}</Descriptions.Item>
            <Descriptions.Item label="Peer Max">{cycle.peer_max_count}</Descriptions.Item>
            <Descriptions.Item label="Peer Anonymity">
              <Tag>{cycle.peer_anonymity}</Tag>
            </Descriptions.Item>
          </>}
          <Descriptions.Item label="Manager Anonymity">
            <Tag>{cycle.manager_anonymity}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Self Anonymity">
            <Tag>{cycle.self_anonymity}</Tag>
          </Descriptions.Item>
          {cycle.nomination_deadline && (
            <Descriptions.Item label="Nomination Deadline">
              {new Date(cycle.nomination_deadline).toLocaleString()}
            </Descriptions.Item>
          )}
          <Descriptions.Item label="Review Deadline">
            {new Date(cycle.review_deadline).toLocaleString()}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* Progress by type */}
      {progress.length > 0 && (
        <Card title="Submission Progress by Reviewer Type">
          <Table rowKey="reviewer_type" columns={progressCols} dataSource={progress} pagination={false} size="small" />
        </Card>
      )}

      {/* Nomination status — HR/Super Admin only, visible during NOMINATION state */}
      {nominationStatus.length > 0 && (() => {
        const notStarted = nominationStatus.filter((p) => p.status === 'NOT_STARTED').length;
        const incomplete = nominationStatus.filter((p) => p.status === 'INCOMPLETE').length;
        const done       = nominationStatus.filter((p) => p.status === 'DONE').length;
        return (
          <Card
            title="Nomination Status by Person"
            extra={
              <Space>
                <Tag color="success">{done} Done</Tag>
                {incomplete > 0 && <Tag color="warning">{incomplete} Incomplete</Tag>}
                {notStarted > 0 && <Tag color="error">{notStarted} Not Started</Tag>}
                <Button loading={downloadingNom} onClick={handleDownloadNominations}>
                  Download Excel
                </Button>
              </Space>
            }
          >
            {notStarted > 0 && (
              <div style={{ marginBottom: 12, padding: '8px 12px', background: '#fff2f0', borderRadius: 6, border: '1px solid #ffccc7' }}>
                <strong style={{ color: '#cf1322' }}>
                  {notStarted} participant{notStarted > 1 ? 's have' : ' has'} not nominated any peers yet.
                </strong>
                <span style={{ color: '#666', marginLeft: 6 }}>
                  Finalization is blocked until all participants meet the minimum.
                </span>
              </div>
            )}
            <Table
              rowKey="user_id"
              size="small"
              pagination={{ pageSize: 15 }}
              dataSource={nominationStatus}
              columns={[
                {
                  title: 'Name',
                  render: (_, r) => `${r.first_name} ${r.last_name}`,
                  sorter: (a, b) => `${a.last_name}${a.first_name}`.localeCompare(`${b.last_name}${b.first_name}`),
                },
                { title: 'Email',     dataIndex: 'email' },
                { title: 'Dept',      dataIndex: 'department', render: (v) => v || '—' },
                { title: 'Nominated', dataIndex: 'nominated',  width: 90,
                  render: (v, r) => `${v} / ${r.min_required}` },
                { title: 'Approved',  dataIndex: 'approved',   width: 85,
                  render: (v) => <Tag color={parseInt(v,10) > 0 ? 'success' : 'default'}>{v}</Tag> },
                { title: 'Pending',   dataIndex: 'pending',    width: 80,
                  render: (v) => <Tag color={parseInt(v,10) > 0 ? 'warning' : 'default'}>{v}</Tag> },
                { title: 'Rejected',  dataIndex: 'rejected',   width: 80,
                  render: (v) => <Tag color={parseInt(v,10) > 0 ? 'error' : 'default'}>{v}</Tag> },
                {
                  title: 'Status',
                  dataIndex: 'status',
                  width: 120,
                  filters: [
                    { text: 'Done',        value: 'DONE' },
                    { text: 'Incomplete',  value: 'INCOMPLETE' },
                    { text: 'Not Started', value: 'NOT_STARTED' },
                  ],
                  onFilter: (value, record) => record.status === value,
                  render: (v) => {
                    if (v === 'DONE')        return <Tag color="success">Done</Tag>;
                    if (v === 'INCOMPLETE')  return <Tag color="warning">Incomplete</Tag>;
                    return <Tag color="error">Not Started</Tag>;
                  },
                },
              ]}
            />
          </Card>
        );
      })()}

      {/* Per-person submission status — HR/Super Admin only, visible once cycle is Active or later */}
      {participantStatus.length > 0 && (() => {
        const hasPending = participantStatus.some((p) => p.overall === 'PENDING');
        const hasDone    = participantStatus.some((p) => p.overall === 'COMPLETED' || p.overall === 'PARTIAL');
        return (
          <Card
            title="Submission Status by Person"
            extra={
              <Space>
                <Button
                  danger
                  loading={downloading.pending}
                  disabled={!hasPending}
                  onClick={() => handleDownload('pending')}
                >
                  Download Pending
                </Button>
                <Button
                  style={{ color: '#52c41a', borderColor: '#52c41a' }}
                  loading={downloading.done}
                  disabled={!hasDone}
                  onClick={() => handleDownload('done')}
                >
                  Download Completed
                </Button>
              </Space>
            }
          >
            <Input.Search
              placeholder="Search by name or email…"
              value={statusSearch}
              onChange={(e) => setStatusSearch(e.target.value)}
              allowClear
              style={{ marginBottom: 12, maxWidth: 320 }}
            />
            <Table
              rowKey="user_id"
              size="small"
              pagination={{ pageSize: 15 }}
              dataSource={participantStatus.filter((p) =>
                !statusSearch.trim() ||
                `${p.first_name} ${p.last_name} ${p.email}`.toLowerCase()
                  .includes(statusSearch.toLowerCase())
              )}
              columns={[
                {
                  title: 'Name',
                  render: (_, r) => `${r.first_name} ${r.last_name}`,
                  sorter: (a, b) => `${a.last_name}${a.first_name}`.localeCompare(`${b.last_name}${b.first_name}`),
                },
                { title: 'Email',     dataIndex: 'email' },
                { title: 'Dept',      dataIndex: 'department', render: (v) => v || '—' },
                { title: 'Tasks',     dataIndex: 'total',      width: 70 },
                { title: 'Submitted', dataIndex: 'submitted',  width: 85,
                  render: (v) => <Tag color={parseInt(v,10) > 0 ? 'success' : 'default'}>{v}</Tag> },
                { title: 'Locked',    dataIndex: 'locked',     width: 75,
                  render: (v) => <Tag color={parseInt(v,10) > 0 ? 'warning' : 'default'}>{v}</Tag> },
                { title: 'Pending',   dataIndex: 'pending',    width: 80,
                  render: (v) => <Tag color={parseInt(v,10) > 0 ? 'error' : 'default'}>{v}</Tag> },
                {
                  title: 'Status',
                  dataIndex: 'overall',
                  width: 130,
                  filters: [
                    { text: 'Completed', value: 'COMPLETED' },
                    { text: 'Partial',   value: 'PARTIAL' },
                    { text: 'Missed',    value: 'MISSED' },
                    { text: 'Pending',   value: 'PENDING' },
                  ],
                  onFilter: (value, record) => record.overall === value,
                  render: (v) => {
                    if (v === 'COMPLETED') return <Tag color="success">Completed</Tag>;
                    if (v === 'PARTIAL')   return <Tag color="warning">Partial</Tag>;
                    if (v === 'MISSED')    return <Tag color="error">Missed</Tag>;
                    if (v === 'PENDING')   return <Tag color="processing">Pending</Tag>;
                    return <Tag color="default">No Tasks</Tag>;
                  },
                },
              ]}
            />
          </Card>
        );
      })()}

      {/* Participants */}
      {(() => {
        const filtered = participantSearch.trim()
          ? participants.filter((p) =>
              `${p.first_name} ${p.last_name} ${p.email}`.toLowerCase()
                .includes(participantSearch.toLowerCase()))
          : participants;
        return (
          <Card
            title={`Participants (${filtered.length}${filtered.length !== participants.length ? ` / ${participants.length}` : ''})`}
            extra={
              cycle.state === 'DRAFT' && (
                <Button type="primary" size="small" onClick={openAddParticipantModal}>
                  + Add Participants
                </Button>
              )
            }
          >
            <Input.Search
              placeholder="Search by name or email…"
              value={participantSearch}
              onChange={(e) => setParticipantSearch(e.target.value)}
              allowClear
              style={{ marginBottom: 12, maxWidth: 320 }}
            />
            <Table
              rowKey="id"
              size="small"
              dataSource={filtered}
              pagination={{ pageSize: 10 }}
              columns={[
                { title: 'Name',  render: (_, r) => `${r.first_name} ${r.last_name}` },
                { title: 'Email', dataIndex: 'email' },
                { title: 'Dept',  dataIndex: 'department', render: (v) => v || '—' },
                {
                  title: 'Report',
                  width: 130,
                  render: (_, r) =>
                    ['RESULTS_RELEASED', 'ARCHIVED'].includes(cycle.state)
                      ? (
                        <Button
                          size="small"
                          type="primary"
                          icon={<EyeOutlined />}
                          onClick={() => navigate(`/reports/${cycle.id}/${r.id}`)}
                        >
                          View
                        </Button>
                      ) : (
                        <Tooltip title="Available once results are released">
                          <Button size="small" icon={<LockOutlined />} disabled>
                            Pending
                          </Button>
                        </Tooltip>
                      ),
                },
                ...(cycle.state === 'DRAFT' ? [{
                  title: '',
                  width: 80,
                  render: (_, r) => (
                    <Popconfirm
                      title="Remove this participant?"
                      okText="Remove"
                      okButtonProps={{ danger: true }}
                      onConfirm={async () => {
                        try {
                          await removeParticipant(id, r.id);
                          message.success(`${r.first_name} ${r.last_name} removed`);
                          setParticipants((prev) => prev.filter((p) => p.id !== r.id));
                        } catch (err) {
                          message.error(err.response?.data?.message || 'Failed to remove');
                        }
                      }}
                    >
                      <Button size="small" danger>Remove</Button>
                    </Popconfirm>
                  ),
                }] : []),
              ]}
            />
          </Card>
        );
      })()}

      {/* Nominations — HR/Super Admin, shown from NOMINATION state onward */}
      {nominations.length > 0 && (() => {
        const pending  = nominations.filter((n) => n.status === 'PENDING');
        const resolved = nominations.filter((n) => n.status !== 'PENDING');
        return (
          <>
            {pending.length > 0 && (
              user?.role === 'SUPER_ADMIN' ? (
                <Card
                  title={`Escalated Nominations — Awaiting Your Approval (${pending.length})`}
                  headStyle={{ background: '#fffbe6', borderBottom: '1px solid #ffe58f' }}
                >
                  <p style={{ color: '#8c6914', marginBottom: 12 }}>
                    These nominations were not acted on by the direct manager. Please approve or reject them before the cycle can be finalized.
                  </p>
                  <Table
                    rowKey="id"
                    size="small"
                    pagination={false}
                    dataSource={pending}
                    columns={[
                      { title: 'Reviewee',       render: (_, r) => `${r.reviewee_first} ${r.reviewee_last}` },
                      { title: 'Nominated Peer', render: (_, r) => `${r.peer_first} ${r.peer_last}` },
                      {
                        title: 'Action',
                        render: (_, r) => (
                          <Space size="small">
                            <Button
                              type="primary" size="small"
                              loading={nomActionLoading[r.id] === 'approve'}
                              onClick={() => handleNomApprove(r)}
                            >Approve</Button>
                            <Popconfirm
                              title="Reject this nomination?"
                              description={
                                <Input.TextArea
                                  placeholder="Optional reason"
                                  rows={2}
                                  value={rejectNote[r.id] || ''}
                                  onChange={(e) => setRejectNote((prev) => ({ ...prev, [r.id]: e.target.value }))}
                                />
                              }
                              onConfirm={() => handleNomReject(r)}
                              okText="Reject"
                              okButtonProps={{ danger: true, loading: nomActionLoading[r.id] === 'reject' }}
                            >
                              <Button size="small" danger>Reject</Button>
                            </Popconfirm>
                          </Space>
                        ),
                      },
                    ]}
                  />
                </Card>
              ) : (
                <Card
                  title={`Pending Nominations — Action Required (${pending.length})`}
                  headStyle={{ background: '#fff2f0', borderBottom: '1px solid #ffccc7' }}
                >
                  <p style={{ color: '#cf1322', marginBottom: 12 }}>
                    {pending.length} nomination(s) are awaiting approval by the Super Admin. The cycle cannot be finalized until all nominations are resolved.
                  </p>
                  <Table
                    rowKey="id"
                    size="small"
                    pagination={false}
                    dataSource={pending}
                    columns={[
                      { title: 'Reviewee',       render: (_, r) => `${r.reviewee_first} ${r.reviewee_last}` },
                      { title: 'Nominated Peer', render: (_, r) => `${r.peer_first} ${r.peer_last}` },
                      { title: 'Status',         dataIndex: 'status', render: () => <Tag color="orange">PENDING</Tag> },
                    ]}
                  />
                </Card>
              )
            )}

            {resolved.length > 0 && (
              <Card title={`All Peer Nominations (${resolved.length})`}>
                <Table
                  rowKey="id"
                  size="small"
                  pagination={{ pageSize: 10 }}
                  dataSource={resolved}
                  columns={[
                    { title: 'Reviewee',       render: (_, r) => `${r.reviewee_first} ${r.reviewee_last}` },
                    { title: 'Nominated Peer', render: (_, r) => `${r.peer_first} ${r.peer_last}` },
                    {
                      title: 'Status',
                      dataIndex: 'status',
                      render: (v) => <Tag color={v === 'APPROVED' ? 'green' : 'red'}>{v}</Tag>,
                    },
                  ]}
                />
              </Card>
            )}
          </>
        );
      })()}

      {/* Override Modal */}
      <Modal
        title="Override Cycle State (Super Admin)"
        open={overrideModal}
        onOk={handleOverride}
        onCancel={() => setOverrideModal(false)}
        okText="Apply Override"
        okButtonProps={{ danger: true }}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <div>Target State:</div>
          <Select
            style={{ width: '100%' }}
            placeholder="— select state —"
            value={overrideState || undefined}
            onChange={(v) => setOverrideState(v)}
            options={['DRAFT', 'NOMINATION', 'ACTIVE', 'CLOSED', 'RESULTS_RELEASED', 'ARCHIVED'].map((s) => ({ value: s, label: s }))}
          />
          <div>Reason (required):</div>
          <Input.TextArea
            rows={3}
            value={overrideReason}
            onChange={(e) => setOverrideReason(e.target.value)}
            placeholder="Explain why this override is needed..."
          />
        </Space>
      </Modal>

      {/* Edit Cycle Modal (DRAFT only) */}
      <Modal
        title="Edit Cycle"
        open={editModal}
        onOk={handleEditSave}
        onCancel={() => setEditModal(false)}
        okText="Save Changes"
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="name" label="Cycle Name" rules={[{ required: true, message: 'Name is required' }]}>
            <Input />
          </Form.Item>
          <Space wrap>
            <Form.Item name="quarter" label="Quarter">
              <Select style={{ width: 120 }} placeholder="None" allowClear
                options={['Q1', 'Q2', 'Q3', 'Q4'].map((v) => ({ value: v, label: v }))}
              />
            </Form.Item>
            <Form.Item name="quarter_year" label="Year">
              <InputNumber placeholder="2025" min={2020} max={2035} style={{ width: 120 }} />
            </Form.Item>
          </Space>
          <Form.Item name="review_deadline" label="Review Deadline" rules={[{ required: true, message: 'Deadline is required' }]}>
            <DatePicker showTime style={{ width: '100%' }} />
          </Form.Item>
          {cycle?.peer_enabled && (
            <>
              <Form.Item name="nomination_deadline" label="Nomination Deadline (optional)">
                <DatePicker showTime style={{ width: '100%' }} />
              </Form.Item>
              <Space style={{ width: '100%' }}>
                <Form.Item name="peer_min_count" label="Min Peers" style={{ flex: 1 }}>
                  <InputNumber min={1} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item name="peer_max_count" label="Max Peers" style={{ flex: 1 }}>
                  <InputNumber min={1} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item name="peer_threshold" label="Anon Threshold" style={{ flex: 1 }}>
                  <InputNumber min={1} style={{ width: '100%' }} />
                </Form.Item>
              </Space>
            </>
          )}
        </Form>
      </Modal>

      {/* Add Participants Modal */}
      <Modal
        title="Add Participants"
        open={addParticipantModal}
        onOk={handleAddParticipants}
        onCancel={() => setAddParticipantModal(false)}
        okText={`Add ${selectedUserIds.length || ''} Selected`}
        confirmLoading={addingParticipants}
        okButtonProps={{ disabled: !selectedUserIds.length }}
        width={800}
      >
        {(() => {
          const departments = [...new Map(
            allUsers.filter((u) => u.department && u.department_name)
                    .map((u) => [u.department, u.department_name])
          ).entries()].sort((a, b) => a[1].localeCompare(b[1]));

          const noDeptUsers = allUsers.filter((u) => !u.department);

          const transferData = allUsers.map((u) => ({
            key: u.id,
            title: `${u.first_name} ${u.last_name} (${u.email})`,
            department: u.department_name || '',
            name: `${u.first_name} ${u.last_name}`,
            email: u.email,
          }));

          const getDeptState = (deptId) => {
            const ids = allUsers.filter((u) => u.department === deptId).map((u) => u.id);
            const sel = ids.filter((id) => selectedUserIds.includes(id)).length;
            return { checked: sel === ids.length && ids.length > 0, indeterminate: sel > 0 && sel < ids.length, total: ids.length, sel };
          };

          const toggleDept = (deptId, checked) => {
            const ids = allUsers.filter((u) => u.department === deptId).map((u) => u.id);
            setSelectedUserIds((prev) => checked ? [...new Set([...prev, ...ids])] : prev.filter((k) => !ids.includes(k)));
          };

          const noDeptState = (() => {
            const ids = noDeptUsers.map((u) => u.id);
            const sel = ids.filter((id) => selectedUserIds.includes(id)).length;
            return { checked: sel === ids.length && ids.length > 0, indeterminate: sel > 0 && sel < ids.length, total: ids.length, sel };
          })();

          return (
            <>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 14, padding: '12px 14px', background: '#fafafa', borderRadius: 8, border: '1px solid #f0f0f0' }}>
                <span style={{ fontSize: 12, color: '#888', fontWeight: 500, marginRight: 4 }}>Quick select:</span>
                {departments.map(([deptId, deptName]) => {
                  const { checked, indeterminate, total, sel } = getDeptState(deptId);
                  return (
                    <div key={deptId} onClick={() => toggleDept(deptId, !checked)} style={{
                      cursor: 'pointer', userSelect: 'none', display: 'inline-flex', alignItems: 'center', gap: 6,
                      padding: '4px 12px', borderRadius: 20, fontSize: 13,
                      border: `1px solid ${checked ? '#1677ff' : indeterminate ? '#fa8c16' : '#d9d9d9'}`,
                      background: checked ? '#1677ff' : indeterminate ? '#fff7e6' : '#fff',
                      color: checked ? '#fff' : indeterminate ? '#d46b08' : '#555',
                    }}>
                      {deptName}
                      <span style={{ background: checked ? 'rgba(255,255,255,0.25)' : indeterminate ? '#ffd591' : '#f0f0f0', borderRadius: 10, padding: '0 6px', fontSize: 11, fontWeight: 600 }}>
                        {sel}/{total}
                      </span>
                    </div>
                  );
                })}
                {noDeptUsers.length > 0 && (
                  <div onClick={() => { const ids = noDeptUsers.map((u) => u.id); setSelectedUserIds((prev) => noDeptState.checked ? prev.filter((k) => !ids.includes(k)) : [...new Set([...prev, ...ids])]); }} style={{
                    cursor: 'pointer', userSelect: 'none', display: 'inline-flex', alignItems: 'center', gap: 6,
                    padding: '4px 12px', borderRadius: 20, fontSize: 13,
                    border: `1px solid ${noDeptState.checked ? '#8c8c8c' : noDeptState.indeterminate ? '#fa8c16' : '#d9d9d9'}`,
                    background: noDeptState.checked ? '#8c8c8c' : noDeptState.indeterminate ? '#fff7e6' : '#fff',
                    color: noDeptState.checked ? '#fff' : noDeptState.indeterminate ? '#d46b08' : '#555',
                  }}>
                    No Department
                    <span style={{ background: noDeptState.checked ? 'rgba(255,255,255,0.25)' : noDeptState.indeterminate ? '#ffd591' : '#f0f0f0', borderRadius: 10, padding: '0 6px', fontSize: 11, fontWeight: 600 }}>
                      {noDeptState.sel}/{noDeptState.total}
                    </span>
                  </div>
                )}
              </div>
              <Transfer
                dataSource={transferData}
                showSearch
                filterOption={(input, item) =>
                  item.title.toLowerCase().includes(input.toLowerCase()) ||
                  (item.department || '').toLowerCase().includes(input.toLowerCase())
                }
                targetKeys={selectedUserIds}
                onChange={setSelectedUserIds}
                titles={['All Employees', 'Selected']}
                render={(item) => (
                  <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', paddingRight: 4 }}>
                    <span style={{ fontSize: 13, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {item.name}
                      <span style={{ color: '#aaa', fontSize: 11, marginLeft: 6 }}>({item.email})</span>
                    </span>
                    {item.department && <Tag color="geekblue" style={{ fontSize: 10, lineHeight: '18px', padding: '0 5px', margin: 0 }}>{item.department}</Tag>}
                  </span>
                )}
                listStyle={{ width: '45%', height: 380 }}
                style={{ width: '100%' }}
              />
            </>
          );
        })()}
      </Modal>
    </Space>
  );
}
