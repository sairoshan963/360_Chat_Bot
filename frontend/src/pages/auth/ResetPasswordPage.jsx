import { useState, useEffect } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import { Form, Input, Button, Card, Typography, Alert, Space } from 'antd';
import { LockOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { resetPassword } from '../../api/auth';
import usePageTitle from '../../hooks/usePageTitle';

const { Title, Text } = Typography;

export default function ResetPasswordPage() {
  usePageTitle('Reset Password');
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState('');
  const token = searchParams.get('token') || '';

  useEffect(() => {
    if (!token) setError('Invalid or missing reset token. Please request a new link.');
  }, [token]);

  const onFinish = async ({ new_password }) => {
    setLoading(true);
    setError('');
    try {
      await resetPassword(token, new_password);
      navigate('/login', { state: { message: 'password_reset' } });
    } catch (err) {
      setError(err.response?.data?.message || 'Reset failed. The link may have expired.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', background: 'linear-gradient(135deg,#001529 0%,#0050b3 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <Card style={{ width: 420, borderRadius: 12, boxShadow: '0 8px 32px rgba(0,0,0,0.3)' }}>
        <Space direction="vertical" size={20} style={{ width: '100%' }}>
          <div style={{ textAlign: 'center' }}>
            <Title level={3} style={{ margin: 0, color: '#1677ff' }}>Set New Password</Title>
            <Text type="secondary">Enter your new password below</Text>
          </div>

          {error && <Alert message={error} type="error" showIcon closable onClose={() => setError('')} />}

          <Form layout="vertical" onFinish={onFinish} autoComplete="off" size="large">
            <Form.Item name="new_password" rules={[{ required: true, message: 'Password is required' }, { min: 8, message: 'At least 8 characters' }]}>
              <Input.Password prefix={<LockOutlined />} placeholder="New password (min 8 characters)" />
            </Form.Item>
            <Form.Item name="confirm_password"
              dependencies={['new_password']}
              rules={[
                { required: true, message: 'Please confirm your password' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('new_password') === value) return Promise.resolve();
                    return Promise.reject(new Error('Passwords do not match'));
                  },
                }),
              ]}>
              <Input.Password prefix={<LockOutlined />} placeholder="Confirm new password" />
            </Form.Item>
            <Form.Item style={{ marginBottom: 8 }}>
              <Button type="primary" htmlType="submit" block loading={loading} disabled={!token}>
                Reset Password
              </Button>
            </Form.Item>
          </Form>

          <div style={{ textAlign: 'center' }}>
            <Link to="/login"><Text><ArrowLeftOutlined /> Back to Login</Text></Link>
          </div>
        </Space>
      </Card>
    </div>
  );
}
