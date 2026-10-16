export type FinishedMatterVersion = {
  version_id: string
  version_no: number
  status: "finished"
  published_at: string | null
  source_checked_at: string | null
  config_revision: number
  matter_id: string
  code: string
  official_code: string | null
  name: string
  is_active: boolean
  region_code: string
  region_name: string
  description: string | null
  location_name: string | null
  address: string | null
  phone: string | null
  material_count: number
  acquisition_method_count: number
}

const apiBaseUrl = import.meta.env.VITE_API_URL ?? ""

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("access_token")
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function getFinishedMatterVersions(keyword = ""): Promise<FinishedMatterVersion[]> {
  const search = new URLSearchParams()
  if (keyword.trim()) search.set("q", keyword.trim())
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/finished?${search.toString()}`, {
    headers: authHeaders(),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? "已发布事项加载失败")
  }
  return ((await response.json()) as { data: { items: FinishedMatterVersion[] } }).data.items
}

export async function createDraftFromFinishedVersion(version: FinishedMatterVersion): Promise<{ version_id: string; version_no: number; status: "draft" }> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/${version.version_id}/create-draft`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ expected_config_revision: version.config_revision }),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? "创建事项草稿失败")
  }
  return ((await response.json()) as { data: { version_id: string; version_no: number; status: "draft" } }).data
}

export async function disableMatter(version: FinishedMatterVersion): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/${version.version_id}/disable`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ expected_config_revision: version.config_revision }),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? "禁用事项失败")
  }
}
