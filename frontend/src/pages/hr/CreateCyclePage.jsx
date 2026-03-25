import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card, Form, Input, Select, Switch, InputNumber, DatePicker,
  Button, Space, Typography, message, Divider, Transfer, Tag,
} from 'antd';
import { listTemplates, createCycle, addParticipants } from '../../api/cycles';
import { listUsers } from '../../api/users';
import usePageTitle from '../../hooks/usePageTitle';

const { Title } = Typography;
const { Option } = Select;
const { TextArea } = Input;

export default function CreateCyclePage() {
  usePageTitle('New Cycle');
  const [form]        = Form.useForm();
  const [loading,     setLoading]    = useState(false);
  const [templates,   setTemplates]  = useState([]);
  const [users,       setUsers]      = useState([]);
  const [peerEnabled, setPeerEnabled] = useState(false);
  const [targetKeys,  setTargetKeys] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    listTemplates().then((r) => setTemplates(r.data.templates || [])).catch(() => {});
    listUsers().then((r) => setUsers((r.data.users || []).filter((u) => u.status === 'ACTIVE'))).catch(() => {});
  }, []);

  const onFinish = async (vals) => {
    if (!targetKeys.length) { message.error('Add at least one participant'); return; }
    setLoading(true);
    try {
      const payload = {
        name:                     vals.name,
        description:              vals.description,
        template_id:              vals.template_id,
        peer_enabled:             vals.peer_enabled || false,
        peer_min_count:           vals.peer_min_count,
        peer_max_count:           vals.peer_max_count,
        peer_anonymity:           vals.peer_anonymity,
        manager_anonymity:        vals.manager_anonymity  || 'TRANSPARENT',
        self_anonymity:           vals.self_anonymity     || 'TRANSPARENT',
        nomination_deadline:      vals.nomination_deadline?.toISOString(),
        review_deadline:          vals.review_deadline.toISOString(),
        quarter:                  vals.quarter            || null,
        quarter_year:             vals.quarter_year       || null,
        nomination_approval_mode: vals.nomination_approval_mode || 'AUTO',
      };
      const res = await createCycle(payload);
      const cycleId = res.data.cycle.id;
      await addParticipants(cycleId, targetKeys);
      message.success('Cycle created successfully');
      navigate(`/hr/cycles/${cycleId}`);
    } catch (err) {
      message.error(err.response?.data?.message || 'Failed to create cycle');
    } finally { setLoading(false); }
  };

  // departments: array of [deptId, deptName] pairs, sorted by name
  const departments = [...new Map(
    users.filter((u) => u.department && u.department_name)
         .map((u) => [u.department, u.department_name])
  ).entries()].sort((a, b) => a[1].localeCompare(b[1]));

  const noDeptUsers = users.filter((u) => !u.department);

  const transferData = users.map((u) => ({
    key: u.id,
    title: `${u.first_name} ${u.last_name} (${u.email})`,
    description: u.department_name ? `${u.role} · ${u.department_name}` : u.role,
    department: u.department_name || '',
    role: u.role,
    jobTitle: u.job_title || '',
    name: `${u.first_name} ${u.last_name}`,
  }));

  const ROLE_COLOR = { SUPER_ADMIN: 'magenta', HR_ADMIN: 'gold', MANAGER: 'blue', EMPLOYEE: 'cyan' };

  const getDeptState = (deptId) => {
    const ids = users.filter((u) => u.department === deptId).map((u) => u.id);
    const sel = ids.filter((id) => targetKeys.includes(id)).length;
    return { checked: sel === ids.length && ids.length > 0, indeterminate: sel > 0 && sel < ids.length, total: ids.length, sel };
  };

  const getGroupState = (groupUsers) => {
    const ids = groupUsers.map((u) => u.id);
    const sel = ids.filter((id) => targetKeys.includes(id)).length;
    return { checked: sel === ids.length && ids.length > 0, indeterminate: sel > 0 && sel < ids.length, total: ids.length, sel };
  };

  const toggleDept = (deptId, checked) => {
    const ids = users.filter((u) => u.department === deptId).map((u) => u.id);
    setTargetKeys((prev) => checked ? [...new Set([...prev, ...ids])] : prev.filter((k) => !ids.includes(k)));
  };

  const toggleGroup = (groupUsers, checked) => {
    const ids = groupUsers.map((u) => u.id);
    setTargetKeys((prev) => checked ? [...new Set([...prev, ...ids])] : prev.filter((k) => !ids.includes(k)));
  };

  return (
    <Card>
      <Title level={4} style={{ marginBottom: 24 }}>Create Review Cycle</Title>
      <Form form={form} layout="vertical" onFinish={onFinish} initialValues={{ peer_anonymity: 'ANONYMOUS', manager_anonymity: 'TRANSPARENT', self_anonymity: 'TRANSPARENT' }}>
        <Form.Item name="name" label="Cycle Name" rules={[{ required: true }]}>
          <Input placeholder="e.g. Q1 2026 Performance Review" />
        </Form.Item>
        <Space wrap>
          <Form.Item name="quarter" label="Quarter">
            <Select placeholder="Select quarter" allowClear style={{ width: 120 }}>
              {['Q1','Q2','Q3','Q4'].map((q) => <Option key={q} value={q}>{q}</Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="quarter_year" label="Year">
            <InputNumber placeholder="2025" min={2020} max={2030} style={{ width: 120 }} />
          </Form.Item>
        </Space>
        <Form.Item name="description" label="Description"><TextArea rows={2} /></Form.Item>
        <Form.Item name="template_id" label="Review Template" rules={[{ required: true }]}>
          <Select placeholder="Select a template">
            {templates.map((t) => <Option key={t.id} value={t.id}>{t.name}</Option>)}
          </Select>
        </Form.Item>

        <Divider>Anonymity Settings</Divider>
        <Space wrap>
          <Form.Item name="self_anonymity" label="Self Review Anonymity">
            <Select style={{ width: 180 }}>
              {['TRANSPARENT','SEMI_ANONYMOUS','ANONYMOUS'].map((a) => <Option key={a} value={a}>{a.replace(/_/g,' ')}</Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="manager_anonymity" label="Manager Review Anonymity">
            <Select style={{ width: 180 }}>
              {['TRANSPARENT','SEMI_ANONYMOUS','ANONYMOUS'].map((a) => <Option key={a} value={a}>{a.replace(/_/g,' ')}</Option>)}
            </Select>
          </Form.Item>
        </Space>

        <Divider>Peer Review</Divider>
        <Form.Item name="peer_enabled" label="Enable Peer Review" valuePropName="checked">
          <Switch onChange={setPeerEnabled} />
        </Form.Item>
        {peerEnabled && (
          <Space wrap>
            <Form.Item name="peer_min_count" label="Min Peers" rules={[{ required: true }]}><InputNumber min={1} max={10} /></Form.Item>
            <Form.Item name="peer_max_count" label="Max Peers" rules={[{ required: true }]}><InputNumber min={1} max={10} /></Form.Item>
            <Form.Item name="peer_anonymity" label="Peer Anonymity">
              <Select style={{ width: 180 }}>
                {['ANONYMOUS','SEMI_ANONYMOUS','TRANSPARENT'].map((a) => <Option key={a} value={a}>{a.replace(/_/g,' ')}</Option>)}
              </Select>
            </Form.Item>
            <Form.Item name="nomination_deadline" label="Nomination Deadline" rules={[{ required: true, message: 'Nomination deadline is required when peer review is enabled' }]}><DatePicker showTime /></Form.Item>
            <Form.Item name="nomination_approval_mode" label="Nomination Approval" initialValue="AUTO">
              <Select style={{ width: 220 }}>
                <Option value="AUTO">Auto-approve (immediate)</Option>
                <Option value="MANUAL">Manager must approve</Option>
              </Select>
            </Form.Item>
          </Space>
        )}

        <Divider>Deadlines</Divider>
        <Form.Item name="review_deadline" label="Review Deadline" rules={[{ required: true }]}>
          <DatePicker showTime />
        </Form.Item>

        <Divider>
          Participants
          {targetKeys.length > 0 && <Tag color="blue" style={{ marginLeft: 10, fontWeight: 600 }}>{targetKeys.length} selected</Tag>}
        </Divider>
        <Form.Item>
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginBottom: 14, padding: '12px 14px', background: '#fafafa', borderRadius: 8, border: '1px solid #f0f0f0' }}>
            <span style={{ fontSize: 12, color: '#888', fontWeight: 500, marginRight: 4 }}>Quick select:</span>
            {departments.length > 0 ? departments.map(([deptId, deptName]) => {
              const { checked, indeterminate, total, sel } = getDeptState(deptId);
              return (
                <div key={deptId} onClick={() => toggleDept(deptId, !checked)} style={{
                  cursor: 'pointer', userSelect: 'none', display: 'inline-flex', alignItems: 'center', gap: 6,
                  padding: '4px 12px', borderRadius: 20, fontSize: 13,
                  border: `1px solid ${checked?'#1677ff':indeterminate?'#fa8c16':'#d9d9d9'}`,
                  background: checked?'#1677ff':indeterminate?'#fff7e6':'#fff',
                  color: checked?'#fff':indeterminate?'#d46b08':'#555',
                }}>
                  {deptName}
                  <span style={{ background: checked?'rgba(255,255,255,0.25)':indeterminate?'#ffd591':'#f0f0f0', borderRadius: 10, padding: '0 6px', fontSize: 11, fontWeight: 600 }}>
                    {sel}/{total}
                  </span>
                </div>
              );
            }) : <span style={{ color: '#bbb', fontSize: 13 }}>No departments configured — assign via Org Hierarchy.</span>}
            {noDeptUsers.length > 0 && (() => {
              const { checked, indeterminate, total, sel } = getGroupState(noDeptUsers);
              return (
                <div onClick={() => toggleGroup(noDeptUsers, !checked)} style={{
                  cursor: 'pointer', userSelect: 'none', display: 'inline-flex', alignItems: 'center', gap: 6,
                  padding: '4px 12px', borderRadius: 20, fontSize: 13,
                  border: `1px solid ${checked?'#8c8c8c':indeterminate?'#fa8c16':'#d9d9d9'}`,
                  background: checked?'#8c8c8c':indeterminate?'#fff7e6':'#fff',
                  color: checked?'#fff':indeterminate?'#d46b08':'#555',
                }}>
                  No Department
                  <span style={{ background: checked?'rgba(255,255,255,0.25)':indeterminate?'#ffd591':'#f0f0f0', borderRadius: 10, padding: '0 6px', fontSize: 11, fontWeight: 600 }}>
                    {sel}/{total}
                  </span>
                </div>
              );
            })()}
          </div>
          <Transfer
            dataSource={transferData}
            showSearch
            filterOption={(input, item) => item.title.toLowerCase().includes(input.toLowerCase()) || (item.department||'').toLowerCase().includes(input.toLowerCase())}
            targetKeys={targetKeys}
            onChange={setTargetKeys}
            titles={['All Users','Selected']}
            render={(item) => (
              <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', paddingRight: 4 }}>
                <span style={{ fontSize: 13, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {item.name}
                  <span style={{ color: '#aaa', fontSize: 11, marginLeft: 6 }}>({item.title.match(/\(([^)]+)\)/)?.[1]})</span>
                  {item.jobTitle?.toLowerCase().includes('intern') && (
                    <span style={{ marginLeft: 5, fontSize: 10, background: '#f9f0ff', color: '#722ed1', border: '1px solid #d3adf7', borderRadius: 4, padding: '0 4px' }}>Intern</span>
                  )}
                </span>
                <span style={{ display: 'flex', gap: 4, flexShrink: 0, marginLeft: 8 }}>
                  {item.department && <Tag color="geekblue" style={{ fontSize: 10, lineHeight: '18px', padding: '0 5px', margin: 0 }}>{item.department}</Tag>}
                </span>
              </span>
            )}
            listStyle={{ width: '45%', height: 440 }}
            style={{ width: '100%' }}
          />
        </Form.Item>

        <Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" loading={loading}>Create Cycle</Button>
            <Button onClick={() => navigate('/hr/cycles')}>Cancel</Button>
          </Space>
        </Form.Item>
      </Form>
    </Card>
  );
}
