export type DraftMatterVersion = {
  version_id: string
  version_no: number
  status: "draft"
  config_revision: number
  change_summary: string | null
  metadata_json: Record<string, unknown>
  government_profile_json: Record<string, string>
  processing_steps_json: Array<{ step: string | null; time_limit: string | null; result: string | null; review_standard: string | null }>
  legal_bases_json: string[]
  field_evidence_json: Array<{ field_path: string; page_number: number | null; quote: string }>
  matter_id: string
  matter_code: string
  official_code: string | null
  matter_name: string
  region_name: string
  description: string | null
  location_name: string | null
  location_id: string | null
  source_id: string | null
  address: string | null
  phone: string | null
  opening_hours: string | null
  official_entry_url: string | null
  location_verification_status: string | null
  location_checked_at: string | null
  source_title: string | null
  source_url: string | null
  source_publisher: string | null
  source_verification_status: string | null
  materials: Array<{
    id: string
    name: string
    requirement_code: string
    level: string
    submission_mode: string
    format_requirements: string | null
    verification_status: string
    material_type_id: string
    material_type: string
  }>
  acquisition_methods: Array<{
    id: string
    requirement_id: string
    material_name: string
    title: string
    method_type: string
    steps: string | null
    entry_url: string | null
    verification_status: string
  }>
  delegation_policy: {
    id: string
    delegation_allowed: boolean
    applicant_must_attend: boolean
    relationship_required: boolean
    allowed_relationships: string[]
    condition_expr: Record<string, unknown>
    questionnaire_required: boolean
    verification_status: string
    source_id: string | null
    materials: Array<{
      id: string
      material_code: string
      name: string
      requirement_level: "required" | "optional"
      submission_mode: "user_upload" | "department_fetch" | "on_site" | "no_submission"
      applicability_expr: Record<string, unknown>
      sort_order: number
      verification_status: string
    }>
  } | null
}

const apiBaseUrl = import.meta.env.VITE_API_URL ?? ""

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("access_token")
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

export async function getDraftMatterVersions(keyword = ""): Promise<DraftMatterVersion[]> {
  const search = new URLSearchParams()
  if (keyword.trim()) search.set("q", keyword.trim())
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/drafts?${search.toString()}`, {
    headers: authHeaders(),
  })
  if (!response.ok) throw new Error("待审核事项加载失败")
  return ((await response.json()) as { data: { items: DraftMatterVersion[] } }).data.items
}

export async function publishMatterVersion(version: DraftMatterVersion): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/${version.version_id}/publish`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ expected_config_revision: version.config_revision }),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? "发布事项失败")
  }
}

export async function updateDraftMatterName(version: DraftMatterVersion, name: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/${version.version_id}/matter-name`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ expected_config_revision: version.config_revision, name }),
  })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "修改事项名称失败")
}

export async function deleteDraftMatterVersion(version: DraftMatterVersion): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/${version.version_id}`, {
    method: "DELETE", headers: authHeaders(),
  })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "删除事项失败")
}

export async function updateGovernmentDetails(version: DraftMatterVersion, data: {
  government_profile: Record<string, string>
  processing_steps: Array<Record<string, unknown>>
  legal_bases: string[]
  field_evidence: Array<Record<string, unknown>>
}): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/${version.version_id}/government-details`, {
    method: "PATCH", headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ expected_config_revision: version.config_revision, ...data }),
  })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "保存政务基础信息失败")
}

export async function confirmGovernmentDetails(version: DraftMatterVersion): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/${version.version_id}/government-details/confirm`, {
    method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ expected_config_revision: version.config_revision }),
  })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "确认政务基础信息失败")
}

export async function saveReviewNote(version: DraftMatterVersion, section: string, note: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/${version.version_id}/review-sections/${section}`, {
    method: "PATCH", headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ expected_config_revision: version.config_revision, note }),
  })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "保存核对备注失败")
}

export async function confirmReviewSection(version: DraftMatterVersion, section: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/${version.version_id}/review-sections/${section}/confirm`, {
    method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ expected_config_revision: version.config_revision }),
  })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "确认核对失败")
}

export async function updateMatterStatusConfig(
  version: DraftMatterVersion,
  data: { acceptance_condition_raw: string; channels: string[]; uncertainties: string[] },
): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/${version.version_id}/status-config`, {
    method: "PATCH", headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ expected_config_revision: version.config_revision, ...data }),
  })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "保存事项状态配置失败")
}

export async function updatePolicySourceConfig(
  version: DraftMatterVersion,
  data: { publisher: string; url: string },
): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/${version.version_id}/source-config`, {
    method: "PATCH", headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ expected_config_revision: version.config_revision, ...data }),
  })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "保存官方来源失败")
}

export async function updateServiceLocationConfig(
  version: DraftMatterVersion,
  data: { name: string; address: string; phone: string; opening_hours: string; official_entry_url: string; verification_status: "pending" | "verified" | "unavailable"; checked_at: string | null; source_id: string | null },
): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/${version.version_id}/location-config`, {
    method: "PATCH", headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ expected_config_revision: version.config_revision, ...data }),
  })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "保存办理地点失败")
}

export async function createMaterialRequirement(version: DraftMatterVersion, data: { material_type_id: string; name: string; requirement_level: "required" | "optional"; format_requirements: string }): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/${version.version_id}/material-requirements`, {
    method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ expected_config_revision: version.config_revision, ...data }),
  })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "新增材料要求失败")
}

export async function updateMaterialRequirement(version: DraftMatterVersion, requirement: DraftMatterVersion["materials"][number]): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/${version.version_id}/material-requirements/${requirement.id}`, {
    method: "PATCH", headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ expected_config_revision: version.config_revision, name: requirement.name, requirement_level: requirement.level, format_requirements: requirement.format_requirements ?? "" }),
  })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "修改材料要求失败")
}

export async function deleteMaterialRequirement(version: DraftMatterVersion, requirementId: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/${version.version_id}/material-requirements/${requirementId}?expected_config_revision=${version.config_revision}`, { method: "DELETE", headers: authHeaders() })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "删除材料要求失败")
}

export type DelegationPolicyPayload = {
  delegation_allowed: boolean
  applicant_must_attend: boolean
  relationship_required: boolean
  allowed_relationships: string[]
  condition_expr: Record<string, unknown>
  questionnaire_required: boolean
  source_id: string | null
  materials: Array<{
    material_code: string
    name: string
    requirement_level: "required" | "optional"
    submission_mode: "user_upload" | "department_fetch" | "on_site" | "no_submission"
    applicability_expr: Record<string, unknown>
  }>
}

export async function updateDelegationPolicy(version: DraftMatterVersion, data: DelegationPolicyPayload): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/${version.version_id}/delegation-policy`, {
    method: "PUT", headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ expected_config_revision: version.config_revision, ...data }),
  })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "保存代办规则失败")
}

export async function confirmDelegationPolicy(version: DraftMatterVersion): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/${version.version_id}/delegation-policy/confirm`, {
    method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ expected_config_revision: version.config_revision }),
  })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "确认代办规则失败")
}

type AcquisitionMethodPayload = {
  requirement_id: string
  method_type: "online_download" | "online_apply" | "in_person" | "self_prepare" | "department_fetch" | "on_site"
  title: string
  steps: string
  entry_url: string
}

export async function createAcquisitionMethod(version: DraftMatterVersion, data: AcquisitionMethodPayload): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/${version.version_id}/acquisition-methods`, {
    method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ expected_config_revision: version.config_revision, ...data }),
  })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "新增材料获取方式失败")
}

export async function updateAcquisitionMethod(version: DraftMatterVersion, methodId: string, data: AcquisitionMethodPayload): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/${version.version_id}/acquisition-methods/${methodId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ expected_config_revision: version.config_revision, ...data }),
  })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "修改材料获取方式失败")
}

export async function deleteAcquisitionMethod(version: DraftMatterVersion, methodId: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/admin/matter-versions/${version.version_id}/acquisition-methods/${methodId}?expected_config_revision=${version.config_revision}`, {
    method: "DELETE", headers: authHeaders(),
  })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "删除材料获取方式失败")
}
