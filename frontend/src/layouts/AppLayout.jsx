import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Avatar, Dropdown, Typography, Space } from 'antd';
import {
  UserOutlined, TeamOutlined, BarChartOutlined,
  FileTextOutlined, SyncOutlined, CheckSquareOutlined,
  TrophyOutlined, LogoutOutlined, MenuFoldOutlined, MenuUnfoldOutlined,
  DashboardOutlined, SafetyOutlined, UsergroupAddOutlined, ProfileOutlined,
  WarningOutlined, NotificationOutlined,
} from '@ant-design/icons';
import useAuthStore from '../store/authStore';
import { logout } from '../api/auth';
import NotificationBell from '../components/shared/NotificationBell';
import FeedbackButton from '../components/shared/FeedbackButton';
import AnnouncementBanner from '../components/shared/AnnouncementBanner';

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

const ROLE_LABEL = {
  SUPER_ADMIN: 'Super Admin',
  HR_ADMIN:    'HR Admin',
  MANAGER:     'Manager',
  EMPLOYEE:    'Employee',
};

function navItems(role) {
  const all = [];

  if (role === 'SUPER_ADMIN') {
    all.push(
      { key: '/admin/users',  icon: <UserOutlined />,   label: 'Users' },
      { key: '/admin/org',    icon: <TeamOutlined />,   label: 'Org Hierarchy' },
      { key: '/admin/audit',  icon: <SafetyOutlined />, label: 'Audit Logs' },
    );
  }

  if (['HR_ADMIN', 'SUPER_ADMIN'].includes(role)) {
    all.push(
      { key: '/hr/cycles',        icon: <SyncOutlined />,         label: 'Cycles' },
      { key: '/hr/templates',     icon: <FileTextOutlined />,     label: 'Templates' },
      { key: '/hr/dashboard',     icon: <BarChartOutlined />,     label: 'HR Dashboard' },
      { key: '/hr/reports',       icon: <TrophyOutlined />,       label: 'View Reports' },
      { key: '/hr/announcements', icon: <NotificationOutlined />, label: 'Announcements' },
    );
  }

  if (['MANAGER', 'SUPER_ADMIN'].includes(role)) {
    all.push(
      { key: '/manager/dashboard',   icon: <DashboardOutlined />,    label: 'Team Dashboard' },
      { key: '/manager/tasks',       icon: <CheckSquareOutlined />,  label: 'My Reviews' },
      { key: '/manager/nominations', icon: <UsergroupAddOutlined />, label: 'Approve Nominations' },
    );
  }

  if (['EMPLOYEE', 'MANAGER', 'HR_ADMIN', 'SUPER_ADMIN'].includes(role)) {
    all.push(
      { key: '/employee/tasks',       icon: <CheckSquareOutlined />,  label: 'My Tasks' },
      { key: '/employee/nominations', icon: <UsergroupAddOutlined />, label: 'Nominations' },
      { key: '/employee/report',      icon: <TrophyOutlined />,       label: 'My Report' },
    );
  }

  if (['MANAGER', 'HR_ADMIN', 'EMPLOYEE'].includes(role)) {
    all.push(
      { key: '/admin/org', icon: <TeamOutlined />, label: 'Org Hierarchy' },
    );
  }

  return all;
}

const useIsMobile = () => {
  const [mobile, setMobile] = useState(() => window.innerWidth < 768);
  useState(() => {
    const handler = () => setMobile(window.innerWidth < 768);
    window.addEventListener('resize', handler);
    return () => window.removeEventListener('resize', handler);
  });
  return mobile;
};

export default function AppLayout() {
  const isMobile    = useIsMobile();
  const [collapsed,  setCollapsed]  = useState(() => window.innerWidth < 768);
  const [reportOpen, setReportOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const navigate  = useNavigate();
  const location  = useLocation();
  const { user, clearAuth } = useAuthStore();

  const handleLogout = async () => {
    try { await logout(); } catch {}
    clearAuth();
    navigate('/login');
  };

  const userMenu = {
    items: [
      { key: 'profile', icon: <ProfileOutlined />, label: 'My Profile' },
      { type: 'divider' },
      { key: 'report',  icon: <WarningOutlined />, label: 'Report an Issue' },
      { type: 'divider' },
      { key: 'logout',  icon: <LogoutOutlined />,  label: 'Logout', danger: true },
    ],
    onClick: ({ key }) => {
      if (key === 'profile') navigate('/profile');
      if (key === 'report')  setReportOpen(true);
      if (key === 'logout')  handleLogout();
    },
  };

  const selectedKey = navItems(user?.role || '')
    .map((i) => i.key)
    .filter((k) => location.pathname.startsWith(k))
    .sort((a, b) => b.length - a.length)[0] || '';

  const avatarUrl = user?.avatar_url;
  const apiBase   = import.meta.env.VITE_API_BASE_URL || '';
  const avatarSrc = avatarUrl
    ? (avatarUrl.startsWith('http') ? avatarUrl : `${apiBase}${avatarUrl}`)
    : null;
  const initials = user
    ? `${user.first_name?.[0] || ''}${user.last_name?.[0] || ''}`.toUpperCase()
    : '';

  const sidebarWidth  = isMobile ? 0   : (collapsed ? 80  : 264);
  const contentLeft   = isMobile ? 0   : (collapsed ? 80  : 264);

  const sideMenu = (
    <>
      <div style={{
        padding: collapsed && !isMobile ? '12px 8px' : '12px 16px',
        borderBottom: '1px solid #112240', height: 64,
        display: 'flex', alignItems: 'center',
        justifyContent: collapsed && !isMobile ? 'center' : 'flex-start', gap: 10,
      }}>
        <img src="/gamyam360.png" alt="Gamyam 360" style={{ width: 44, height: 44, objectFit: 'contain', flexShrink: 0 }} />
        {(!collapsed || isMobile) && (
          <Text strong style={{ color: '#fff', fontSize: 15, whiteSpace: 'nowrap' }}>
            Gamyam 360° Feedback
          </Text>
        )}
      </div>
      <Menu
        theme="dark"
        mode="inline"
        selectedKeys={[selectedKey]}
        items={navItems(user?.role || '')}
        onClick={({ key }) => { navigate(key); if (isMobile) setDrawerOpen(false); }}
        style={{ borderRight: 0, marginTop: 24 }}
      />
    </>
  );

  return (
    <Layout style={{ minHeight: '100vh', overflow: 'hidden' }}>

      {/* Desktop sidebar */}
      {!isMobile && (
        <Sider
          collapsible collapsed={collapsed} onCollapse={setCollapsed}
          width={264}
          style={{
            background: '#001529',
            position: 'fixed', left: 0, top: 0, bottom: 0,
            height: '100vh', overflowY: 'auto', overflowX: 'hidden', zIndex: 1000,
          }}
          trigger={null}
        >
          {sideMenu}
        </Sider>
      )}

      {/* Mobile drawer */}
      {isMobile && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: drawerOpen ? 1100 : -1,
          pointerEvents: drawerOpen ? 'auto' : 'none',
        }}>
          {/* Backdrop */}
          <div onClick={() => setDrawerOpen(false)} style={{
            position: 'absolute', inset: 0,
            background: drawerOpen ? 'rgba(0,0,0,0.5)' : 'transparent',
            transition: 'background 0.2s',
          }} />
          {/* Drawer panel */}
          <div style={{
            position: 'absolute', left: 0, top: 0, bottom: 0, width: 264,
            background: '#001529', overflowY: 'auto',
            transform: drawerOpen ? 'translateX(0)' : 'translateX(-100%)',
            transition: 'transform 0.25s ease',
          }}>
            {sideMenu}
          </div>
        </div>
      )}

      <Layout style={{ marginLeft: contentLeft, minHeight: '100vh', overflow: 'auto', transition: 'margin-left 0.2s' }}>
        <Header style={{
          background: '#fff', padding: '0 16px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          borderBottom: '1px solid #f0f0f0',
          position: 'fixed', top: 0, right: 0, left: contentLeft,
          zIndex: 999, height: 64, transition: 'left 0.2s',
        }}>
          <Space>
            {isMobile
              ? <MenuUnfoldOutlined onClick={() => setDrawerOpen(true)}  style={{ fontSize: 20, cursor: 'pointer' }} />
              : (collapsed
                  ? <MenuUnfoldOutlined onClick={() => setCollapsed(false)} style={{ fontSize: 18, cursor: 'pointer' }} />
                  : <MenuFoldOutlined   onClick={() => setCollapsed(true)}  style={{ fontSize: 18, cursor: 'pointer' }} />
                )
            }
          </Space>

          <Space size={isMobile ? 12 : 20}>
            <div style={{ marginTop: 6 }}><NotificationBell /></div>
            <Dropdown menu={userMenu} placement="bottomRight">
              <Space style={{ cursor: 'pointer' }}>
                <Avatar size={isMobile ? 36 : 44} src={avatarSrc || undefined} style={{ background: '#1677ff', flexShrink: 0 }}>
                  {!avatarSrc && initials}
                </Avatar>
                {!isMobile && user && (
                  <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, maxWidth: 216 }}>
                    <span style={{
                      fontWeight: 600, fontSize: 17, color: '#262626',
                      whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', lineHeight: 1.4,
                    }}>
                      {user.display_name?.trim() || [user.first_name, user.middle_name, user.last_name].filter(Boolean).join(' ')}
                    </span>
                    <span style={{ fontSize: 14, color: '#8c8c8c', lineHeight: 1.4 }}>
                      {ROLE_LABEL[user.role]}
                    </span>
                  </div>
                )}
              </Space>
            </Dropdown>
          </Space>
        </Header>

        <div style={{ position: 'fixed', top: 64, right: 0, left: contentLeft, zIndex: 998, transition: 'left 0.2s' }}>
          <AnnouncementBanner />
        </div>

        <Content style={{ margin: isMobile ? 12 : 24, minHeight: 280, marginTop: 88 }}>
          <Outlet />
        </Content>
        <FeedbackButton open={reportOpen} onClose={() => setReportOpen(false)} />
      </Layout>
    </Layout>
  );
}
