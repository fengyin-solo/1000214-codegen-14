/** 统一请求封装：拼后端地址、带上当前身份、抛网络错误、给页脚留一句可读的说明。 */
const API_BASE = import.meta.env.VITE_API_BASE ?? ''

/** 网络层错误的统一前缀：视图层据此判断「数据失败可重试」。 */
export const NETWORK_ERROR_PREFIX = '接口请求失败'

export interface RequestIdentity {
  operator: string
  role: string
  supplier: string
}

/** 当前请求身份：默认审核管理员，供应商权限视图里切换身份时会更新。 */
let identity: RequestIdentity = { operator: '值班管理员', role: 'reviewer', supplier: '' }

export function setRequestIdentity(next: Partial<RequestIdentity>): void {
  identity = { ...identity, ...next }
}

/** 把当前身份拼进查询参数：中文走 URLSearchParams 自动编码，后端按 _role/_supplier 解析。 */
function withIdentity(path: string): string {
  const params = new URLSearchParams()
  if (identity.operator) params.set('_operator', identity.operator)
  if (identity.role) params.set('_role', identity.role)
  if (identity.supplier) params.set('_supplier', identity.supplier)
  const query = params.toString()
  if (!query) return path
  return `${path}${path.includes('?') ? '&' : '?'}${query}`
}

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  return fetch(withIdentity(url), {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  }).catch((error: unknown) => {
    const detail = error instanceof Error ? error.message : '请求未送达'
    throw new Error(`${NETWORK_ERROR_PREFIX}：${detail}`)
  })
}

/** 读取后端返回的错误说明（FastAPI 的 detail 字段），读不到就给状态码。 */
export async function readError(response: Response): Promise<string> {
  try {
    const payload: unknown = await response.json()
    if (payload && typeof (payload as { detail?: unknown }).detail === 'string') {
      return (payload as { detail: string }).detail
    }
  } catch {
    // 响应体不是 JSON 时走兜底文案
  }
  return `接口返回 ${response.status}，操作未生效`
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) {
    throw new Error(`接口返回 ${response.status}，数据未更新`)
  }
  return (await response.json()) as T
}
