const DEFAULT_API_BASE_URL = '/api'

const normalizeBaseUrl = (value: string) => value.replace(/\/+$/, '')

export const API_BASE_URL = normalizeBaseUrl(
  import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL,
)

const isAbsoluteHttpUrl = (value: string) => /^https?:\/\//i.test(value)

export const API_ORIGIN = isAbsoluteHttpUrl(API_BASE_URL)
  ? API_BASE_URL.replace(/\/api\/?$/i, '')
  : window.location.origin

/** 把 /api/xxx 这类相对路径转成可直接给 <img src> 用的绝对地址。 */
export const toAbsoluteApiUrl = (path?: string) => {
  if (!path) return ''
  if (isAbsoluteHttpUrl(path)) return path
  return `${API_ORIGIN}${path.startsWith('/') ? path : `/${path}`}`
}

/** 后端 /static 挂载的是数据目录，抓拍/诊断图走这里。 */
export const toStaticUrl = (relPath?: string | null) =>
  relPath ? toAbsoluteApiUrl(`/static/${relPath}`) : ''
