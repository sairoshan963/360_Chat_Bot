import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { RequireAuth, RequireRole, roleDashboard } from './ProtectedRoute';
import useAuthStore from '../store/authStore';

import LoginPage           from '../pages/auth/LoginPage';
import AuthCallbackPage    from '../pages/auth/AuthCallbackPage';
import ResetPasswordPage   from '../pages/auth/ResetPasswordPage';
import UnauthorizedPage    from '../pages/auth/UnauthorizedPage';
import ForgotPasswordPage  from '../pages/auth/ForgotPasswordPage';
import AppLayout        from '../layouts/AppLayout';

import UsersPage           from '../pages/admin/UsersPage';
import OrgPage             from '../pages/admin/OrgPage';
import AuditPage           from '../pages/admin/AuditPage';
import ChatAnalyticsPage   from '../pages/admin/ChatAnalyticsPage';

import CyclesPage       from '../pages/hr/CyclesPage';
import CycleDetailPage  from '../pages/hr/CycleDetailPage';
import CreateCyclePage  from '../pages/hr/CreateCyclePage';
import TemplatesPage    from '../pages/hr/TemplatesPage';
import CreateTemplatePage from '../pages/hr/CreateTemplatePage';
import EditTemplatePage   from '../pages/hr/EditTemplatePage';
import HrDashboardPage    from '../pages/hr/HrDashboardPage';
import ViewReportsPage    from '../pages/hr/ViewReportsPage';
import AnnouncementsPage  from '../pages/hr/AnnouncementsPage';
import EmployeeReportPage from '../pages/hr/EmployeeReportPage';

import ManagerDashboardPage    from '../pages/manager/ManagerDashboardPage';
import ManagerTasksPage        from '../pages/manager/ManagerTasksPage';
import ManagerNominationsPage  from '../pages/manager/ManagerNominationsPage';

import EmployeeTasksPage from '../pages/employee/EmployeeTasksPage';
import FeedbackFormPage  from '../pages/employee/FeedbackFormPage';
import NominationsPage   from '../pages/employee/NominationsPage';
import MyReportPage      from '../pages/employee/MyReportPage';

import ProfilePage from '../pages/shared/ProfilePage';
import ChatPage    from '../pages/shared/ChatPage';

function RootRedirect() {
  const user = useAuthStore((s) => s.user);
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={roleDashboard(user.role)} replace />;
}

export default function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public */}
        <Route path="/login"            element={<LoginPage />} />
        <Route path="/forgot-password"  element={<ForgotPasswordPage />} />
        <Route path="/auth/callback"    element={<AuthCallbackPage />} />
        <Route path="/reset-password"   element={<ResetPasswordPage />} />
        <Route path="/unauthorized"     element={<UnauthorizedPage />} />
        <Route path="/"               element={<RootRedirect />} />

        {/* Protected */}
        <Route element={<RequireAuth><AppLayout /></RequireAuth>}>

          {/* Super Admin */}
          <Route path="/admin/users"
            element={<RequireRole roles={['SUPER_ADMIN']}><UsersPage /></RequireRole>} />
          <Route path="/admin/org"
            element={<RequireRole roles={['SUPER_ADMIN','HR_ADMIN','MANAGER','EMPLOYEE']}><OrgPage /></RequireRole>} />
          <Route path="/admin/audit"
            element={<RequireRole roles={['SUPER_ADMIN']}><AuditPage /></RequireRole>} />
          <Route path="/admin/chat-analytics"
            element={<RequireRole roles={['SUPER_ADMIN','HR_ADMIN']}><ChatAnalyticsPage /></RequireRole>} />

          {/* HR Admin */}
          <Route path="/hr/cycles"
            element={<RequireRole roles={['HR_ADMIN','SUPER_ADMIN']}><CyclesPage /></RequireRole>} />
          <Route path="/hr/cycles/new"
            element={<RequireRole roles={['HR_ADMIN','SUPER_ADMIN']}><CreateCyclePage /></RequireRole>} />
          <Route path="/hr/cycles/:id"
            element={<RequireRole roles={['HR_ADMIN','SUPER_ADMIN']}><CycleDetailPage /></RequireRole>} />
          <Route path="/hr/templates"
            element={<RequireRole roles={['HR_ADMIN','SUPER_ADMIN']}><TemplatesPage /></RequireRole>} />
          <Route path="/hr/templates/new"
            element={<RequireRole roles={['HR_ADMIN','SUPER_ADMIN']}><CreateTemplatePage /></RequireRole>} />
          <Route path="/hr/templates/:id/edit"
            element={<RequireRole roles={['HR_ADMIN','SUPER_ADMIN']}><EditTemplatePage /></RequireRole>} />
          <Route path="/hr/dashboard"
            element={<RequireRole roles={['HR_ADMIN','SUPER_ADMIN']}><HrDashboardPage /></RequireRole>} />
          <Route path="/hr/reports"
            element={<RequireRole roles={['HR_ADMIN','SUPER_ADMIN']}><ViewReportsPage /></RequireRole>} />
          <Route path="/hr/announcements"
            element={<RequireRole roles={['HR_ADMIN','SUPER_ADMIN']}><AnnouncementsPage /></RequireRole>} />

          {/* Manager */}
          <Route path="/manager/dashboard"
            element={<RequireRole roles={['MANAGER','SUPER_ADMIN']}><ManagerDashboardPage /></RequireRole>} />
          <Route path="/manager/tasks"
            element={<RequireRole roles={['MANAGER','SUPER_ADMIN']}><ManagerTasksPage /></RequireRole>} />
          <Route path="/manager/nominations"
            element={<RequireRole roles={['MANAGER','SUPER_ADMIN']}><ManagerNominationsPage /></RequireRole>} />

          {/* Employee */}
          <Route path="/employee/tasks"
            element={<RequireRole roles={['EMPLOYEE','MANAGER','HR_ADMIN','SUPER_ADMIN']}><EmployeeTasksPage /></RequireRole>} />
          <Route path="/employee/tasks/:id"
            element={<RequireRole roles={['EMPLOYEE','MANAGER','HR_ADMIN','SUPER_ADMIN']}><FeedbackFormPage /></RequireRole>} />
          <Route path="/employee/nominations"
            element={<RequireRole roles={['EMPLOYEE','MANAGER','HR_ADMIN','SUPER_ADMIN']}><NominationsPage /></RequireRole>} />
          <Route path="/employee/report"
            element={<RequireRole roles={['EMPLOYEE','MANAGER','HR_ADMIN','SUPER_ADMIN']}><MyReportPage /></RequireRole>} />

          {/* Cross-role */}
          <Route path="/reports/:cycleId/:employeeId"
            element={<RequireRole roles={['SUPER_ADMIN','HR_ADMIN','MANAGER']}><EmployeeReportPage /></RequireRole>} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/chat"    element={<ChatPage />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
