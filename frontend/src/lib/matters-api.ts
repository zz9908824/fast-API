export type MatterCard = {
  id: string
  code: string
  name: string
  region: string
  description: string | null
  location: string
  checked_at: string | null
  supported: boolean
  material_count: number
  version_id: string
  version_no: number
}

export type MatterDetail = {
  id: string
  name: string
  region_name: string
  description: string | null
  version_id: string
  version_no: number
  location_name: string | null
  address: string | null
  phone: string | null
  opening_hours: string | null
  metadata_json: Record<string, unknown>
  requirements: Array<{
    id: string
    name: string
    requirement_level: "required" | "optional"
    submission_mode: string
    material_type_name: string
  }>
}

type SearchResponse = {
  data: {
    items: MatterCard[]
    count: number
    keyword: string
  }
}

const apiBaseUrl = import.meta.env.VITE_API_URL ?? ""

export async function searchMatters(keyword: string): Promise<SearchResponse["data"]> {
  const params = new URLSearchParams({ q: keyword })
  const response = await fetch(`${apiBaseUrl}/api/v1/matters/search?${params}`)
  if (!response.ok) throw new Error("事项查询失败，请稍后重试")
  const body = (await response.json()) as SearchResponse
  return body.data
}

export async function getMatter(matterId: string): Promise<MatterDetail | null> {
  const response = await fetch(`${apiBaseUrl}/api/v1/matters/${matterId}`)
  if (response.status === 404) return null
  if (!response.ok) throw new Error("事项详情加载失败，请稍后重试")
  return ((await response.json()) as { data: MatterDetail }).data
}
