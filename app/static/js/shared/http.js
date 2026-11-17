/** One fetch policy: timeout, session expiry and structured errors. */
export async function api(path, {signal, timeout = 10000, ...options} = {}) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener('abort', abort, {once: true});
  if (signal?.aborted) controller.abort();
  const timer = setTimeout(abort, timeout);
  try {
    const response = await fetch(path, {cache: 'no-store', ...options, signal: controller.signal});
    if (response.status === 401 && path !== '/api/login') {
      window.location.replace('/login?expired=1');
      throw new Error('Session expirée');
    }
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(data.error || data.detail || 'Requête impossible');
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
  }
}
