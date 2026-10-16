const apiBaseUrl = import.meta.env.VITE_API_URL ?? ""

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("access_token")
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export type ApplicationRecord = {
  id: string
  application_no: string
  matter_version_id: string
  status: string
  questionnaire_status: string
  is_delegated: boolean
  content_revision: number
  created_at: string
  updated_at: string
  matter_name: string
  region_name: string | null
  latest_check_status?: string | null
  material_summary?: string | null
}

export type Participant = { id: string; participant_code: string; role_code: string; display_name: string | null }
export type ChecklistItem = {
  item_kind: "requirement" | "extra"
  requirement_id: string
  requirement_code: string
  name: string
  requirement_level: "required" | "optional"
  submission_mode: string
  preparation_declaration: "not_ready" | "ready" | "unknown" | null
  uploaded_file_count: number
  files: Array<{ id: string; original_filename: string; mime_type: string; byte_size: number }>
  review_decision: "pass" | "reupload" | "model_pass" | null
  review_note: string | null
  reupload_file_saved: boolean
  review_result: {
    decision?: "pass" | "manual_review"
    summary?: string
    manual_review_required?: boolean
    items?: Array<{ material_name: string; result: string; reason: string; suggested_action?: string | null }>
  } | null
}
export type MaterialReview = {
  id: string
  status: string
  material_summary: string | null
  model_info: { provider?: string; model?: string }
  model_result_json: {
    decision?: "pass" | "manual_review"
    summary?: string
    manual_review_required?: boolean
    items?: Array<{ material_name: string; result: string; reason: string; suggested_action?: string | null }>
  }
  error_code: string | null
  created_at: string
  staff_review?: {
    outcome: "confirmed" | "supplement_required"
    comment: string
    details: { item_decisions?: Array<{ material_name: string; decision: "pass" | "reupload"; note: string }> }
    created_at: string
  } | null
}

type CreateApplicationInput = { matterId: string; matterVersionId: string; createNew?: boolean }
export type CreatedApplication = { id: string; application_no: string; matter_version_id: string; status: string; content_revision: number }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}/api/v1${path}`, {
    ...init,
    headers: { ...authHeaders(), ...init?.headers },
  })
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new Error(body?.detail ?? "请求失败，请稍后重试")
  return body.data as T
}

export function createApplication({ matterId, matterVersionId, createNew = false }: CreateApplicationInput) {
  return request<CreatedApplication>("/applications", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({ matter_id: matterId, matter_version_id: matterVersionId, create_new: createNew }),
  })
}

export function getOpenApplications(matterId: string) {
  return request<{ items: ApplicationRecord[]; count: number }>(`/applications/open?matter_id=${encodeURIComponent(matterId)}`)
}

export function getApplications() { return request<{ items: ApplicationRecord[]; count: number }>("/applications") }
export function updateApplicationDisplayName(id: string, displayName: string, expectedRevision: number) {
  return request<{ display_name: string; content_revision: number }>(`/applications/${id}/display-name`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display_name: displayName, expected_revision: expectedRevision }),
  })
}
export function getApplication(id: string) { return request<ApplicationRecord & { scenario_answers: Record<string, unknown>; matter: { matter_name: string; region_name: string | null } }>(`/applications/${id}`) }
export function getParticipants(id: string) { return request<Participant[]>(`/applications/${id}/participants`) }
export function getChecklist(id: string) { return request<{ items: ChecklistItem[]; content_revision: number }>(`/applications/${id}/checklist`) }
export function getLatestMaterialReview(id: string) { return request<MaterialReview | null>(`/applications/${id}/material-review`) }
export function startMaterialReview(id: string, provider: "local" | "cloud", expectedRevision: number, target?: { materialId: string; itemKind: ChecklistItem["item_kind"] }) {
  return request<{ id: string; status: string; provider: string; decision: "pass" | "manual_review"; application_status: string; result: MaterialReview["model_result_json"] }>(`/applications/${id}/material-review`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, expected_revision: expectedRevision, material_id: target?.materialId, item_kind: target?.itemKind }),
  })
}
export async function openApplicationDocument(applicationId: string, fileId: string) {
  // Open synchronously from the click handler so browsers do not treat the
  // later authenticated blob response as an unsolicited pop-up.
  const previewWindow = window.open("", "_blank")
  const response = await fetch(`${apiBaseUrl}/api/v1/applications/${applicationId}/documents/${fileId}`, { headers: authHeaders() })
  if (!response.ok) {
    previewWindow?.close()
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? "无法预览上传的材料")
  }
  const url = URL.createObjectURL(await response.blob())
  if (previewWindow) previewWindow.location.href = url
  else window.open(url, "_blank", "noopener,noreferrer")
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
export type PreparationPackage = { id: string; package_no: number; content_revision: number; created_at: string; is_current: boolean; result_url?: string }
export function getLatestPreparationPackage(applicationId: string) { return request<PreparationPackage | null>(`/applications/${applicationId}/preparation-packages/latest`) }
export function createPreparationPackage(applicationId: string) { return request<PreparationPackage>(`/applications/${applicationId}/preparation-packages`, { method: "POST" }) }
export async function downloadPreparationPackage(packageId: string, kind: "pdf" | "zip" | "qr") {
  const response = await fetch(`${apiBaseUrl}/api/v1/preparation-packages/${packageId}/${kind}`, { headers: authHeaders() })
  if (!response.ok) { const body = await response.json().catch(() => null); throw new Error(body?.detail ?? "准备包下载失败") }
  const url = URL.createObjectURL(await response.blob())
  if (kind === "qr") return url
  const link = document.createElement("a"); link.href = url; link.download = kind === "pdf" ? "办前准备单.pdf" : "电子材料.zip"; link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
  return null
}
export type DelegationPolicy = {
  delegation_allowed: boolean
  applicant_must_attend: boolean
  relationship_required: boolean
  allowed_relationships: string[]
  questionnaire_required: boolean
  verification_status: string
  is_verified: boolean
}
export function getQuestionnaire(id: string) { return request<{ answers: Record<string, unknown>; show_submission_plan: boolean; delegation_policy: DelegationPolicy; content_revision: number }>(`/applications/${id}/questionnaire`) }

export function saveScenario(id: string, answers: Record<string, unknown>, mode: "draft" | "submit", expectedRevision: number) {
  return request<{ content_revision: number; questionnaire_status: string }>(`/applications/${id}/scenario`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answers, mode, expected_revision: expectedRevision }),
  })
}

export function addParticipant(id: string, displayName: string, expectedRevision: number) {
  return request<{ participant: Participant; content_revision: number }>(`/applications/${id}/participants`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role_code: "applicant", display_name: displayName, identity_payload: {}, expected_revision: expectedRevision }),
  })
}

export function submitQuestionnaire(id: string, data: {
  preparedFor: "self" | "other"
  applicantName: string
  submissionPlan: "applicant" | "agent" | "unknown"
  agentRelationship?: string
  agentName?: string
  expectedRevision: number
}) {
  return request<{
    content_revision: number
    questionnaire_status: "submitted"
    is_delegated: boolean
    delegation_status: "delegated" | "not_delegated" | "pending_confirmation" | "unknown"
  }>(`/applications/${id}/questionnaire`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prepared_for: data.preparedFor, applicant_name: data.applicantName,
      submission_plan: data.submissionPlan, agent_relationship: data.agentRelationship ?? null,
      agent_name: data.agentName ?? null, expected_revision: data.expectedRevision,
    }),
  })
}

export function cancelApplication(id: string) {
  return request<{ id: string; status: string }>(`/applications/${id}/cancel`, { method: "POST" })
}

export function updatePreparation(id: string, requirementId: string, declaration: "not_ready" | "ready" | "unknown", expectedRevision: number) {
  return request<{ content_revision: number }>(`/applications/${id}/preparation-items`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ requirement_id: requirementId, declaration, expected_revision: expectedRevision }),
  })
}

export function updateExtraPreparation(id: string, materialId: string, declaration: "not_ready" | "ready" | "unknown", expectedRevision: number) {
  return request<{ content_revision: number }>(`/applications/${id}/extra-materials/${materialId}`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ declaration, expected_revision: expectedRevision }),
  })
}

export async function uploadApplicationMaterial(
  applicationId: string,
  materialId: string,
  itemKind: ChecklistItem["item_kind"],
  files: File[],
  expectedRevision: number,
): Promise<{ document_id: string; document_version_id: string; file_count: number; content_revision: number }> {
  const body = new FormData()
  body.set("item_kind", itemKind)
  body.set("expected_revision", String(expectedRevision))
  files.forEach((file) => body.append("files", file))
  const response = await fetch(`${apiBaseUrl}/api/v1/applications/${applicationId}/materials/${materialId}/documents`, {
    method: "POST", headers: authHeaders(), body,
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) throw new Error(payload?.detail ?? "上传材料失败")
  return payload.data
}
