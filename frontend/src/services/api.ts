import axios from 'axios'
import { API_BASE_URL } from './runtime'

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
})

// 请求前 camelCase -> snake_case，响应再转回来
const toSnakeKey = (key: string) => key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`)
const toCamelKey = (key: string) => key.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase())

const convertKeys = <T,>(value: T, convert: (key: string) => string): T => {
  if (Array.isArray(value)) {
    return value.map((item) => convertKeys(item, convert)) as unknown as T
  }
  if (value && typeof value === 'object' && !(value instanceof FormData)) {
    return Object.entries(value as Record<string, unknown>).reduce((acc, [key, val]) => {
      acc[convert(key)] = convertKeys(val, convert)
      return acc
    }, {} as Record<string, unknown>) as unknown as T
  }
  return value
}

api.interceptors.request.use((config) => {
  if (config.data && !(config.data instanceof FormData)) {
    config.data = convertKeys(config.data, toSnakeKey)
  }
  if (config.params) {
    config.params = convertKeys(config.params, toSnakeKey)
  }
  return config
})

api.interceptors.response.use((response) => {
  response.data = convertKeys(response.data, toCamelKey)
  return response
})

// ── 按域导出 ────────────────────────────────────────────────
export const cameraApi = {
  list: () => api.get('/cameras/'),
  scan: (maxIndex = 6) => api.get('/cameras/scan', { params: { maxIndex } }),
  create: (data: unknown) => api.post('/cameras/', data),
  update: (id: string, data: unknown) => api.put(`/cameras/${id}`, data),
  delete: (id: string) => api.delete(`/cameras/${id}`),
}

export const modelApi = {
  list: () => api.get('/models/'),
  create: (data: unknown) => api.post('/models/', data),
  activate: (id: string) => api.post(`/models/${id}/activate`),
  delete: (id: string) => api.delete(`/models/${id}`),
}

export const targetApi = {
  list: () => api.get('/targets/'),
  create: (data: unknown) => api.post('/targets/', data),
  update: (id: string, data: unknown) => api.put(`/targets/${id}`, data),
  delete: (id: string) => api.delete(`/targets/${id}`),
}

export const processApi = {
  list: () => api.get('/processes/'),
  create: (data: unknown) => api.post('/processes/', data),
  update: (id: string, data: unknown) => api.put(`/processes/${id}`, data),
  delete: (id: string) => api.delete(`/processes/${id}`),
}

export const calibrationApi = {
  run: (cameraId?: string | null) => api.post('/calibration/run', { cameraId: cameraId ?? null }),
  current: () => api.get('/calibration/current'),
  list: () => api.get('/calibration/'),
}

/** 标定自检图的直链（PNG，直接给 <img src>，不要走 axios 的 JSON 拦截器）。 */
export const calibrationOverlayUrl = (id?: string | null) =>
  id ? `${API_BASE_URL}/calibration/${id}/overlay` : ''

export const runtimeApi = {
  start: (processId: string, cameraId?: string | null) =>
    api.post('/runtime/start', { processId, cameraId: cameraId ?? null }),
  stop: () => api.post('/runtime/stop'),
  status: () => api.get('/runtime/status'),
}

export const projectorApi = {
  state: () => api.get('/projector/state'),
}

export const recordApi = {
  runs: (limit = 100, status?: string) =>
    api.get('/records/runs', { params: { limit, ...(status ? { status } : {}) } }),
  run: (id: string) => api.get(`/records/runs/${id}`),
  deleteRun: (id: string) => api.delete(`/records/runs/${id}`),
  stats: () => api.get('/records/stats'),
}

// 系统设置：全局引导参数（工序级覆盖见 processApi）。
export const settingsApi = {
  getGuide: () => api.get('/settings/guide'),
  saveGuide: (config: unknown) => api.put('/settings/guide', { config }),
  resetGuide: () => api.delete('/settings/guide'),
}

export const configApi = {
  get: () => api.get('/config'),
}

export default api
