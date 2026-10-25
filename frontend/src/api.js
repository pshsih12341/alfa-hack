class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'include',
    ...options,
    headers: options.body
      ? { 'Content-Type': 'application/json', ...options.headers }
      : options.headers,
  })

  if (!response.ok) {
    let message = 'Не удалось выполнить запрос'

    try {
      const body = await response.json()
      if (typeof body.detail === 'string') {
        message = body.detail
      } else if (Array.isArray(body.detail)) {
        message = body.detail.map((item) => item.msg).filter(Boolean).join('. ') || message
      }
    } catch {
      // У ответа может не быть JSON-тела.
    }

    throw new ApiError(message, response.status)
  }

  return response.status === 204 ? null : response.json()
}

const post = (path, body) =>
  request(path, { method: 'POST', body: JSON.stringify(body) })

const getAdminApplications = ({ from = '', to = '' } = {}) => {
  const query = new URLSearchParams()
  if (from) query.set('dateFrom', from)
  if (to) query.set('dateTo', to)
  const suffix = query.toString() ? `?${query}` : ''
  return request(`/api/admin/applications${suffix}`)
}

export const api = {
  register: (data) => post('/api/users/reg', data),
  login: (phoneNumber) => post('/api/users/login', { phoneNumber }),
  logout: () => request('/api/users/logout', { method: 'POST' }),
  getMe: () => request('/api/users/me'),
  getApplications: () => request('/api/applications'),
  createApplication: (data) => post('/api/applications', data),
  getApplication: (id) => request(`/api/applications/${id}`),
  acceptApplication: (id, data) => post(`/api/applications/${id}/accept`, data),
  acceptOffer: (id, data) => post(`/api/applications/${id}/accept-offer`, data),
  getAdminApplications,
  getAdminApplication: (id) => request(`/api/admin/applications/${id}`),
  completeAdminApplication: (id) =>
    request(`/api/admin/applications/${id}/complete`, { method: 'POST' }),
}

export { ApiError }
