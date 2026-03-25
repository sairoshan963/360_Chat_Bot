import axios from 'axios';

// Django API base is /api/v1/
const baseURL = import.meta.env.VITE_API_BASE_URL
  ? `${import.meta.env.VITE_API_BASE_URL.replace(/\/$/, '')}/api/v1`
  : '/api/v1';

const api = axios.create({
  baseURL,
  headers: { 'Content-Type': 'application/json' },
});

// Retry logic for transient failures
const retryConfig = {
  maxRetries: 3,
  retryDelay: 1000,
  retryableStatuses: [408, 429, 500, 502, 503, 504],
};

let requestCount = 0;

// Attach JWT on every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  config.metadata = { startTime: Date.now() };
  return config;
});

// Retry on transient failures + handle token refresh
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const config = err.config;
    if (!config || !config.metadata) return Promise.reject(err);

    config.metadata.retryCount = config.metadata.retryCount || 0;

    // 401 → try token refresh first, then redirect
    if (err.response?.status === 401 && !config._retry) {
      config._retry = true;
      
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken && !window.location.pathname.includes('/login')) {
        try {
          const response = await axios.post(`${baseURL}/auth/refresh/`, {
            refresh: refreshToken
          });
          
          if (response.data.success) {
            localStorage.setItem('access_token', response.data.access);
            config.headers.Authorization = `Bearer ${response.data.access}`;
            return api(config); // Retry original request
          }
        } catch (refreshError) {
          // Refresh failed, clear tokens and redirect
        }
      }
      
      // Clear auth and redirect if refresh failed or no refresh token
      if (!window.location.pathname.includes('/login')) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        window.location.href = '/login';
      }
      return Promise.reject(err);
    }

    // Retry on transient failures (only for safe methods)
    if (
      config.metadata.retryCount < retryConfig.maxRetries &&
      retryConfig.retryableStatuses.includes(err.response?.status) &&
      ['GET', 'HEAD', 'OPTIONS'].includes(config.method?.toUpperCase())
    ) {
      config.metadata.retryCount++;
      const delay = retryConfig.retryDelay * Math.pow(2, config.metadata.retryCount - 1);
      await new Promise((resolve) => setTimeout(resolve, delay));
      return api(config);
    }

    return Promise.reject(err);
  }
);

export default api;
