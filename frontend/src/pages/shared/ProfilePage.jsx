import { useRef, useState } from 'react';
import {
  Card, Row, Col, Form, Input, Button, Avatar, Typography,
  Space, Divider, message, Tooltip,
} from 'antd';
import {
  CameraOutlined, SaveOutlined, LockOutlined,
  MailOutlined, UserOutlined, IdcardOutlined, DeleteOutlined,
} from '@ant-design/icons';
import useAuthStore from '../../store/authStore';
import { updateMe, changePassword, uploadAvatar, removeAvatar } from '../../api/auth';
import usePageTitle from '../../hooks/usePageTitle';

const { Text } = Typography;

const ROLE_COLOR = { SUPER_ADMIN: '#ef4444', HR_ADMIN: '#3b82f6', MANAGER: '#16a34a', EMPLOYEE: '#6366f1' };
const ROLE_BG    = { SUPER_ADMIN: '#fef2f2', HR_ADMIN: '#eff6ff', MANAGER: '#f0fdf4', EMPLOYEE: '#eef2ff' };
const ROLE_LABEL = { SUPER_ADMIN: 'Super Admin', HR_ADMIN: 'HR Admin', MANAGER: 'Manager', EMPLOYEE: 'Employee' };

const AVATAR_COLORS = ['#4f46e5','#16a34a','#7c3aed','#ea580c','#db2777','#0891b2'];
function avatarColor(id = '') {
  const code = [...String(id)].reduce((s, c) => s + c.charCodeAt(0), 0);
  return AVATAR_COLORS[code % AVATAR_COLORS.length];
}

function buildAvatarSrc(avatarUrl) {
  if (!avatarUrl) return null;
  if (avatarUrl.startsWith('http')) return avatarUrl;
  const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
  return `${base}${avatarUrl}`;
}

export default function ProfilePage() {
  usePageTitle('My Profile');
  const { user, updateUser } = useAuthStore();
  const [profileForm] = Form.useForm();
  const [pwForm]      = Form.useForm();
  const [savingProfile, setSavingProfile] = useState(false);
  const [savingPw,      setSavingPw]      = useState(false);
  const [uploading,  setUploading]  = useState(false);
  const [removing,   setRemoving]   = useState(false);
  const fileRef = useRef(null);

  const [avatarSrc, setAvatarSrc] = useState(buildAvatarSrc(user?.avatar_url));

  const initials   = user ? `${user.first_name?.[0]||''}${user.last_name?.[0]||''}`.toUpperCase() : '?';
  const accentColor = avatarColor(user?.id);

  const handleAvatarUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) { message.error('Image must be smaller than 2 MB'); return; }
    setUploading(true);
    try {
      const res = await uploadAvatar(file);
      const avatarUrl = res.data?.avatar_url;
      if (avatarUrl) {
        setAvatarSrc(buildAvatarSrc(avatarUrl));
        updateUser({ avatar_url: avatarUrl });
        message.success('Profile photo updated');
      }
    } catch (err) {
      message.error(err.response?.data?.message || err.response?.data?.detail || 'Failed to upload avatar');
    } finally { setUploading(false); }
  };

  const handleRemoveAvatar = async () => {
    setRemoving(true);
    try {
      await removeAvatar();
      setAvatarSrc(null);
      updateUser({ avatar_url: null });
      message.success('Profile photo removed');
    } catch (err) {
      message.error(err.response?.data?.message || err.response?.data?.detail || 'Failed to remove photo');
    } finally { setRemoving(false); }
  };

  const handleSaveProfile = async (values) => {
    setSavingProfile(true);
    try {
      const res = await updateMe({
        first_name: values.first_name.trim(),
        middle_name: values.middle_name?.trim() || null,
        last_name: values.last_name.trim(),
        display_name: values.display_name?.trim() || null,
        // job_title not sent — read-only in profile (managed by admin)
      });
      const updated = res.data?.user || values;
      updateUser({
        first_name: updated.first_name,
        middle_name: updated.middle_name,
        last_name: updated.last_name,
        display_name: updated.display_name,
        job_title: user?.job_title,
      });
      message.success('Profile updated successfully');
    } catch (err) {
      message.error(err.response?.data?.message || err.response?.data?.detail || 'Failed to update profile');
    } finally { setSavingProfile(false); }
  };

  const handleChangePassword = async (values) => {
    if (values.new_password !== values.confirm_password) { message.error('New passwords do not match'); return; }
    setSavingPw(true);
    try {
      await changePassword({ current_password: values.current_password, new_password: values.new_password });
      message.success('Password changed successfully');
      pwForm.resetFields();
    } catch (err) {
      message.error(err.response?.data?.message || err.response?.data?.detail || 'Failed to change password');
    } finally { setSavingPw(false); }
  };

  return (
    <Space direction="vertical" size={20} style={{ width: '100%' }}>
      <Row gutter={[20, 20]}>
        <Col xs={24} md={8}>
          <Card style={{ borderRadius: 16, overflow: 'hidden', border: 'none', boxShadow: '0 4px 20px rgba(0,0,0,0.08)' }} styles={{ body: { padding: 0 } }}>
            <div style={{ height: 90, background: `linear-gradient(135deg, ${accentColor} 0%, ${accentColor}88 100%)` }} />
            <div style={{ textAlign: 'center', padding: '0 24px 28px' }}>
              <div style={{ display: 'inline-block', marginTop: -44, position: 'relative', marginBottom: 12 }}>
                <Avatar size={88} src={avatarSrc || undefined}
                  style={{ background: accentColor, fontSize: 30, fontWeight: 700, border: '4px solid #fff', boxShadow: '0 4px 16px rgba(0,0,0,0.15)' }}>
                  {!avatarSrc && initials}
                </Avatar>
                <Tooltip title="Change photo">
                  <div onClick={() => !uploading && fileRef.current?.click()}
                    style={{ position: 'absolute', bottom: 2, right: 2, width: 26, height: 26, borderRadius: '50%', background: uploading?'#94a3b8':'#1e293b', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: uploading?'not-allowed':'pointer', boxShadow: '0 2px 8px rgba(0,0,0,0.3)', border: '2px solid #fff' }}>
                    <CameraOutlined style={{ color: '#fff', fontSize: 11 }} />
                  </div>
                </Tooltip>
              </div>

              <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={handleAvatarUpload} />

              <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginBottom: 12 }}>
                <Button size="small" icon={<CameraOutlined />} onClick={() => !uploading && fileRef.current?.click()} loading={uploading} style={{ borderRadius: 8, fontSize: 12 }}>Change Photo</Button>
                {avatarSrc && <Button size="small" danger icon={<DeleteOutlined />} onClick={handleRemoveAvatar} loading={removing} style={{ borderRadius: 8, fontSize: 12 }}>Remove</Button>}
              </div>

              <div style={{ fontWeight: 700, fontSize: 18, color: '#1e293b', marginBottom: 3 }}>
                {user?.display_name?.trim() || [user?.first_name, user?.middle_name, user?.last_name].filter(Boolean).join(' ')}
              </div>
              {user?.job_title && <div style={{ fontSize: 13, color: '#64748b', marginBottom: 8 }}>{user.job_title}</div>}
              <div style={{ marginBottom: 14 }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: ROLE_BG[user?.role], color: ROLE_COLOR[user?.role], fontWeight: 600, fontSize: 12, padding: '4px 12px', borderRadius: 20 }}>
                  <span style={{ width: 7, height: 7, borderRadius: '50%', background: ROLE_COLOR[user?.role], display: 'inline-block' }} />
                  {ROLE_LABEL[user?.role]}
                </span>
              </div>
              <Divider style={{ margin: '0 0 14px' }} />
              <Space direction="vertical" size={8} style={{ width: '100%', textAlign: 'left' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#64748b', fontSize: 13 }}>
                  <MailOutlined style={{ color: accentColor, fontSize: 14 }} />
                  <Text style={{ fontSize: 13, color: '#475569' }}>{user?.email}</Text>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#64748b', fontSize: 13 }}>
                  <IdcardOutlined style={{ color: accentColor, fontSize: 14 }} />
                  <Text style={{ fontSize: 13, color: '#475569' }}>ID: {user?.id}</Text>
                </div>
              </Space>
            </div>
          </Card>
        </Col>

        <Col xs={24} md={16}>
          <Space direction="vertical" size={20} style={{ width: '100%' }}>
            <Card title={<Space><UserOutlined style={{ color: '#4f46e5' }} /><span>Profile Information</span></Space>} style={{ borderRadius: 14, border: 'none', boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}>
              <Form form={profileForm} layout="vertical" initialValues={{ first_name: user?.first_name, middle_name: user?.middle_name, last_name: user?.last_name, display_name: user?.display_name, job_title: user?.job_title }} onFinish={handleSaveProfile}>
                <Row gutter={16}>
                  <Col span={8}><Form.Item name="first_name"  label="First Name"  rules={[{ required: true, message: 'Required' }]}><Input placeholder="First name" /></Form.Item></Col>
                  <Col span={8}><Form.Item name="middle_name" label="Middle Name"><Input placeholder="Middle name" /></Form.Item></Col>
                  <Col span={8}><Form.Item name="last_name"  label="Last Name"  rules={[{ required: true, message: 'Required' }]}><Input placeholder="Last name" /></Form.Item></Col>
                </Row>
                <Form.Item name="display_name" label="Display Name">
                  <Input placeholder="e.g. Rama, Teja K" maxLength={100} />
                </Form.Item>
                <Form.Item name="job_title" label="Job Title"><Input placeholder="e.g. Senior Engineer, Product Manager" disabled /></Form.Item>
                <Row gutter={16}>
                  <Col span={12}><Form.Item label="Email"><Input value={user?.email} disabled prefix={<MailOutlined />} /></Form.Item></Col>
                  <Col span={12}><Form.Item label="Role"><Input value={ROLE_LABEL[user?.role]} disabled prefix={<IdcardOutlined />} /></Form.Item></Col>
                </Row>
                <Form.Item style={{ marginBottom: 0 }}>
                  <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={savingProfile} style={{ borderRadius: 8 }}>Save Changes</Button>
                </Form.Item>
              </Form>
            </Card>

            <Card title={<Space><LockOutlined style={{ color: '#4f46e5' }} /><span>Change Password</span></Space>} style={{ borderRadius: 14, border: 'none', boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}>
              <Form form={pwForm} layout="vertical" onFinish={handleChangePassword}>
                <Form.Item name="current_password" label="Current Password" rules={[{ required: true, message: 'Required' }]}><Input.Password placeholder="Enter current password" /></Form.Item>
                <Divider style={{ margin: '4px 0 16px' }} />
                <Row gutter={16}>
                  <Col span={12}><Form.Item name="new_password" label="New Password" rules={[{ required: true, message: 'Required' },{ min: 8, message: 'At least 8 characters' }]}><Input.Password placeholder="New password" /></Form.Item></Col>
                  <Col span={12}><Form.Item name="confirm_password" label="Confirm New Password" rules={[{ required: true, message: 'Required' }]}><Input.Password placeholder="Confirm new password" /></Form.Item></Col>
                </Row>
                <Form.Item style={{ marginBottom: 0 }}>
                  <Button type="primary" htmlType="submit" icon={<LockOutlined />} loading={savingPw} style={{ borderRadius: 8 }}>Update Password</Button>
                </Form.Item>
              </Form>
            </Card>
          </Space>
        </Col>
      </Row>
    </Space>
  );
}
