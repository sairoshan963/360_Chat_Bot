import api from './client';

export const sendMessage = (message, sessionId, displayMessage = null) => {
  const payload = { message, session_id: sessionId || '' };
  if (displayMessage && displayMessage !== message) payload.display_message = displayMessage;
  return api.post('/chat/message/', payload);
};

/**
 * Send a message via the SSE streaming endpoint.
 * Calls onChunk(text) for each LLM text chunk and onDone(payload) when complete.
 * Returns a promise that resolves when the stream closes.
 */
export const sendMessageStream = async (message, sessionId, displayMessage, onChunk, onDone) => {
  const token = localStorage.getItem('access_token');
  const baseURL = import.meta.env.VITE_API_BASE_URL
    ? `${import.meta.env.VITE_API_BASE_URL.replace(/\/$/, '')}/api/v1`
    : '/api/v1';

  const body = { message, session_id: sessionId || '' };
  if (displayMessage && displayMessage !== message) body.display_message = displayMessage;

  const res = await fetch(`${baseURL}/chat/stream/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.message || 'Stream request failed'), { status: res.status, data: err });
  }

  const reader  = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer    = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop(); // keep any incomplete event
    for (const part of parts) {
      for (const line of part.split('\n')) {
        if (!line.startsWith('data: ')) continue;
        try {
          const event = JSON.parse(line.slice(6));
          if (event.type === 'chunk') onChunk(event.text);
          if (event.type === 'done')  onDone(event);
        } catch (_) { /* ignore malformed lines */ }
      }
    }
  }
};

export const confirmAction = (sessionId, confirmed) =>
  api.post('/chat/confirm/', { session_id: sessionId, confirmed });

export const getChatHistory = (sessionId = null) =>
  api.get('/chat/history/', sessionId ? { params: { session_id: sessionId } } : {});

export const getChatSessions = () =>
  api.get('/chat/sessions/');

export const getSessionState = () =>
  api.get('/chat/session/');

export const discardSession = () =>
  api.delete('/chat/session/');

export const getChatAnalytics = (days = 30) =>
  api.get('/chat/analytics/', { params: { days } });

export const deleteSession = (sessionId) =>
  api.delete(`/chat/sessions/${sessionId}/`);

export const renameSession = (sessionId, title) =>
  api.patch(`/chat/sessions/${sessionId}/`, { title });

export const uploadChatFile = (file) => {
  const formData = new FormData();
  formData.append('file', file);
  return api.post('/chat/upload/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};
