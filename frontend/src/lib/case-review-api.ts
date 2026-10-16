const apiBaseUrl = import.meta.env.VITE_API_URL ?? ""

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("access_token")
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export type CaseReviewTask = {
  id: string
  status: "pending" | "in_progress" | "cancelled"
  priority: number
  request_note: string | null
  created_at: string
  claimed_at: string | null
  application_id: string
  application_no: string
  matter_name: string
  claimed_by_me: boolean
  user_cancelled: boolean
  model_result_json: { summary?: string; items?: Array<{ material_name: string; reason: string }> } | null
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}/api/v1${path}`, { ...init, headers: { ...authHeaders(), ...init?.headers } })
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new Error(body?.detail ?? "请求失败，请稍后重试")
  return body.data as T
}

export function getCaseReviewTasks() { return request<{ items: CaseReviewTask[]; count: number }>("/staff/review-tasks") }
export function claimCaseReviewTask(taskId: string) { return request<{ id: string; status: string }>(`/staff/review-tasks/${taskId}/claim`, { method: "POST" }) }
export function deleteCancelledCaseReviewTask(taskId: string) { return request<{ id: string; deleted: boolean }>(`/staff/review-tasks/${taskId}`, { method: "DELETE" }) }

export type CaseReviewTaskDetail = {
  id: string
  status: "in_progress" | "completed" | "cancelled"
  request_note: string | null
  created_at: string
  claimed_at: string | null
  reviewer_user_id: string | null
  application_id: string
  application_no: string
  application_status: string
  matter_name: string
  material_summary: string | null
  model_info: { provider?: string; model?: string } | null
  model_result_json: { summary?: string; items?: Array<{ material_name: string; result: string; reason: string; suggested_action?: string | null }> } | null
  documents: Array<{ id: string; original_filename: string; mime_type: string; byte_size: number; document_code: string; material_name: string }>
}

export function getCaseReviewTask(taskId: string) { return request<CaseReviewTaskDetail>(`/staff/review-tasks/${taskId}`) }
export type CaseReviewItemDecision = { material_name: string; decision: "pass" | "reupload"; note: string }
export function completeCaseReviewTask(taskId: string, itemDecisions: CaseReviewItemDecision[], comment = "") {
  return request<{ id: string; status: string; application_status: string; outcome: string }>(`/staff/review-tasks/${taskId}/complete`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ item_decisions: itemDecisions, comment }),
  })
}

export async function openCaseReviewDocument(taskId: string, fileId: string) {
  const response = await fetch(`${apiBaseUrl}/api/v1/staff/review-tasks/${taskId}/documents/${fileId}`, { headers: authHeaders() })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? "无法打开上传文件")
  }
  const url = URL.createObjectURL(await response.blob())
  window.open(url, "_blank", "noopener,noreferrer")
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
