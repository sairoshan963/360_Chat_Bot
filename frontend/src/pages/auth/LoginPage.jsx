import { useState, useEffect } from 'react';
import { useNavigate, Navigate, useLocation } from 'react-router-dom';
import { Form, Input, Alert, Spin } from 'antd';
import { MailOutlined, LockOutlined, LoadingOutlined, ArrowLeftOutlined, CheckCircleOutlined } from '@ant-design/icons';
import useAuthStore from '../../store/authStore';
import { login, forgotPassword, getMe } from '../../api/auth';
import { roleDashboard } from '../../router/ProtectedRoute';
import usePageTitle from '../../hooks/usePageTitle';

const ORANGE = '#FF6B1A';
const NAVY   = '#0f172a';

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" style={{ flexShrink: 0 }}>
      <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.616z"/>
      <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"/>
      <path fill="#FBBC05" d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"/>
      <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 6.29C4.672 4.163 6.656 3.58 9 3.58z"/>
    </svg>
  );
}

export default function LoginPage() {
  usePageTitle('Sign In');
  const [view,         setView]        = useState('login'); // 'login' | 'forgot'
  const [loading,      setLoading]     = useState(false);
  const [error,        setError]       = useState('');
  const [info,         setInfo]        = useState('');
  const [fpLoading,    setFpLoading]   = useState(false);
  const [fpError,      setFpError]     = useState('');
  const [fpSent,       setFpSent]      = useState(false);
  const [devRevealed,  setDevRevealed] = useState(false);
  const [oauthLoading, setOauthLoading] = useState(false);
  const [rippleKey,    setRippleKey]   = useState(0);
  const navigate  = useNavigate();
  const location  = useLocation();
  const { token, setAuth } = useAuthStore();

  useEffect(() => {
    const stateError = location.state?.error;
    if (stateError) setError(stateError);
    const stateMsg = location.state?.message;
    if (stateMsg === 'password_reset') setInfo('Your password has been reset. You may now log in.');
  }, []); // eslint-disable-line react-hooks/exhaustive-deps


  if (token) {
    const user = useAuthStore.getState().user;
    return <Navigate to={roleDashboard(user?.role)} replace />;
  }

  const onFinish = async ({ email, password }) => {
    setLoading(true);
    setError('');
    try {
      const res = await login(email, password);
      // Django simplejwt returns: { access, refresh, user }
      setAuth(res.data.access, res.data.user, res.data.refresh);
      navigate(roleDashboard(res.data.user.role), { replace: true });
    } catch (err) {
      setError(err.response?.data?.detail || err.response?.data?.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  const onForgotFinish = async ({ email }) => {
    setFpLoading(true);
    setFpError('');
    try {
      await forgotPassword(email);
      setFpSent(true);
    } catch (err) {
      setFpError(err.response?.data?.message || 'Something went wrong. Please try again.');
    } finally {
      setFpLoading(false);
    }
  };

  const goToForgot = () => { setView('forgot'); setError(''); setFpError(''); setFpSent(false); };
  const goToLogin  = () => { setView('login');  setFpSent(false); setFpError(''); };
  const triggerRipple = () => setRippleKey((k) => k + 1);

  const handleGoogleLogin = () => {
    const clientId   = import.meta.env.VITE_GOOGLE_CLIENT_ID;
    const origin     = window.location.origin;
    const redirectUri = `${origin}/auth/callback`;

    const params = new URLSearchParams({
      client_id:     clientId,
      redirect_uri:  redirectUri,
      response_type: 'code',
      scope:         'openid email profile',
      access_type:   'online',
      prompt:        'select_account',
    });

    window.location.href = `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
  };

  return (
    <>
      {oauthLoading && (
        <div style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(255,255,255,0.9)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 12,
          zIndex: 9999,
          color: NAVY,
        }}>
          <Spin size="large" />
          <span style={{ fontSize: 14, fontWeight: 500 }}>Signing you in…</span>
        </div>
      )}
      <style>{`
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        @keyframes lp-spin-scale {
          0%   { transform: scale(1)    rotate(0deg); }
          40%  { transform: scale(1.18) rotate(180deg); }
          100% { transform: scale(1)    rotate(360deg); }
        }
        .lp-ripple-wrap {
          display: contents;
          cursor: pointer;
        }
        .lp-logo-spinning {
          animation: lp-spin-scale 0.6s cubic-bezier(0.4, 0, 0.2, 1) forwards;
        }

        @keyframes lp-fadein {
          from { opacity: 0; transform: translateY(12px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes lp-slidein {
          from { opacity: 0; transform: translateX(20px); }
          to   { opacity: 1; transform: translateX(0); }
        }
        @keyframes lp-viewswitch {
          from { opacity: 0; transform: translateY(10px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .lp-view { animation: lp-viewswitch 0.25s ease both; }

        .lp-root {
          display: flex;
          min-height: 100vh;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', sans-serif;
          animation: lp-fadein 0.4s ease both;
        }

        .lp-left {
          flex: 0 0 48%;
          position: relative;
          overflow: hidden;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          padding: 48px 56px;
          background:
            radial-gradient(ellipse 90% 70% at 60% 20%, rgba(255,107,26,0.18) 0%, transparent 55%),
            radial-gradient(ellipse 70% 60% at 20% 85%, rgba(255,107,26,0.10) 0%, transparent 55%),
            linear-gradient(160deg, #0f172a 0%, #111827 60%, #0c1220 100%);
        }

        .lp-left::before {
          content: '';
          position: absolute;
          top: -160px; right: -160px;
          width: 520px; height: 520px;
          border-radius: 50%;
          border: 1px solid rgba(255,107,26,0.10);
          pointer-events: none;
        }
        .lp-left::after {
          content: '';
          position: absolute;
          top: -100px; right: -100px;
          width: 360px; height: 360px;
          border-radius: 50%;
          border: 1px solid rgba(255,107,26,0.07);
          pointer-events: none;
        }

        .lp-grid {
          position: absolute;
          inset: 0;
          background-image: radial-gradient(rgba(255,255,255,0.04) 1px, transparent 1px);
          background-size: 28px 28px;
          pointer-events: none;
        }

        .lp-left-top {
          position: relative;
          z-index: 2;
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .lp-left-top img {
          width: 35px;
          height: 35px;
          object-fit: contain;
        }
        .lp-left-top-name {
          font-size: 15px;
          font-weight: 600;
          color: rgba(255,255,255,0.7);
          letter-spacing: 0.2px;
        }

        .lp-left-mid {
          position: relative;
          z-index: 2;
          flex: 1;
          display: flex;
          flex-direction: column;
          justify-content: center;
          padding: 40px 0;
        }

        .lp-left-logo {
          width: 242px;
          height: 242px;
          object-fit: contain;
          filter: drop-shadow(0 12px 48px rgba(255,107,26,0.4));
        }

        .lp-left-headline {
          font-size: 38px;
          font-weight: 800;
          color: #ffffff;
          line-height: 1.15;
          letter-spacing: -1px;
          margin-bottom: 16px;
        }
        .lp-left-headline em {
          font-style: normal;
          color: ${ORANGE};
        }

        .lp-left-tagline {
          font-size: 15px;
          color: #94a3b8;
          line-height: 1.7;
          max-width: 320px;
        }

        .lp-left-rule {
          width: 40px;
          height: 3px;
          background: ${ORANGE};
          border-radius: 2px;
          margin: 28px 0 20px;
        }
        .lp-left-trust {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 12px;
          color: #475569;
          font-weight: 500;
        }
        .lp-left-trust-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: ${ORANGE};
          flex-shrink: 0;
        }

        .lp-left-bottom {
          position: relative;
          z-index: 2;
          font-size: 13px;
          color: #334155;
        }

        .lp-right {
          flex: 1;
          background: #ffffff;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 64px 80px;
          position: relative;
        }

        .lp-right::before {
          content: '';
          position: absolute;
          left: 0; top: 10%; bottom: 10%;
          width: 1px;
          background: linear-gradient(to bottom, transparent, #f1f5f9 20%, #f1f5f9 80%, transparent);
        }

        .lp-form-inner {
          width: 100%;
          max-width: 380px;
          animation: lp-slidein 0.45s ease both;
        }

        .lp-form-title {
          font-size: 29px;
          font-weight: 800;
          color: ${NAVY};
          letter-spacing: -0.5px;
          margin-bottom: 6px;
        }
        .lp-form-sub {
          font-size: 15px;
          color: #94a3b8;
          margin-bottom: 28px;
        }

        .lp-form-inner .ant-form-item-label > label {
          font-size: 14px !important;
          font-weight: 600 !important;
          color: #374151 !important;
          letter-spacing: 0.1px !important;
        }
        .lp-form-inner .ant-form-item { margin-bottom: 18px; }
        .lp-form-inner .ant-form-item-required::before { display: none !important; }

        .lp-form-inner .ant-input-affix-wrapper {
          height: 48px !important;
          border: 1.5px solid #e5e7eb !important;
          border-radius: 10px !important;
          background: #ffffff !important;
          padding: 0 14px !important;
          transition: border-color 0.15s, box-shadow 0.15s !important;
          box-shadow: 0 1px 2px rgba(0,0,0,0.04) !important;
        }
        .lp-form-inner .ant-input-affix-wrapper:hover {
          border-color: #d1d5db !important;
        }
        .lp-form-inner .ant-input-affix-wrapper:focus-within {
          border-color: ${ORANGE} !important;
          box-shadow: 0 0 0 3px rgba(255,107,26,0.12) !important;
        }
        .lp-form-inner .ant-input {
          font-size: 15px !important;
          color: ${NAVY} !important;
          background: transparent !important;
          padding: 4px 6px !important;
          line-height: 1.5 !important;
        }
        .lp-form-inner .ant-input::placeholder { color: #9ca3af !important; }
        .lp-form-inner .ant-input-suffix .anticon { color: #9ca3af; }

        .lp-form-inner .ant-input:-webkit-autofill,
        .lp-form-inner .ant-input:-webkit-autofill:hover,
        .lp-form-inner .ant-input:-webkit-autofill:focus {
          -webkit-box-shadow: 0 0 0px 1000px #ffffff inset !important;
          -webkit-text-fill-color: ${NAVY} !important;
          transition: background-color 9999s ease-in-out 0s !important;
        }

        .lp-form-inner .ant-form-item-has-error .ant-input-affix-wrapper {
          border-color: #f87171 !important;
          box-shadow: 0 0 0 3px rgba(248,113,113,0.12) !important;
        }
        .lp-form-inner .ant-form-item-explain-error {
          font-size: 12px !important;
          color: #ef4444 !important;
          margin-top: 4px !important;
        }

        .lp-forgot {
          display: flex;
          justify-content: flex-end;
          margin-top: 8px;
          margin-bottom: 24px;
        }
        .lp-forgot a {
          font-size: 14px;
          color: ${ORANGE};
          font-weight: 500;
          text-decoration: none;
          transition: opacity 0.15s;
        }
        .lp-forgot a:hover { opacity: 0.75; }

        .lp-btn-signin {
          width: 100%;
          height: 50px;
          background: ${ORANGE};
          border: none;
          border-radius: 10px;
          font-size: 17px;
          font-weight: 700;
          color: #fff;
          cursor: pointer;
          letter-spacing: 0.2px;
          box-shadow: 0 4px 16px rgba(255,107,26,0.35);
          transition: all 0.15s;
        }
        .lp-btn-signin:hover:not(:disabled) {
          background: #f05e10;
          box-shadow: 0 8px 24px rgba(255,107,26,0.45);
          transform: translateY(-1px);
        }
        .lp-btn-signin:active:not(:disabled) {
          transform: translateY(0);
          box-shadow: 0 2px 8px rgba(255,107,26,0.3);
        }
        .lp-btn-signin:disabled { opacity: 0.6; cursor: not-allowed; }

        .lp-divider {
          display: flex;
          align-items: center;
          gap: 12px;
          margin: 22px 0;
        }
        .lp-divider hr {
          flex: 1;
          border: none;
          border-top: 1px solid #e5e7eb;
        }
        .lp-divider span {
          font-size: 13px;
          color: #9ca3af;
          white-space: nowrap;
          font-weight: 500;
        }

        .lp-btn-google {
          width: 100%;
          height: 50px;
          background: #fff;
          border: 1.5px solid #e5e7eb;
          border-radius: 10px;
          font-size: 15px;
          font-weight: 500;
          color: #374151;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 10px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.05);
          transition: all 0.15s;
        }
        .lp-btn-google:hover {
          border-color: #d1d5db;
          box-shadow: 0 3px 10px rgba(0,0,0,0.08);
        }

        .lp-footer-note {
          font-size: 14px;
          text-align: center;
          margin-top: 24px;
          color: #9ca3af;
        }

        .lp-dev-reveal {
          text-align: center;
          margin-top: 14px;
          font-size: 12px;
          cursor: pointer;
          user-select: none;
          transition: all 0.2s;
        }
        .lp-dev-reveal.hidden {
          color: #d1d5db;
          letter-spacing: 0.3px;
        }
        .lp-dev-reveal.hidden:hover { color: #9ca3af; }
        .lp-dev-reveal.revealed {
          color: ${ORANGE};
          font-weight: 600;
          letter-spacing: 0.3px;
        }

        .lp-back-btn {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          background: none;
          border: none;
          font-size: 14px;
          font-weight: 500;
          color: #64748b;
          cursor: pointer;
          padding: 0;
          margin-bottom: 28px;
          transition: color 0.15s;
        }
        .lp-back-btn:hover { color: ${NAVY}; }

        .lp-success-box {
          text-align: center;
          padding: 16px 0;
        }
        .lp-success-icon {
          font-size: 48px;
          color: #22c55e;
          margin-bottom: 16px;
        }
        .lp-success-title {
          font-size: 22px;
          font-weight: 700;
          color: ${NAVY};
          margin-bottom: 8px;
        }
        .lp-success-sub {
          font-size: 14px;
          color: #64748b;
          line-height: 1.65;
          margin-bottom: 28px;
        }

        @media (max-width: 960px) {
          .lp-left { flex: 0 0 44%; padding: 40px 36px; }
          .lp-right { padding: 48px 48px; }
          .lp-left-headline { font-size: 30px; }
        }
        @media (max-width: 768px) {
          .lp-left { flex: 0 0 40%; padding: 36px 28px; }
          .lp-right { padding: 40px 32px; }
          .lp-left-headline { font-size: 26px; }
          .lp-left-logo { width: 160px; height: 160px; }
        }
        @media (max-width: 540px) {
          .lp-left { display: none; }
          .lp-right { padding: 40px 24px; }
          .lp-right::before { display: none; }
        }
      `}</style>

      <div className="lp-root">

        {/* ══════════ LEFT PANEL ══════════ */}
        <div className="lp-left">
          <div className="lp-grid" />

          {/* Top: small wordmark */}
          <div className="lp-left-top">
            <img src="/gamyam360.png" alt="Gamyam" />
            <span className="lp-left-top-name">Gamyam</span>
          </div>

          {/* Center: logo + tagline */}
          <div className="lp-left-mid">
            <div className="lp-ripple-wrap" onClick={triggerRipple}>
              <img
                key={rippleKey}
                src="/gamyam360.png"
                alt="Gamyam 360"
                className={`lp-left-logo${rippleKey > 0 ? ' lp-logo-spinning' : ''}`}
                style={{ marginBottom: 0 }}
              />
            </div>
            <p style={{
              fontSize: 15,
              color: '#475569',
              letterSpacing: 1.5,
              textTransform: 'uppercase',
              marginTop: 20,
              textAlign: 'center',
              marginLeft: '12%',
              fontWeight: 500,
            }}>
              Performance. Clarity. Growth.
            </p>
          </div>

          {/* Bottom: copyright */}
          <div className="lp-left-bottom" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
            <span>© {new Date().getFullYear()} Gamyam. All rights reserved.</span>
            <span>A Gamyam Product</span>
          </div>
        </div>

        {/* ══════════ RIGHT PANEL ══════════ */}
        <div className="lp-right">
          <div className="lp-form-inner">

            {/* ── LOGIN VIEW ── */}
            {view === 'login' && (
              <div className="lp-view">
                <div className="lp-form-title">Welcome back</div>
                <div className="lp-form-sub">Sign in to your Gamyam 360° account</div>

                {info  && <Alert message={info}  type="success" showIcon closable onClose={() => setInfo('')}  style={{ marginBottom: 24, borderRadius: 8 }} />}
                {error && <Alert message={error} type="error"   showIcon closable onClose={() => setError('')} style={{ marginBottom: 24, borderRadius: 8 }} />}

                <Form layout="vertical" onFinish={onFinish} autoComplete="on">
                  <Form.Item
                    label="Email address"
                    name="email"
                    rules={[
                      { required: true, message: 'Email is required' },
                      { type: 'email',  message: 'Enter a valid email' },
                    ]}
                  >
                    <Input
                      prefix={<MailOutlined style={{ color: '#9ca3af', marginRight: 4 }} />}
                      placeholder="you@company.com"
                      autoComplete="email"
                      size="large"
                    />
                  </Form.Item>

                  <Form.Item
                    label="Password"
                    name="password"
                    rules={[{ required: true, message: 'Password is required' }]}
                    style={{ marginBottom: 0 }}
                  >
                    <Input.Password
                      prefix={<LockOutlined style={{ color: '#9ca3af', marginRight: 4 }} />}
                      placeholder="Enter your password"
                      autoComplete="current-password"
                      size="large"
                    />
                  </Form.Item>

                  <div className="lp-forgot">
                    <button type="button" onClick={goToForgot} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, color: ORANGE, fontWeight: 500, padding: 0 }}>
                      Forgot password?
                    </button>
                  </div>

                  <Form.Item style={{ marginBottom: 0 }}>
                    <button type="submit" className="lp-btn-signin" disabled={loading}>
                      {loading
                        ? <><Spin indicator={<LoadingOutlined style={{ fontSize: 16, color: '#fff', marginRight: 8 }} spin />} />Signing in…</>
                        : 'Sign In'
                      }
                    </button>
                  </Form.Item>
                </Form>

                <div className="lp-divider">
                  <hr /><span>or continue with</span><hr />
                </div>

                <button className="lp-btn-google" onClick={handleGoogleLogin}>
                  <GoogleIcon />
                  Continue with Google
                </button>

                <p className="lp-footer-note">
                  Contact your HR administrator if you need access.
                </p>

                <div
                  className={`lp-dev-reveal ${devRevealed ? 'revealed' : 'hidden'}`}
                  onClick={() => setDevRevealed(true)}
                >
                  {devRevealed
                    ? 'Designed & Developed by Roshan'
                    : 'Tap to know the developer'
                  }
                </div>
              </div>
            )}

            {/* ── FORGOT PASSWORD VIEW ── */}
            {view === 'forgot' && (
              <div className="lp-view">
                <button className="lp-back-btn" onClick={goToLogin}>
                  <ArrowLeftOutlined style={{ fontSize: 13 }} /> Back to Sign In
                </button>

                {fpSent ? (
                  <div className="lp-success-box">
                    <CheckCircleOutlined className="lp-success-icon" />
                    <div className="lp-success-title">Check your inbox</div>
                    <p className="lp-success-sub">
                      If an account with that email exists, a reset link has been sent.<br />It will expire in 1 hour.
                    </p>
                    <button className="lp-btn-signin" onClick={goToLogin}>
                      Back to Sign In
                    </button>
                  </div>
                ) : (
                  <>
                    <div className="lp-form-title">Forgot password?</div>
                    <div className="lp-form-sub">Enter your email and we'll send you a reset link</div>

                    {fpError && <Alert message={fpError} type="error" showIcon closable onClose={() => setFpError('')} style={{ marginBottom: 24, borderRadius: 8 }} />}

                    <Form layout="vertical" onFinish={onForgotFinish} autoComplete="on">
                      <Form.Item
                        label="Email address"
                        name="email"
                        rules={[
                          { required: true, message: 'Email is required' },
                          { type: 'email',  message: 'Enter a valid email' },
                        ]}
                        style={{ marginBottom: 24 }}
                      >
                        <Input
                          prefix={<MailOutlined style={{ color: '#9ca3af', marginRight: 4 }} />}
                          placeholder="you@company.com"
                          autoComplete="email"
                          size="large"
                        />
                      </Form.Item>

                      <Form.Item style={{ marginBottom: 0 }}>
                        <button type="submit" className="lp-btn-signin" disabled={fpLoading}>
                          {fpLoading
                            ? <><Spin indicator={<LoadingOutlined style={{ fontSize: 16, color: '#fff', marginRight: 8 }} spin />} />Sending…</>
                            : 'Send Reset Link'
                          }
                        </button>
                      </Form.Item>
                    </Form>
                  </>
                )}
              </div>
            )}

          </div>
        </div>

      </div>
    </>
  );
}
