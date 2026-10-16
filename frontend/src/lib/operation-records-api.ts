const apiBaseUrl = import.meta.env.VITE_API_URL ?? ""

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("access_token")
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export type ApplicationOperationRecord = {
  id: string
  application_no: string
  status: string
  created_at: string
  updated_at: string
  matter_name: string
  region_name: string | null
}

export type CaseReviewRecord = {
  id: string
  action: string
  comment: string | null
  created_at: string
  task_status: string
  application_no: string
  matter_name: string
}

export type AuditRecord = {
  id: string
  action: string
  target_type: string
  target_name: string | null
  details_json: Record<string, unknown>
  created_at: string
}

export type OperationRecords = {
  role: "administrator" | "user"
  application_records: ApplicationOperationRecord[]
  case_review_records?: CaseReviewRecord[]
  matter_review_records?: AuditRecord[]
  user_management_records?: AuditRecord[]
}

export async function getOperationRecords(): Promise<OperationRecords> {
  const response = await fetch(`${apiBaseUrl}/api/v1/operation-records`, { headers: authHeaders() })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? "加载记录失败")
  }
  return ((await response.json()) as { data: OperationRecords }).data
}
