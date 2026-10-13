const apiBaseUrl = import.meta.env.VITE_API_URL ?? ""

type CreateApplicationInput = {
  matterId: string
  matterVersionId: string
}

type CreatedApplication = {
  id: string
  application_no: string
  matter_version_id: string
  status: string
}

export async function createApplication({ matterId, matterVersionId }: CreateApplicationInput): Promise<CreatedApplication> {
  const token = localStorage.getItem("access_token")
  const response = await fetch(`${apiBaseUrl}/api/v1/applications`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ matter_id: matterId, matter_version_id: matterVersionId }),
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? "创建办件失败，请稍后重试")
  }
  return ((await response.json()) as { data: CreatedApplication }).data
}
