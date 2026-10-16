import { API_BASE_URL } from "../config"

type ApiEnvelope<T> = { data: T }

export function isLoggedIn() { return Boolean(uni.getStorageSync("access_token")) }
export function authHeaders() {
  const token = uni.getStorageSync("access_token") as string
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function request<T>(path: string, options: UniApp.RequestOptions = {}): Promise<T> {
  const response = await uni.request({
    url: `${API_BASE_URL}${path}`,
    ...options,
    header: { ...authHeaders(), ...(options.header ?? {}) },
  })
  const body = response.data as ApiEnvelope<T> & { detail?: string }
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw new Error(body?.detail || "请求失败，请稍后重试")
  }
  return body.data
}

export function requireLogin(returnUrl?: string) {
  if (isLoggedIn()) return true
  const suffix = returnUrl ? `?returnUrl=${encodeURIComponent(returnUrl)}` : ""
  uni.navigateTo({ url: `/pages/login/index${suffix}` })
  return false
}

export async function uploadFiles(path: string, files: UniApp.ChooseFileSuccessCallbackResultFile[], formData: Record<string, string>) {
  const token = uni.getStorageSync("access_token") as string
  const tasks = files.map((file) => new Promise<unknown>((resolve, reject) => {
    uni.uploadFile({
      url: `${API_BASE_URL}${path}`,
      filePath: file.path,
      name: "files",
      formData,
      header: token ? { Authorization: `Bearer ${token}` } : {},
      success: (result) => {
        const body = JSON.parse(result.data || "{}") as { detail?: string }
        if (result.statusCode >= 200 && result.statusCode < 300) resolve(body)
        else reject(new Error(body.detail || "上传失败"))
      },
      fail: reject,
    })
  }))
  return Promise.all(tasks)
}
