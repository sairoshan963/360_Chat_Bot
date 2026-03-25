import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import useAuthStore from '../../store/authStore';
import { googleAuth } from '../../api/auth';
import { roleDashboard } from '../../router/ProtectedRoute';

export default function AuthCallbackPage() {
  const [searchParams] = useSearchParams();
  const navigate       = useNavigate();
  const { setAuth }    = useAuthStore();
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    const code  = searchParams.get('code');
    const error = searchParams.get('error');

    if (error || !code) {
      navigate('/login', { replace: true, state: { error: error || 'Google sign-in was cancelled' } });
      return;
    }

    // Prevent double-exchange caused by React StrictMode double-mounting in dev.
    // Each Google auth code is single-use; sessionStorage persists across remounts.
    const sessionKey = `oauth_exchanged_${code}`;
    if (sessionStorage.getItem(sessionKey)) return;
    sessionStorage.setItem(sessionKey, '1');

    googleAuth(code)
      .then((res) => {
        const { access, refresh, user } = res.data;
        setAuth(access, user, refresh);
        navigate(roleDashboard(user.role), { replace: true });
      })
      .catch((err) => {
        const msg =
          err?.response?.data?.error ||
          err?.response?.data?.detail ||
          err?.message ||
          'Google sign-in failed. Please try again.';
        setErrorMsg(msg);
        setTimeout(() => {
          navigate('/login', { replace: true, state: { error: msg } });
        }, 2500);
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div style={{
      display:        'flex',
      flexDirection:  'column',
      alignItems:     'center',
      justifyContent: 'center',
      height:         '100vh',
      gap:            12,
      background:     '#fff',
      fontFamily:     'Inter, sans-serif',
    }}>
      {errorMsg ? (
        <>
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="12" fill="#fee2e2"/>
            <path d="M12 8v4m0 4h.01" stroke="#ef4444" strokeWidth="2" strokeLinecap="round"/>
          </svg>
          <p style={{ color: '#ef4444', fontWeight: 600, margin: 0 }}>{errorMsg}</p>
          <p style={{ color: '#64748b', fontSize: 13, margin: 0 }}>Redirecting back to login…</p>
        </>
      ) : (
        <>
          <svg width="40" height="40" viewBox="0 0 40 40">
            <circle cx="20" cy="20" r="16" fill="none" stroke="#e2e8f0" strokeWidth="4"/>
            <path d="M20 4 a16 16 0 0 1 16 16" fill="none" stroke="#FF6B1A" strokeWidth="4" strokeLinecap="round">
              <animateTransform attributeName="transform" type="rotate" from="0 20 20" to="360 20 20" dur="0.8s" repeatCount="indefinite"/>
            </path>
          </svg>
          <p style={{ color: '#0f172a', fontWeight: 600, margin: 0 }}>Signing you in…</p>
          <p style={{ color: '#64748b', fontSize: 13, margin: 0 }}>Please wait a moment</p>
        </>
      )}
    </div>
  );
}
