const TOKEN_KEY = 'entrecol_token';
const USER_KEY = 'entrecol_user';

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function getUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY)) || null;
  } catch (e) {
    return null;
  }
}

export function setSession(token, usuario) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(usuario || {}));
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function goToLogin() {
  clearSession();
  window.location.replace('index.html');
}

export function buildQuery(params) {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    search.append(key, value);
  });
  const text = search.toString();
  return text ? '?' + text : '';
}

async function readBody(response) {
  const type = response.headers.get('content-type') || '';
  if (type.includes('application/json')) {
    try {
      return await response.json();
    } catch (e) {
      return null;
    }
  }
  return null;
}

async function request(method, path, options = {}) {
  const headers = { Accept: 'application/json' };
  const token = getToken();
  if (token) headers.Authorization = 'Bearer ' + token;
  const init = { method, headers };
  if (options.json !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(options.json);
  }
  if (options.form) init.body = options.form;
  if (options.pdf) headers.Accept = 'application/pdf';
  let response;
  try {
    response = await fetch('/api' + path + buildQuery(options.params), init);
  } catch (e) {
    throw new ApiError('No fue posible conectar con el servidor', 0, null);
  }
  if (response.status === 401 && !options.public) {
    goToLogin();
    throw new ApiError('Sesión expirada', 401, null);
  }
  if (!response.ok) {
    const data = await readBody(response);
    const message = (data && data.error) || 'Error ' + response.status;
    throw new ApiError(message, response.status, data);
  }
  if (options.pdf) {
    const disposition = response.headers.get('content-disposition') || '';
    const match = disposition.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
    return { blob: await response.blob(), filename: match ? decodeURIComponent(match[1]) : 'reporte.pdf' };
  }
  return readBody(response);
}

export function apiGet(path, params, options) {
  return request('GET', path, { params, ...options });
}

export function apiPost(path, body, options) {
  return request('POST', path, { json: body === undefined ? {} : body, ...options });
}

export function apiPut(path, body) {
  return request('PUT', path, { json: body });
}

export function apiDelete(path) {
  return request('DELETE', path);
}

export function apiUpload(path, file, field = 'archivo') {
  const form = new FormData();
  form.append(field, file);
  return request('POST', path, { form });
}

export function apiFetchPdf(payload) {
  return request('POST', '/reportes/pdf', { json: payload, pdf: true });
}
