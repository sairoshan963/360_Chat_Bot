import { useEffect, useState } from 'react';
import {
  Table, Button, Tag, Space, Modal, Form, Input, Select, AutoComplete,
  Typography, Card, message, Popconfirm,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { listUsers, createUser, updateUser, deleteUser } from '../../api/users';
import usePageTitle from '../../hooks/usePageTitle';

const { Title } = Typography;
const { Option } = Select;

const ROLE_COLOR   = { SUPER_ADMIN: 'red', HR_ADMIN: 'blue', MANAGER: 'green', EMPLOYEE: 'default' };
const STATUS_COLOR = { ACTIVE: 'green', INACTIVE: 'default', SUSPENDED: 'orange' };

const JOB_TITLES = [
  'CEO','CTO','COO','CFO','VP of Engineering','VP of Product','Head of Engineering',
  'Engineering Manager','Tech Lead','Senior Software Engineer','Software Engineer',
  'Frontend Engineer','Backend Engineer','Full Stack Engineer','DevOps Engineer',
  'QA Engineer','Product Manager','Senior Product Manager','Product Designer',
  'UX/UI Designer','Data Analyst','Data Scientist','HR Manager','Recruiter',
  'Operations Manager','Finance Manager','Accountant','Sales Manager','Account Executive',
  'Marketing Manager','Customer Success Manager','Customer Support Specialist',
];

export default function UsersPage() {
  usePageTitle('Users');
  const [users,   setUsers]   = useState([]);
  const [loading, setLoading] = useState(false);
  const [modal,   setModal]   = useState({ open: false, user: null });
  const [form]                = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const res = await listUsers();
      setUsers(res.data.users || []);
    } catch { message.error('Failed to load users'); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const openCreate = () => { form.resetFields(); setModal({ open: true, user: null }); };
  const openEdit   = (u) => {
    form.setFieldsValue({
      first_name: u.first_name, middle_name: u.middle_name ?? undefined, last_name: u.last_name, email: u.email,
      job_title: u.job_title ?? undefined, role: u.role, status: u.status,
      manager_id: u.manager_id ?? undefined, department: u.department ?? undefined,
    });
    setModal({ open: true, user: u });
  };

  const handleSave = async () => {
    const vals = await form.validateFields();
    try {
      if (modal.user) { await updateUser(modal.user.id, vals); message.success('User updated'); }
      else { await createUser(vals); message.success('User created'); }
      setModal({ open: false, user: null });
      load();
    } catch (err) {
      message.error(err.response?.data?.message || err.response?.data?.email?.[0] || 'Save failed');
    }
  };

  const handleDelete = async (id) => {
    try { await deleteUser(id); message.success('User deactivated'); load(); }
    catch { message.error('Failed to deactivate'); }
  };

  const managerOptions  = users.filter((u) => u.id !== modal.user?.id);
  const existingDepts   = [...new Set(users.map((u) => u.department).filter(Boolean))].sort();

  const columns = [
    { title: 'Name',      render: (_, r) => [r.first_name, r.middle_name, r.last_name].filter(Boolean).join(' ') },
    { title: 'Job Title', dataIndex: 'job_title', render: (v) => v || '—' },
    { title: 'Email',     dataIndex: 'email' },
    {
      title: 'Role', dataIndex: 'role',
      render: (v) => <Tag color={ROLE_COLOR[v]}>{v.replace('_', ' ')}</Tag>,
      filters: ['SUPER_ADMIN','HR_ADMIN','MANAGER','EMPLOYEE'].map((r) => ({ text: r, value: r })),
      onFilter: (v, r) => r.role === v,
    },
    { title: 'Status', dataIndex: 'status', render: (v) => <Tag color={STATUS_COLOR[v]}>{v}</Tag> },
    {
      title: 'Reports To',
      render: (_, r) => { const mgr = users.find((u) => u.id === r.manager_id); return mgr ? [mgr.first_name, mgr.middle_name, mgr.last_name].filter(Boolean).join(' ') : '—'; },
    },
    { title: 'Department', dataIndex: 'department', render: (v) => v || '—' },
    {
      title: 'Actions',
      render: (_, r) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
          <Popconfirm title="Deactivate this user?" onConfirm={() => handleDelete(r.id)} disabled={r.status === 'INACTIVE'}>
            <Button size="small" danger icon={<DeleteOutlined />} disabled={r.status === 'INACTIVE'} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>Users</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>Add User</Button>
      </Space>

      <Table rowKey="id" columns={columns} dataSource={users} loading={loading} pagination={{ pageSize: 10 }} scroll={{ x: true }} />

      <Modal title={modal.user ? 'Edit User' : 'Create User'} open={modal.open} onOk={handleSave} onCancel={() => setModal({ open: false, user: null })} okText="Save" destroyOnClose>
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="first_name"  label="First Name"  rules={[{ required: true }]}><Input placeholder="First name" /></Form.Item>
          <Form.Item name="middle_name" label="Middle Name"><Input placeholder="Middle name (optional)" /></Form.Item>
          <Form.Item name="last_name"   label="Last Name"   rules={[{ required: true }]}><Input placeholder="Last name" /></Form.Item>
          <Form.Item name="email"      label="Email"      rules={[{ required: true, type: 'email' }]}>
            <Input disabled={!!modal.user} />
          </Form.Item>
          <Form.Item name="job_title" label="Job Title">
            <AutoComplete options={JOB_TITLES.map((t) => ({ value: t }))} filterOption={(i, o) => o.value.toLowerCase().includes(i.toLowerCase())} placeholder="Select or type a job title" allowClear />
          </Form.Item>
          {!modal.user && (
            <Form.Item name="password" label="Password" rules={[{ required: true, min: 8 }]}>
              <Input.Password />
            </Form.Item>
          )}
          <Form.Item name="role" label="Role" rules={[{ required: true }]}>
            <Select>
              {['SUPER_ADMIN','HR_ADMIN','MANAGER','EMPLOYEE'].map((r) => (
                <Option key={r} value={r}>{r.replace('_', ' ')}</Option>
              ))}
            </Select>
          </Form.Item>
          {modal.user && (
            <Form.Item name="status" label="Status">
              <Select>
                {['ACTIVE','INACTIVE','SUSPENDED'].map((s) => (<Option key={s} value={s}>{s}</Option>))}
              </Select>
            </Form.Item>
          )}
          <Form.Item name="department" label="Department" extra="Pick an existing department or type a new one">
            <AutoComplete options={existingDepts.map((d) => ({ value: d }))} filterOption={(i, o) => o.value.toLowerCase().includes(i.toLowerCase())} placeholder="e.g. Engineering, Product" allowClear />
          </Form.Item>
          <Form.Item name="manager_id" label="Reports To">
            <Select showSearch allowClear placeholder="Select reporting manager"
              filterOption={(i, o) => o.label.toLowerCase().includes(i.toLowerCase())}
              options={managerOptions.map((u) => ({ value: u.id, label: `${[u.first_name, u.middle_name, u.last_name].filter(Boolean).join(' ')} (${u.role.replace('_', ' ')})` }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
