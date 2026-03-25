import { useEffect, useState } from 'react';
import {
  Table, Button, Tag, Space, Modal, Form, Input, Select, AutoComplete,
  Typography, Card, message, Popconfirm,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, KeyOutlined } from '@ant-design/icons';
import { listUsers, createUser, updateUser, deleteUser, adminResetUserPassword } from '../../api/users';
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
  const [users,    setUsers]    = useState([]);
  const [allUsers, setAllUsers] = useState([]);  // unfiltered — used for manager dropdown
  const [loading,  setLoading]  = useState(false);
  const [searchInput,   setSearchInput]   = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [modal,   setModal]   = useState({ open: false, user: null });
  const [form]                = Form.useForm();

  const loadAll = async () => {
    try {
      const res = await listUsers({});
      setAllUsers(res.data.users || []);
    } catch { /* silent — table still works */ }
  };

  const load = async () => {
    setLoading(true);
    try {
      const params = appliedSearch.trim() ? { search: appliedSearch.trim() } : {};
      const res = await listUsers(params);
      setUsers(res.data.users || []);
    } catch { message.error('Failed to load users'); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadAll(); }, []);
  useEffect(() => { load(); }, [appliedSearch]);

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
      loadAll();
    } catch (err) {
      message.error(err.response?.data?.message || err.response?.data?.email?.[0] || 'Save failed');
    }
  };

  const handleDelete = async (id) => {
    try { await deleteUser(id); message.success('User deleted'); load(); loadAll(); }
    catch (err) { message.error(err.response?.data?.error || 'Failed to delete user'); }
  };

  const handleResetPassword = async (u) => {
    try {
      await adminResetUserPassword(u.id);
      message.success(`Password reset email sent to ${u.email}`);
    } catch (err) {
      message.error(err.response?.data?.error || 'Failed to send reset email');
    }
  };

  const managerOptions = allUsers.filter((u) => u.id !== modal.user?.id);
  const deptOptions    = [...new Map(allUsers.filter((u) => u.department).map((u) => [u.department, u.department_name])).entries()].map(([id, name]) => ({ value: id, label: name || id }));

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
    { title: 'Reports To', dataIndex: 'manager_name', render: (v) => v || '—' },
    { title: 'Department', dataIndex: 'department_name', render: (v) => v || '—' },
    {
      title: 'Actions',
      render: (_, r) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
          <Popconfirm
            title="Send password reset email?"
            description={`A reset link will be sent to ${r.email}`}
            onConfirm={() => handleResetPassword(r)}
            okText="Send"
            disabled={r.status !== 'ACTIVE'}
          >
            <Button size="small" icon={<KeyOutlined />} disabled={r.status !== 'ACTIVE'} title="Reset Password" />
          </Popconfirm>
          <Popconfirm title="Delete this user?" description="This will permanently delete the user and all their data." onConfirm={() => handleDelete(r.id)} okText="Delete" okType="danger">
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
        <Title level={4} style={{ margin: 0 }}>Users</Title>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
          <Input.Search
            placeholder="Search by name or email"
            allowClear
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onSearch={(v) => setAppliedSearch(v ?? '')}
            style={{ width: 300, maxWidth: '100%' }}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>Add User</Button>
        </div>
      </div>

      <Table rowKey="id" columns={columns} dataSource={users} loading={loading}
        pagination={{ defaultPageSize: 10, showSizeChanger: true, pageSizeOptions: ['10', '20', '50', '100'], showTotal: (total) => `${total} users` }}
        scroll={{ x: true }} />

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
          <Form.Item name="department" label="Department" extra="Pick an existing department">
            <Select allowClear placeholder="e.g. Engineering, Product" showSearch filterOption={(i, o) => (o?.label ?? '').toLowerCase().includes(i.toLowerCase())} options={deptOptions} />
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
