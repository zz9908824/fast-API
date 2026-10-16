const apiBaseUrl = import.meta.env.VITE_API_URL ?? ""

export type ImportCandidate = {
  matter: { name: string | null; official_code: string | null; description: string | null }
  scope: { acceptance_condition_raw: string | null; channels: string[] }
  source: { title: string | null; publisher: string | null; published_date: string | null }
  location: { name: string | null; address: string | null; phone: string | null; opening_hours: string | null; official_entry_url: string | null }
  materials: Array<{ local_key: string; name: string | null; requirement_level: "required" | "optional" | null; submission_mode: string | null; acquisition_methods: Array<{ title: string | null; method_type: string | null }> }>
  delegation: {
    delegation_allowed: boolean | null
    materials: Array<{ local_key: string; name: string | null; requirement_level: "required" | "optional" | null; submission_mode: string | null }>
  }
  uncertainties: Array<{ field_path: string; kind: string; message: string; blocking: boolean }>
}

export type MatterImportInput = {
  region_code: string
  region_name: string
  source_url: string
  source_kind: "guide" | "policy" | "template" | "faq" | "contact"
  model_provider: "local" | "cloud"
  pasted_text: string
  source_title_override?: string
  import_note?: string
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("access_token")
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function responseError(response: Response, fallback: string): Promise<Error> {
  const body = await response.json().catch(() => null)
  const detail = body?.detail
  if (typeof detail === "string") return new Error(detail)
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") return item
        if (!item || typeof item !== "object") return null
        const location = Array.isArray(item.loc) ? item.loc.filter((part: unknown) => part !== "body").join(" → ") : ""
        return location ? `${location}：${item.msg ?? "输入不符合要求"}` : (item.msg ?? "输入不符合要求")
      })
      .filter(Boolean)
    return new Error(messages.join("；") || fallback)
  }
  if (detail && typeof detail === "object") {
    return new Error((detail as { message?: string }).message ?? JSON.stringify(detail))
  }
  return new Error(fallback)
}

export async function startMatterImport(data: MatterImportInput): Promise<{ id: string; status: string; candidate: ImportCandidate }> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-imports`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(data),
  })
  if (!response.ok) throw await responseError(response, "智能提取失败")
  return ((await response.json()) as { data: { id: string; status: string; candidate: ImportCandidate } }).data
}

export async function uploadMatterImport(data: MatterImportInput, files: File[]): Promise<{ id: string; status: string; candidate: ImportCandidate }> {
  const body = new FormData()
  body.set("region_code", data.region_code)
  body.set("region_name", data.region_name)
  body.set("source_url", data.source_url)
  body.set("source_kind", data.source_kind)
  body.set("model_provider", data.model_provider)
  body.set("pasted_text", data.pasted_text)
  body.set("source_title_override", data.source_title_override ?? "")
  body.set("import_note", data.import_note ?? "")
  files.forEach((file) => body.append("files", file))
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-imports/upload`, {
    method: "POST",
    headers: authHeaders(),
    body,
  })
  if (!response.ok) throw await responseError(response, "文件提取失败")
  return ((await response.json()) as { data: { id: string; status: string; candidate: ImportCandidate } }).data
}

export async function applyMatterImport(jobId: string): Promise<{ matter_version_id: string; status: "draft" }> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-imports/${jobId}/apply`, {
    method: "POST",
    headers: authHeaders(),
  })
  if (!response.ok) throw await responseError(response, "生成草稿事项失败")
  return ((await response.json()) as { data: { matter_version_id: string; status: "draft" } }).data
}
