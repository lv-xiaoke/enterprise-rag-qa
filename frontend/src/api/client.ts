let csrf = '';
export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}
export async function request(path: string, options: RequestInit = {}): Promise<Response> {
  const method = options.method ?? 'GET';
  if (!['GET', 'HEAD'].includes(method) && !csrf) {
    const result = await fetch('/api/auth/csrf', {credentials: 'same-origin'});
    if (!result.ok) throw new ApiError('无法初始化安全会话，请刷新后重试', result.status);
    csrf = (await result.json()).csrf_token;
  }
  const headers = new Headers(options.headers);
  if (!['GET', 'HEAD'].includes(method)) headers.set('X-CSRF-Token', csrf);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const response = await fetch(`/api${path}`, {...options, headers, credentials: 'same-origin'});
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401 && path !== '/auth/login') window.dispatchEvent(new Event('auth-expired'));
    throw new ApiError(payload.error?.message ?? `请求失败 (${response.status})`, response.status);
  }
  return response;
}
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  return (await request(path, options)).json();
}
export const jsonBody = (value: unknown) => JSON.stringify(value);
export const errorText = (error: unknown) => error instanceof Error ? error.message : '请求失败，请稍后重试';
