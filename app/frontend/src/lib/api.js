const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  if (res.status === 204) return null
  return res.json()
}

// Articles
export const getArticles = (params = {}) => {
  const qs = new URLSearchParams(
    Object.fromEntries(Object.entries(params).filter(([, v]) => v != null && v !== ''))
  ).toString()
  return request(`/articles${qs ? `?${qs}` : ''}`)
}

export const getStats = () => request('/articles/stats')

export const refreshFeeds = () =>
  request('/articles/refresh', { method: 'POST' })

export const toggleReadLater = (id) =>
  request(`/articles/${id}/read-later`, { method: 'POST' })

export const markRead = (id) =>
  request(`/articles/${id}/read`, { method: 'POST' })

export const setFeedback = (id, rating) =>
  request(`/articles/${id}/feedback?rating=${encodeURIComponent(rating)}`, { method: 'POST' })

export const summarizeArticle = (id, refresh = false) =>
  request(`/articles/${id}/summarize${refresh ? '?refresh=true' : ''}`, { method: 'POST' })

// Feeds
export const getFeeds = () => request('/feeds')

export const createFeed = (data) =>
  request('/feeds', { method: 'POST', body: JSON.stringify(data) })

export const updateFeed = (id, data) =>
  request(`/feeds/${id}`, { method: 'PUT', body: JSON.stringify(data) })

export const deleteFeed = (id) =>
  request(`/feeds/${id}`, { method: 'DELETE' })

// Profile
export const getProfile = () => request('/interests')

export const updateProfile = (data) =>
  request('/interests', { method: 'PUT', body: JSON.stringify(data) })

// Blocks
export const getBlocks = () => request('/blocks')

export const createBlock = (data) =>
  request('/blocks', { method: 'POST', body: JSON.stringify(data) })

export const deleteBlock = (id) =>
  request(`/blocks/${id}`, { method: 'DELETE' })
