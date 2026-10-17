import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { Check, CheckCircle2, ExternalLink, FileText, MapPin, Pencil, Phone, RefreshCw, ShieldCheck, Trash2 } from "lucide-react"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import {
  confirmReviewSection,
  confirmDelegationPolicy,
  confirmGovernmentDetails,
  createAcquisitionMethod,
  createMaterialRequirement,
  deleteAcquisitionMethod,
  deleteDraftMatterVersion,
  deleteMaterialRequirement,
  getDraftMatterVersions,
  publishMatterVersion,
  type DraftMatterVersion,
  updateMatterStatusConfig,
  updatePolicySourceConfig,
  updateServiceLocationConfig,
  updateAcquisitionMethod,
  updateDraftMatterName,
  updateGovernmentDetails,
  updateMaterialRequirement,
  updateDelegationPolicy,
} from "@/lib/matter-review-api"

export const Route = createFileRoute("/_layout/admin/matter-reviews")({
  component: MatterReviews,
})

type StatusEditor = {
  versionId: string
  acceptance: string
  channels: string
  uncertainties: string
}

type SourceEditor = {
  versionId: string
  publisher: string
  url: string
}

type LocationEditor = {
  versionId: string
  name: string
  address: string
  phone: string
  openingHours: string
  guideUrl: string
  verificationStatus: "pending" | "verified" | "unavailable"
  checkedAt: string
  sourceId: string
}

type MaterialEditor = {
  versionId: string
  requirement: DraftMatterVersion["materials"][number]
  name: string
  level: "required" | "optional"
  formatRequirements: string
}

type AcquisitionEditor = {
  versionId: string
  methodId: string | null
  requirementId: string
  methodType: "online_download" | "online_apply" | "in_person" | "self_prepare" | "department_fetch" | "on_site"
  title: string
  steps: string
  entryUrl: string
}

type GovernmentDetailsEditor = {
  versionId: string
  profile: string
  steps: string
  legalBases: string
  evidence: string
}

type DelegationEditor = {
  versionId: string
  delegationAllowed: boolean
  materials: Array<{
    key: string
    name: string
    requirementLevel: "required" | "optional"
    submissionMode: "user_upload" | "department_fetch" | "on_site" | "no_submission"
  }>
}

function MatterReviews() {
  const queryClient = useQueryClient()
  const [statusEditor, setStatusEditor] = useState<StatusEditor | null>(null)
  const [sourceEditor, setSourceEditor] = useState<SourceEditor | null>(null)
  const [locationEditor, setLocationEditor] = useState<LocationEditor | null>(null)
  const [materialEditVersionId, setMaterialEditVersionId] = useState<string | null>(null)
  const [materialEditor, setMaterialEditor] = useState<MaterialEditor | null>(null)
  const [acquisitionEditVersionId, setAcquisitionEditVersionId] = useState<string | null>(null)
  const [acquisitionEditor, setAcquisitionEditor] = useState<AcquisitionEditor | null>(null)
  const [governmentDetailsEditor, setGovernmentDetailsEditor] = useState<GovernmentDetailsEditor | null>(null)
  const [delegationEditor, setDelegationEditor] = useState<DelegationEditor | null>(null)
  const [keyword, setKeyword] = useState("")
  const { data: versions = [], isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: ["draft-matter-versions", keyword],
    queryFn: () => getDraftMatterVersions(keyword),
  })
  const publish = useMutation({
    mutationFn: publishMatterVersion,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["draft-matter-versions"] }),
  })
  const renameMatter = useMutation({
    mutationFn: ({ version, name }: { version: DraftMatterVersion; name: string }) => updateDraftMatterName(version, name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["draft-matter-versions"] }),
  })
  const deleteMatter = useMutation({
    mutationFn: deleteDraftMatterVersion,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["draft-matter-versions"] }),
  })
  const saveGovernmentDetails = useMutation({
    mutationFn: ({ version, editor }: { version: DraftMatterVersion; editor: GovernmentDetailsEditor }) => updateGovernmentDetails(version, {
      government_profile: JSON.parse(editor.profile) as Record<string, string>,
      processing_steps: JSON.parse(editor.steps) as Array<Record<string, unknown>>,
      legal_bases: splitValues(editor.legalBases),
      field_evidence: JSON.parse(editor.evidence) as Array<Record<string, unknown>>,
    }),
    onSuccess: () => {
      setGovernmentDetailsEditor(null)
      queryClient.invalidateQueries({ queryKey: ["draft-matter-versions"] })
    },
  })
  const confirmGovernmentDetailsMutation = useMutation({
    mutationFn: confirmGovernmentDetails,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["draft-matter-versions"] }),
  })
  const saveDelegation = useMutation({
    mutationFn: ({ version, editor }: { version: DraftMatterVersion; editor: DelegationEditor }) => updateDelegationPolicy(version, {
      delegation_allowed: editor.delegationAllowed,
      applicant_must_attend: false,
      relationship_required: false,
      allowed_relationships: [],
      condition_expr: { op: "always" },
      questionnaire_required: editor.delegationAllowed,
      source_id: version.delegation_policy?.source_id ?? version.source_id,
      materials: editor.materials.filter((material) => material.name.trim()).map((material, index) => ({
        material_code: `manual_delegation_${index + 1}_${material.key}`,
        name: material.name.trim(),
        requirement_level: material.requirementLevel,
        submission_mode: material.submissionMode,
        applicability_expr: { op: "always" },
      })),
    }),
    onSuccess: () => {
      setDelegationEditor(null)
      queryClient.invalidateQueries({ queryKey: ["draft-matter-versions"] })
    },
  })
  const confirmDelegation = useMutation({
    mutationFn: confirmDelegationPolicy,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["draft-matter-versions"] }),
  })
  const confirmSection = useMutation({
    mutationFn: ({ version, section }: { version: DraftMatterVersion; section: string }) => confirmReviewSection(version, section),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["draft-matter-versions"] }),
  })
  const saveStatusConfig = useMutation({
    mutationFn: ({ version, editor }: { version: DraftMatterVersion; editor: StatusEditor }) => updateMatterStatusConfig(version, {
      acceptance_condition_raw: editor.acceptance,
      channels: splitValues(editor.channels),
      uncertainties: splitValues(editor.uncertainties),
    }),
    onSuccess: () => {
      setStatusEditor(null)
      queryClient.invalidateQueries({ queryKey: ["draft-matter-versions"] })
    },
  })
  const saveSourceConfig = useMutation({
    mutationFn: ({ version, editor }: { version: DraftMatterVersion; editor: SourceEditor }) => updatePolicySourceConfig(version, editor),
    onSuccess: () => {
      setSourceEditor(null)
      queryClient.invalidateQueries({ queryKey: ["draft-matter-versions"] })
    },
  })
  const saveLocationConfig = useMutation({
    mutationFn: ({ version, editor }: { version: DraftMatterVersion; editor: LocationEditor }) => updateServiceLocationConfig(version, {
      name: editor.name, address: editor.address, phone: editor.phone,
      opening_hours: editor.openingHours, official_entry_url: editor.guideUrl,
      verification_status: editor.verificationStatus,
      checked_at: editor.checkedAt ? new Date(editor.checkedAt).toISOString() : null,
      source_id: editor.sourceId.trim() || null,
    }),
    onSuccess: () => {
      setLocationEditor(null)
      queryClient.invalidateQueries({ queryKey: ["draft-matter-versions"] })
    },
  })
  const manageMaterials = useMutation({
    mutationFn: async ({ action, version, material }: { action: "create" | "delete"; version: DraftMatterVersion; material?: DraftMatterVersion["materials"][number] }) => {
      if (action === "create") {
        const name = window.prompt("材料名称：")
        if (!name?.trim()) return
        const format = window.prompt("材料格式/提交说明（可留空）：") ?? ""
        const typeId = version.materials[0]?.material_type_id
        if (!typeId) throw new Error("当前没有可复用的材料类型，暂不能新增材料")
        await createMaterialRequirement(version, { material_type_id: typeId, name, requirement_level: "required", format_requirements: format })
      } else if (action === "delete" && material) {
        if (!window.confirm(`确认删除材料“${material.name}”吗？`)) return
        await deleteMaterialRequirement(version, material.id)
      }
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["draft-matter-versions"] }),
  })
  const saveMaterial = useMutation({
    mutationFn: ({ version, editor }: { version: DraftMatterVersion; editor: MaterialEditor }) => updateMaterialRequirement(version, {
      ...editor.requirement,
      name: editor.name.trim(),
      level: editor.level,
      format_requirements: editor.formatRequirements,
    }),
    onSuccess: () => {
      setMaterialEditor(null)
      queryClient.invalidateQueries({ queryKey: ["draft-matter-versions"] })
    },
  })
  const saveAcquisitionMethod = useMutation({
    mutationFn: ({ version, editor }: { version: DraftMatterVersion; editor: AcquisitionEditor }) => {
      const data = {
        requirement_id: editor.requirementId,
        method_type: editor.methodType,
        title: editor.title.trim(),
        steps: editor.steps,
        entry_url: editor.entryUrl,
      }
      return editor.methodId
        ? updateAcquisitionMethod(version, editor.methodId, data)
        : createAcquisitionMethod(version, data)
    },
    onSuccess: () => {
      setAcquisitionEditor(null)
      queryClient.invalidateQueries({ queryKey: ["draft-matter-versions"] })
    },
  })
  const deleteAcquisition = useMutation({
    mutationFn: ({ version, methodId }: { version: DraftMatterVersion; methodId: string }) => deleteAcquisitionMethod(version, methodId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["draft-matter-versions"] }),
  })

  const confirmPublish = (version: DraftMatterVersion) => {
    const unfinished = unverifiedReviewSections(version)
    if (unfinished.length) {
      window.alert(`暂时不能发布：${unfinished.join("、")}仍为 pending 或未配置。请逐项核验并点击“确认”。`)
      return
    }
    if (window.confirm(`确认已核对“${version.matter_name}”的官方信息，并发布第 ${version.version_no} 版吗？`)) {
      publish.mutate(version)
    }
  }
  const confirmOneSection = (version: DraftMatterVersion, section: string) => {
    if (window.confirm("确认已核对该部分信息吗？确认后会记录管理员审核时间。")) confirmSection.mutate({ version, section })
  }
  const editStatusConfig = (version: DraftMatterVersion) => {
    const metadata = version.metadata_json
    setStatusEditor({
      versionId: version.version_id,
      acceptance: typeof metadata.acceptance_condition_raw === "string" ? metadata.acceptance_condition_raw : "",
      channels: stringArray(metadata.channels).join("\n"),
      uncertainties: stringArray(metadata.uncertainties).join("\n"),
    })
  }
  const editSourceConfig = (version: DraftMatterVersion) => {
    setSourceEditor({ versionId: version.version_id, publisher: version.source_publisher ?? "", url: version.source_url ?? "" })
  }
  const editLocationConfig = (version: DraftMatterVersion) => {
    setLocationEditor({
      versionId: version.version_id, name: version.location_name ?? "", address: version.address ?? "",
      phone: version.phone ?? "", openingHours: version.opening_hours ?? "", guideUrl: version.official_entry_url ?? "",
      verificationStatus: isLocationStatus(version.location_verification_status),
      checkedAt: dateTimeLocalValue(version.location_checked_at), sourceId: version.source_id ?? "",
    })
  }
  const editMaterial = (version: DraftMatterVersion, material: DraftMatterVersion["materials"][number]) => {
    setMaterialEditor({
      versionId: version.version_id,
      requirement: material,
      name: material.name,
      level: material.level === "optional" ? "optional" : "required",
      formatRequirements: material.format_requirements ?? "",
    })
  }
  const createAcquisition = (version: DraftMatterVersion) => {
    const requirementId = version.materials[0]?.id
    if (!requirementId) return
    setAcquisitionEditor({ versionId: version.version_id, methodId: null, requirementId, methodType: "self_prepare", title: "", steps: "", entryUrl: "" })
  }
  const editAcquisition = (version: DraftMatterVersion, method: DraftMatterVersion["acquisition_methods"][number]) => {
    setAcquisitionEditor({
      versionId: version.version_id, methodId: method.id, requirementId: method.requirement_id,
      methodType: isAcquisitionMethodType(method.method_type), title: method.title,
      steps: method.steps ?? "", entryUrl: method.entry_url ?? "",
    })
  }
  const renameCurrentMatter = (version: DraftMatterVersion) => {
    const originalName = version.matter_name.startsWith(version.region_name)
      ? version.matter_name.slice(version.region_name.length)
      : version.matter_name
    const name = window.prompt(`请输入事项名称（系统将自动添加“${version.region_name}”）`, originalName)?.trim()
    if (name && name !== version.matter_name) renameMatter.mutate({ version, name })
  }
  const deleteCurrentMatter = (version: DraftMatterVersion) => {
    if (window.confirm(`确认删除待审核事项“${version.matter_name}”吗？删除后不能恢复。`)) deleteMatter.mutate(version)
  }
  const editGovernmentDetails = (version: DraftMatterVersion) => {
    setGovernmentDetailsEditor({
      versionId: version.version_id,
      profile: JSON.stringify(version.government_profile_json ?? {}, null, 2),
      steps: JSON.stringify(version.processing_steps_json ?? [], null, 2),
      legalBases: (version.legal_bases_json ?? []).join("\n"),
      evidence: JSON.stringify(version.field_evidence_json ?? [], null, 2),
    })
  }
  const editDelegation = (version: DraftMatterVersion) => {
    const policy = version.delegation_policy
    setDelegationEditor({
      versionId: version.version_id,
      delegationAllowed: policy?.delegation_allowed ?? false,
      materials: (policy?.materials ?? []).map((material) => ({
        key: material.material_code,
        name: material.name,
        requirementLevel: material.requirement_level,
        submissionMode: material.submission_mode,
      })),
    })
  }
  const submitGovernmentDetails = (version: DraftMatterVersion, editor: GovernmentDetailsEditor) => {
    try {
      JSON.parse(editor.profile)
      JSON.parse(editor.steps)
      JSON.parse(editor.evidence)
      saveGovernmentDetails.mutate({ version, editor })
    } catch {
      window.alert("政务基础信息、办理流程和字段原文证据必须是有效的 JSON 格式。")
    }
  }
  if (isLoading) return <p className="text-muted-foreground">正在加载待审核事项…</p>
  if (isError) return <p className="text-destructive">待审核事项加载失败，请确认管理员登录状态和后端服务。</p>

  return <div className="space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-4"><div><h1 className="text-2xl font-bold">事项状态复核</h1><p className="mt-1 text-muted-foreground">核对草稿事项的官方网页、联系信息、办理地点和材料要求；确认无误后发布。</p></div><Button variant="outline" disabled={isFetching} onClick={() => refetch()}><RefreshCw className={`mr-2 size-4 ${isFetching ? "animate-spin" : ""}`} />{isFetching ? "正在刷新…" : "刷新待审核事项"}</Button></header>
    <div className="flex flex-wrap items-center gap-2"><Input className="w-full sm:w-80" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="搜索事项名称、事项编码、地区或办理地点" /><Button variant="outline" disabled={isFetching} onClick={() => refetch()}>查询</Button></div>
    {versions.length === 0 && <div className="rounded-xl border border-dashed p-10 text-center text-muted-foreground">{keyword.trim() ? "未找到匹配的待审核事项。" : "当前没有状态为 draft 的待审核事项。"}</div>}
    {versions.map((version) => <article className="space-y-5 rounded-xl border bg-card p-6" key={version.version_id}>
      <header><div className="flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-2"><Badge variant="secondary">待审核 draft</Badge><span className="text-sm text-muted-foreground">版本 {version.version_no} · 配置修订 {version.config_revision}</span></div><div className="flex gap-2"><Button size="sm" variant="outline" disabled={renameMatter.isPending} onClick={() => renameCurrentMatter(version)}><Pencil className="mr-1 size-3" />修改事项名称</Button><Button size="sm" variant="destructive" disabled={deleteMatter.isPending} onClick={() => deleteCurrentMatter(version)}><Trash2 className="mr-1 size-3" />删除事项</Button></div></div><h2 className="mt-2 text-xl font-semibold">{version.matter_name}</h2><p className="mt-1 text-sm text-muted-foreground">{version.region_name} · 业务办理项编码：{version.official_code ?? "未配置"}</p><p className="mt-3 text-sm text-muted-foreground">{version.description}</p>{(renameMatter.error instanceof Error || deleteMatter.error instanceof Error) && <p className="mt-2 text-sm text-destructive">{renameMatter.error instanceof Error ? renameMatter.error.message : deleteMatter.error instanceof Error ? deleteMatter.error.message : ""}</p>}</header>
      <OfficialGovernmentDetails version={version} editor={governmentDetailsEditor?.versionId === version.version_id ? governmentDetailsEditor : null} onEdit={() => editGovernmentDetails(version)} onChange={setGovernmentDetailsEditor} onCancel={() => setGovernmentDetailsEditor(null)} onSave={(editor) => submitGovernmentDetails(version, editor)} onConfirm={() => confirmGovernmentDetailsMutation.mutate(version)} saving={saveGovernmentDetails.isPending} confirming={confirmGovernmentDetailsMutation.isPending} error={saveGovernmentDetails.error instanceof Error ? saveGovernmentDetails.error.message : confirmGovernmentDetailsMutation.error instanceof Error ? confirmGovernmentDetailsMutation.error.message : null} />
      <ReviewBlock icon={<ShieldCheck className="size-4" />} title="1. 事项状态与适用范围" actions={<Button size="sm" variant="outline" disabled={saveStatusConfig.isPending} onClick={() => editStatusConfig(version)}><Pencil className="mr-1 size-3" />编辑</Button>}><p>当前版本状态：<strong>draft（待管理员审核）</strong>。发布后才会出现在公开事项查询中。</p>{statusEditor?.versionId === version.version_id ? <StatusConfigForm editor={statusEditor!} onChange={setStatusEditor} onCancel={() => setStatusEditor(null)} onSubmit={() => saveStatusConfig.mutate({ version, editor: statusEditor! })} saving={saveStatusConfig.isPending} error={saveStatusConfig.error instanceof Error ? saveStatusConfig.error.message : null} /> : <MetadataSummary metadata={version.metadata_json} />}</ReviewBlock>
      <ReviewBlock icon={<ShieldCheck className="size-4" />} title="2. 是否允许代办与代办材料" actions={<div className="flex gap-2"><Button size="sm" variant="outline" disabled={saveDelegation.isPending} onClick={() => editDelegation(version)}><Pencil className="mr-1 size-3" />编辑</Button><Button size="sm" variant="outline" disabled={confirmDelegation.isPending || !version.delegation_policy || version.delegation_policy.verification_status === "verified"} onClick={() => confirmDelegation.mutate(version)}><Check className="mr-1 size-3" />确认</Button></div>}><DelegationPolicyBlock version={version} editor={delegationEditor?.versionId === version.version_id ? delegationEditor : null} onChange={setDelegationEditor} onCancel={() => setDelegationEditor(null)} onSave={(editor) => saveDelegation.mutate({ version, editor })} saving={saveDelegation.isPending} error={saveDelegation.error instanceof Error ? saveDelegation.error.message : confirmDelegation.error instanceof Error ? confirmDelegation.error.message : null} /></ReviewBlock>
      <ReviewBlock icon={<ExternalLink className="size-4" />} title="3. 官方网页与来源" actions={<div className="flex gap-2"><Button size="sm" variant="outline" disabled={saveSourceConfig.isPending} onClick={() => editSourceConfig(version)}><Pencil className="mr-1 size-3" />编辑</Button><Button size="sm" variant="outline" disabled={confirmSection.isPending} onClick={() => confirmOneSection(version, "source")}><Check className="mr-1 size-3" />确认</Button></div>}><p>{version.source_title ?? "未关联来源"}</p>{sourceEditor?.versionId === version.version_id ? <SourceConfigForm editor={sourceEditor!} onChange={setSourceEditor} onCancel={() => setSourceEditor(null)} onSubmit={() => saveSourceConfig.mutate({ version, editor: sourceEditor! })} saving={saveSourceConfig.isPending} error={saveSourceConfig.error instanceof Error ? saveSourceConfig.error.message : null} /> : <>{version.source_publisher && <p className="mt-1 text-muted-foreground">发布/来源门户：{version.source_publisher}</p>}{version.source_url && <a className="mt-2 inline-flex items-center text-primary hover:underline" href={version.source_url} target="_blank" rel="noreferrer">打开官方网页并人工核对 <ExternalLink className="ml-1 size-3" /></a>}<Status text={version.source_verification_status} /></>}</ReviewBlock>
      <ReviewBlock icon={<MapPin className="size-4" />} title="4. 办理地点与联系电话" actions={<div className="flex gap-2"><Button size="sm" variant="outline" disabled={saveLocationConfig.isPending} onClick={() => editLocationConfig(version)}><Pencil className="mr-1 size-3" />编辑</Button><Button size="sm" variant="outline" disabled={confirmSection.isPending} onClick={() => confirmOneSection(version, "location")}><Check className="mr-1 size-3" />确认</Button></div>}>{locationEditor?.versionId === version.version_id ? <LocationConfigForm editor={locationEditor!} onChange={setLocationEditor} onCancel={() => setLocationEditor(null)} onSubmit={() => saveLocationConfig.mutate({ version, editor: locationEditor! })} saving={saveLocationConfig.isPending} error={saveLocationConfig.error instanceof Error ? saveLocationConfig.error.message : null} /> : <><p>{version.location_name ?? "未配置"}</p><p className="mt-1 text-muted-foreground">{version.address ?? "未配置地址"}</p><p className="mt-1 flex items-center gap-1 text-muted-foreground"><Phone className="size-3" />{version.phone ?? "未配置电话"}</p><p className="mt-1 text-muted-foreground">{version.opening_hours ?? "未配置工作时间"}</p><Status text={version.location_verification_status} /></>}</ReviewBlock>
      <ReviewBlock icon={<FileText className="size-4" />} title="5. 材料要求" actions={<div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => setMaterialEditVersionId(materialEditVersionId === version.version_id ? null : version.version_id)}><Pencil className="mr-1 size-3" />编辑</Button><Button size="sm" variant="outline" disabled={confirmSection.isPending} onClick={() => confirmOneSection(version, "materials")}><Check className="mr-1 size-3" />确认</Button></div>}><p className="mb-3 text-sm text-muted-foreground">核对材料名称、必要性、提交方式、格式说明是否与官方网页一致。</p>{materialEditVersionId === version.version_id && <div className="mb-3"><Button size="sm" disabled={manageMaterials.isPending} onClick={() => manageMaterials.mutate({ action: "create", version })}>新增材料</Button>{manageMaterials.error instanceof Error && <p className="mt-2 text-sm text-destructive">{manageMaterials.error.message}</p>}</div>}{version.materials.length ? <ul className="space-y-2">{version.materials.map((material) => <li className="rounded-md bg-muted p-3 text-sm" key={material.id}><div className="flex flex-wrap items-start justify-between gap-2"><div><span className="font-medium">{material.name}</span><p className="mt-1 text-muted-foreground">{material.level === "required" ? "必要" : "可选"}</p><p className="mt-1 text-muted-foreground">{material.format_requirements}</p></div>{materialEditVersionId === version.version_id && <div className="flex gap-2"><Button size="sm" variant="outline" disabled={saveMaterial.isPending} onClick={() => editMaterial(version, material)}>修改</Button><Button size="sm" variant="destructive" disabled={manageMaterials.isPending} onClick={() => manageMaterials.mutate({ action: "delete", version, material })}>删除</Button></div>}</div></li>)}</ul> : <p>未配置材料要求。</p>}<Status text={aggregateVerificationStatus(version.materials.map((material) => material.verification_status))} /></ReviewBlock>
      <ReviewBlock icon={<FileText className="size-4" />} title="6. 材料获取方式与线上渠道" actions={<div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => setAcquisitionEditVersionId(acquisitionEditVersionId === version.version_id ? null : version.version_id)}><Pencil className="mr-1 size-3" />编辑</Button><Button size="sm" variant="outline" disabled={confirmSection.isPending} onClick={() => confirmOneSection(version, "acquisition")}><Check className="mr-1 size-3" />确认</Button></div>}><p className="mb-3 text-sm text-muted-foreground">核对线上入口、共享数据说明、现场携带要求及其适用范围。</p>{acquisitionEditVersionId === version.version_id && <div className="mb-3"><Button size="sm" disabled={saveAcquisitionMethod.isPending || version.materials.length === 0} onClick={() => createAcquisition(version)}>新增材料获取方式</Button>{version.materials.length === 0 && <p className="mt-2 text-sm text-destructive">请先新增至少一项材料要求，才能关联材料获取方式。</p>}{(saveAcquisitionMethod.error instanceof Error || deleteAcquisition.error instanceof Error) && <p className="mt-2 text-sm text-destructive">{saveAcquisitionMethod.error instanceof Error ? saveAcquisitionMethod.error.message : deleteAcquisition.error instanceof Error ? deleteAcquisition.error.message : ""}</p>}</div>}{version.acquisition_methods.length ? <ul className="space-y-2">{version.acquisition_methods.map((method) => <li className="rounded-md bg-muted p-3 text-sm" key={method.id}><div className="flex flex-wrap items-start justify-between gap-2"><div><span className="font-medium">{method.title}</span><p className="mt-1 text-muted-foreground">关联材料：{method.material_name} · {acquisitionMethodTypeText(method.method_type)}</p><p className="mt-1 text-muted-foreground">{method.steps}</p>{method.entry_url && <a className="mt-1 inline-flex text-primary hover:underline" href={method.entry_url} target="_blank" rel="noreferrer">打开相关链接 <ExternalLink className="ml-1 size-3" /></a>}<Status text={method.verification_status} /></div>{acquisitionEditVersionId === version.version_id && <div className="flex gap-2"><Button size="sm" variant="outline" disabled={saveAcquisitionMethod.isPending} onClick={() => editAcquisition(version, method)}>修改</Button><Button size="sm" variant="destructive" disabled={deleteAcquisition.isPending} onClick={() => { if (window.confirm(`确认删除材料获取方式“${method.title}”吗？`)) deleteAcquisition.mutate({ version, methodId: method.id }) }}>删除</Button></div>}</div></li>)}</ul> : <p>未配置材料获取方式。</p>}<Status text={aggregateVerificationStatus(version.acquisition_methods.map((method) => method.verification_status))} /></ReviewBlock>
      <footer className="border-t pt-5"><p className="mb-3 text-sm text-muted-foreground">确认以上信息已人工核对且可向公众公开后，再发布此事项版本。</p><Button disabled={publish.isPending} onClick={() => confirmPublish(version)}><CheckCircle2 className="mr-2 size-4" />确认核对并发布</Button>{publish.error instanceof Error && <p className="mt-3 text-sm text-destructive">{publish.error.message}</p>}</footer>
    </article>)}
    {materialEditor && <MaterialConfigDialog editor={materialEditor} onChange={setMaterialEditor} onCancel={() => setMaterialEditor(null)} onSubmit={() => {
      const version = versions.find((item) => item.version_id === materialEditor.versionId)
      if (version) saveMaterial.mutate({ version, editor: materialEditor })
    }} saving={saveMaterial.isPending} error={saveMaterial.error instanceof Error ? saveMaterial.error.message : null} />}
    {acquisitionEditor && <AcquisitionConfigDialog editor={acquisitionEditor} materials={(versions.find((item) => item.version_id === acquisitionEditor.versionId)?.materials) ?? []} onChange={setAcquisitionEditor} onCancel={() => setAcquisitionEditor(null)} onSubmit={() => {
      const version = versions.find((item) => item.version_id === acquisitionEditor.versionId)
      if (version) saveAcquisitionMethod.mutate({ version, editor: acquisitionEditor })
    }} saving={saveAcquisitionMethod.isPending} error={saveAcquisitionMethod.error instanceof Error ? saveAcquisitionMethod.error.message : null} />}
  </div>
}

function Status({ text }: { text: string | null }) {
  const statusText = text === "pending" ? "pending（该信息尚未人工核验）" : text === "verified" ? "verified（已人工核验）" : text ?? "未配置"
  return <p className="mt-2 text-xs text-muted-foreground">核验状态：{statusText}</p>
}

function ReviewBlock({ icon, title, actions, children }: { icon: React.ReactNode; title: string; actions: React.ReactNode; children: React.ReactNode }) {
  return <section className="rounded-lg border p-4"><div className="mb-3 flex items-start justify-between gap-3"><h3 className="flex items-center gap-2 font-semibold">{icon}{title}</h3>{actions}</div>{children}</section>
}

function DelegationPolicyBlock({ version, editor, onChange, onCancel, onSave, saving, error }: {
  version: DraftMatterVersion
  editor: DelegationEditor | null
  onChange: (editor: DelegationEditor) => void
  onCancel: () => void
  onSave: (editor: DelegationEditor) => void
  saving: boolean
  error: string | null
}) {
  const policy = version.delegation_policy
  if (!editor) {
    return <div className="space-y-2 text-sm">
      <p>是否允许代办：<strong>{policy ? (policy.delegation_allowed ? "允许" : "不允许") : "尚未配置"}</strong></p>
      {policy?.delegation_allowed && <p className="text-muted-foreground">居民选择代办人后，以下材料会加入其材料清单。</p>}
      {policy?.materials.length ? <ul className="space-y-1 rounded-md bg-muted p-3">{policy.materials.map((material) => <li key={material.id}>{material.name}（{material.requirement_level === "required" ? "必要" : "可选"} · {acquisitionMethodTypeText(material.submission_mode)}）</li>)}</ul> : <p className="text-muted-foreground">未配置代办专用材料。</p>}
      <Status text={policy?.verification_status ?? "pending"} />
    </div>
  }
  const updateMaterial = (index: number, value: Partial<DelegationEditor["materials"][number]>) =>
    onChange({ ...editor, materials: editor.materials.map((material, materialIndex) => materialIndex === index ? { ...material, ...value } : material) })
  return <div className="space-y-4 rounded-lg border bg-muted/30 p-4 text-sm">
    <label className="flex items-center gap-2 font-medium"><input type="checkbox" checked={editor.delegationAllowed} onChange={(event) => onChange({ ...editor, delegationAllowed: event.target.checked })} />允许代办</label>
    <p className="text-muted-foreground">编辑后规则和全部代办材料会重新标记为 pending，需再次点击“确认”才能发布。</p>
    {editor.delegationAllowed && <div className="space-y-3"><div className="flex items-center justify-between"><p className="font-medium">代办需要准备的材料</p><Button type="button" size="sm" variant="outline" onClick={() => onChange({ ...editor, materials: [...editor.materials, { key: crypto.randomUUID(), name: "", requirementLevel: "required", submissionMode: "on_site" }] })}>新增材料</Button></div>{editor.materials.length === 0 && <p className="text-muted-foreground">可新增需要由代办人准备的材料。</p>}{editor.materials.map((material, index) => <div className="grid gap-2 rounded border bg-background p-3 md:grid-cols-[1fr_7rem_10rem_auto]" key={material.key}><input className="rounded border bg-background p-2" value={material.name} placeholder="材料名称" onChange={(event) => updateMaterial(index, { name: event.target.value })} /><select className="rounded border bg-background p-2" value={material.requirementLevel} onChange={(event) => updateMaterial(index, { requirementLevel: event.target.value as "required" | "optional" })}><option value="required">必要</option><option value="optional">可选</option></select><select className="rounded border bg-background p-2" value={material.submissionMode} onChange={(event) => updateMaterial(index, { submissionMode: event.target.value as DelegationEditor["materials"][number]["submissionMode"] })}><option value="on_site">现场携带/核验</option><option value="user_upload">上传材料</option><option value="department_fetch">部门共享获取</option><option value="no_submission">无需提交</option></select><Button type="button" size="sm" variant="destructive" onClick={() => onChange({ ...editor, materials: editor.materials.filter((_, materialIndex) => materialIndex !== index) })}>删除</Button></div>)}</div>}
    <div className="flex gap-2"><Button size="sm" onClick={() => onSave(editor)} disabled={saving}>{saving ? "正在保存…" : "确认提交"}</Button><Button size="sm" variant="outline" onClick={onCancel} disabled={saving}>取消</Button></div>
    {error && <p className="text-destructive">{error}</p>}
  </div>
}

function MetadataSummary({ metadata }: { metadata: Record<string, unknown> }) {
  const acceptance = typeof metadata.acceptance_condition_raw === "string" ? metadata.acceptance_condition_raw : null
  const channels = Array.isArray(metadata.channels) ? metadata.channels.filter((value): value is string => typeof value === "string") : []
  const uncertainties = Array.isArray(metadata.uncertainties) ? metadata.uncertainties.filter((value): value is string => typeof value === "string") : []
  return <div className="mt-3 text-sm text-muted-foreground">{acceptance && <p>受理条件：{acceptance}</p>}{channels.length > 0 && <p className="mt-1">办理渠道：{channels.join("、")}</p>}{uncertainties.length > 0 && <p className="mt-1">待进一步确认：{uncertainties.join("；")}</p>}</div>
}

function OfficialGovernmentDetails({ version, editor, onEdit, onChange, onCancel, onSave, onConfirm, saving, confirming, error }: {
  version: DraftMatterVersion; editor: GovernmentDetailsEditor | null; onEdit: () => void
  onChange: (editor: GovernmentDetailsEditor) => void; onCancel: () => void; onSave: (editor: GovernmentDetailsEditor) => void
  onConfirm: () => void; saving: boolean; confirming: boolean; error: string | null
}) {
  const profile = Object.entries(version.government_profile_json ?? {})
  const steps = version.processing_steps_json ?? []
  const legalBases = version.legal_bases_json ?? []
  const evidence = version.field_evidence_json ?? []
  if (!profile.length && !steps.length && !legalBases.length && !evidence.length) return null
  const verification = version.metadata_json.government_details_verification_status === "verified" ? "verified" : "pending"
  return <details className="rounded-lg border bg-muted/20 p-4">
    <summary className="cursor-pointer font-semibold">政务基础信息、办理流程与提取证据 <span className="ml-2 text-xs font-normal text-muted-foreground">核验状态：{verification}</span></summary>
    <div className="mt-4 flex flex-wrap justify-end gap-2"><Button size="sm" variant="outline" onClick={onEdit} disabled={saving}><Pencil className="mr-1 size-3" />编辑</Button><Button size="sm" variant="outline" onClick={onConfirm} disabled={confirming || saving || verification === "verified"}><Check className="mr-1 size-3" />确认</Button></div>
    {editor ? <div className="mt-4 space-y-4 rounded border bg-background p-4"><p className="text-sm text-muted-foreground">修改后状态将重置为 pending；以下 JSON 保留字段名和结构。</p><label className="block text-sm font-medium">政务基础信息（JSON）<textarea className="mt-2 min-h-36 w-full rounded border bg-background p-2 font-mono text-xs font-normal" value={editor.profile} onChange={(event) => onChange({ ...editor, profile: event.target.value })} /></label><label className="block text-sm font-medium">办理流程（JSON）<textarea className="mt-2 min-h-36 w-full rounded border bg-background p-2 font-mono text-xs font-normal" value={editor.steps} onChange={(event) => onChange({ ...editor, steps: event.target.value })} /></label><label className="block text-sm font-medium">设定依据（每行一项）<textarea className="mt-2 min-h-28 w-full rounded border bg-background p-2 text-sm font-normal" value={editor.legalBases} onChange={(event) => onChange({ ...editor, legalBases: event.target.value })} /></label><label className="block text-sm font-medium">字段原文证据（JSON）<textarea className="mt-2 min-h-36 w-full rounded border bg-background p-2 font-mono text-xs font-normal" value={editor.evidence} onChange={(event) => onChange({ ...editor, evidence: event.target.value })} /></label><div className="flex gap-2"><Button size="sm" onClick={() => onSave(editor)} disabled={saving}><Check className="mr-1 size-3" />确认提交</Button><Button size="sm" variant="outline" onClick={onCancel} disabled={saving}>取消</Button></div>{error && <p className="text-sm text-destructive">{error}</p>}</div> : <>
    {profile.length > 0 && <dl className="mt-4 grid gap-x-6 gap-y-2 text-sm md:grid-cols-2">{profile.map(([label, value]) => <div className="grid grid-cols-[8rem_1fr] gap-2" key={label}><dt className="text-muted-foreground">{label}</dt><dd>{value}</dd></div>)}</dl>}
    {steps.length > 0 && <div className="mt-4"><p className="font-medium">办理流程</p><ol className="mt-2 space-y-2">{steps.map((step, index) => <li className="rounded bg-background p-3 text-sm" key={`${step.step}-${index}`}><p className="font-medium">{index + 1}. {step.step ?? "未命名步骤"}{step.time_limit ? `（${step.time_limit}）` : ""}</p>{step.result && <p className="mt-1 text-muted-foreground">办理结果：{step.result}</p>}{step.review_standard && <p className="mt-1 text-muted-foreground">审查标准：{step.review_standard}</p>}</li>)}</ol></div>}
    {legalBases.length > 0 && <div className="mt-4"><p className="font-medium">设定依据</p><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">{legalBases.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul></div>}
    {evidence.length > 0 && <details className="mt-4 rounded border bg-background p-3"><summary className="cursor-pointer font-medium">字段原文证据（{evidence.length} 条）</summary><ul className="mt-3 space-y-2 text-sm">{evidence.map((item, index) => <li className="rounded bg-muted p-3" key={`${item.field_path}-${index}`}><p className="font-medium">{item.field_path}{item.page_number ? ` · 第 ${item.page_number} 页` : ""}</p><p className="mt-1 whitespace-pre-wrap text-muted-foreground">{item.quote}</p></li>)}</ul></details>}
    </>}
  </details>
}

function StatusConfigForm({ editor, onChange, onCancel, onSubmit, saving, error }: { editor: StatusEditor; onChange: (editor: StatusEditor) => void; onCancel: () => void; onSubmit: () => void; saving: boolean; error: string | null }) {
  return <div className="mt-4 space-y-4 rounded-lg border bg-muted/30 p-4"><label className="block text-sm font-medium">受理条件<textarea className="mt-2 min-h-20 w-full rounded-md border bg-background p-2 font-normal" value={editor.acceptance} onChange={(event) => onChange({ ...editor, acceptance: event.target.value })} /></label><label className="block text-sm font-medium">办理渠道<span className="ml-2 font-normal text-muted-foreground">每行一项</span><textarea className="mt-2 min-h-20 w-full rounded-md border bg-background p-2 font-normal" value={editor.channels} onChange={(event) => onChange({ ...editor, channels: event.target.value })} /></label><label className="block text-sm font-medium">待进一步确认<span className="ml-2 font-normal text-muted-foreground">每行一项</span><textarea className="mt-2 min-h-24 w-full rounded-md border bg-background p-2 font-normal" value={editor.uncertainties} onChange={(event) => onChange({ ...editor, uncertainties: event.target.value })} /></label><div className="flex gap-2"><Button size="sm" onClick={onSubmit} disabled={saving}><Check className="mr-1 size-3" />确认提交</Button><Button size="sm" variant="outline" onClick={onCancel} disabled={saving}>取消</Button></div>{error && <p className="text-sm text-destructive">{error}</p>}</div>
}

function SourceConfigForm({ editor, onChange, onCancel, onSubmit, saving, error }: { editor: SourceEditor; onChange: (editor: SourceEditor) => void; onCancel: () => void; onSubmit: () => void; saving: boolean; error: string | null }) {
  return <div className="mt-4 space-y-4 rounded-lg border bg-muted/30 p-4"><label className="block text-sm font-medium">发布/来源门户<input className="mt-2 w-full rounded-md border bg-background p-2 font-normal" value={editor.publisher} onChange={(event) => onChange({ ...editor, publisher: event.target.value })} /></label><label className="block text-sm font-medium">门户链接<input type="url" className="mt-2 w-full rounded-md border bg-background p-2 font-normal" value={editor.url} onChange={(event) => onChange({ ...editor, url: event.target.value })} required /></label><div className="flex gap-2"><Button size="sm" onClick={onSubmit} disabled={saving || !editor.url.trim()}><Check className="mr-1 size-3" />确认提交</Button><Button size="sm" variant="outline" onClick={onCancel} disabled={saving}>取消</Button></div>{error && <p className="text-sm text-destructive">{error}</p>}</div>
}

function LocationConfigForm({ editor, onChange, onCancel, onSubmit, saving, error }: { editor: LocationEditor; onChange: (editor: LocationEditor) => void; onCancel: () => void; onSubmit: () => void; saving: boolean; error: string | null }) {
  return <div className="space-y-4 rounded-lg border bg-muted/30 p-4"><label className="block text-sm font-medium">办理地点名称<input className="mt-2 w-full rounded-md border bg-background p-2 font-normal" value={editor.name} onChange={(event) => onChange({ ...editor, name: event.target.value })} /></label><label className="block text-sm font-medium">办理地址<textarea className="mt-2 min-h-20 w-full rounded-md border bg-background p-2 font-normal" value={editor.address} onChange={(event) => onChange({ ...editor, address: event.target.value })} /></label><div className="grid gap-4 md:grid-cols-2"><label className="block text-sm font-medium">联系电话<input className="mt-2 w-full rounded-md border bg-background p-2 font-normal" value={editor.phone} onChange={(event) => onChange({ ...editor, phone: event.target.value })} /></label><label className="block text-sm font-medium">工作时间<input className="mt-2 w-full rounded-md border bg-background p-2 font-normal" value={editor.openingHours} onChange={(event) => onChange({ ...editor, openingHours: event.target.value })} /></label></div><label className="block text-sm font-medium">事项指南链接<input type="url" className="mt-2 w-full rounded-md border bg-background p-2 font-normal" value={editor.guideUrl} onChange={(event) => onChange({ ...editor, guideUrl: event.target.value })} /></label><div className="grid gap-4 md:grid-cols-2"><label className="block text-sm font-medium">地点核验状态<select className="mt-2 w-full rounded-md border bg-background p-2 font-normal" value={editor.verificationStatus} onChange={(event) => onChange({ ...editor, verificationStatus: event.target.value as LocationEditor["verificationStatus"] })}><option value="pending">pending（待核验）</option><option value="verified">verified（已核验）</option><option value="unavailable">unavailable（不可用）</option></select></label><label className="block text-sm font-medium">地点核验时间<input type="datetime-local" className="mt-2 w-full rounded-md border bg-background p-2 font-normal" value={editor.checkedAt} onChange={(event) => onChange({ ...editor, checkedAt: event.target.value })} /></label></div><label className="block text-sm font-medium">信息来源 ID<input className="mt-2 w-full rounded-md border bg-background p-2 font-normal" placeholder="policy_sources 表中的 UUID，可留空" value={editor.sourceId} onChange={(event) => onChange({ ...editor, sourceId: event.target.value })} /></label><div className="flex gap-2"><Button size="sm" onClick={onSubmit} disabled={saving || !editor.name.trim()}><Check className="mr-1 size-3" />确认提交</Button><Button size="sm" variant="outline" onClick={onCancel} disabled={saving}>取消</Button></div>{error && <p className="text-sm text-destructive">{error}</p>}</div>
}

function MaterialConfigDialog({ editor, onChange, onCancel, onSubmit, saving, error }: { editor: MaterialEditor; onChange: (editor: MaterialEditor) => void; onCancel: () => void; onSubmit: () => void; saving: boolean; error: string | null }) {
  return <Dialog open onOpenChange={(open) => { if (!open && !saving) onCancel() }}>
    <DialogContent>
      <DialogHeader>
        <DialogTitle>修改材料要求</DialogTitle>
        <DialogDescription>修改后会保存到数据库，并将该材料重新标记为待人工核验。</DialogDescription>
      </DialogHeader>
      <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); onSubmit() }}>
        <label className="block text-sm font-medium">材料名称<input autoFocus className="mt-2 w-full rounded-md border bg-background p-2 font-normal" value={editor.name} onChange={(event) => onChange({ ...editor, name: event.target.value })} /></label>
        <label className="block text-sm font-medium">材料必要性<select className="mt-2 w-full rounded-md border bg-background p-2 font-normal" value={editor.level} onChange={(event) => onChange({ ...editor, level: event.target.value as MaterialEditor["level"] })}><option value="required">必要材料</option><option value="optional">可选材料</option></select></label>
        <label className="block text-sm font-medium">格式与提交说明<textarea className="mt-2 min-h-28 w-full rounded-md border bg-background p-2 font-normal" value={editor.formatRequirements} onChange={(event) => onChange({ ...editor, formatRequirements: event.target.value })} placeholder="例如：上传身份证正反面彩色扫描件；原件现场核验" /></label>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <DialogFooter><Button type="button" variant="outline" onClick={onCancel} disabled={saving}>取消</Button><Button type="submit" disabled={saving || !editor.name.trim()}><Check className="mr-1 size-3" />{saving ? "正在保存…" : "确认提交"}</Button></DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
}

function AcquisitionConfigDialog({ editor, materials, onChange, onCancel, onSubmit, saving, error }: { editor: AcquisitionEditor; materials: DraftMatterVersion["materials"]; onChange: (editor: AcquisitionEditor) => void; onCancel: () => void; onSubmit: () => void; saving: boolean; error: string | null }) {
  return <Dialog open onOpenChange={(open) => { if (!open && !saving) onCancel() }}>
    <DialogContent>
      <DialogHeader>
        <DialogTitle>{editor.methodId ? "修改材料获取方式" : "新增材料获取方式"}</DialogTitle>
        <DialogDescription>填写材料的获取、准备或提交渠道。修改已有信息后，该条记录会重新标记为待人工核验。</DialogDescription>
      </DialogHeader>
      <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); onSubmit() }}>
        <label className="block text-sm font-medium">关联材料<select className="mt-2 w-full rounded-md border bg-background p-2 font-normal" value={editor.requirementId} onChange={(event) => onChange({ ...editor, requirementId: event.target.value })}>{materials.map((material) => <option key={material.id} value={material.id}>{material.name}</option>)}</select></label>
        <label className="block text-sm font-medium">获取方式类型<select className="mt-2 w-full rounded-md border bg-background p-2 font-normal" value={editor.methodType} onChange={(event) => onChange({ ...editor, methodType: event.target.value as AcquisitionEditor["methodType"] })}><option value="self_prepare">自行准备</option><option value="online_download">线上下载</option><option value="online_apply">线上申办</option><option value="in_person">窗口领取/办理</option><option value="department_fetch">部门共享获取</option><option value="on_site">现场提交/核验</option></select></label>
        <label className="block text-sm font-medium">方式名称<input autoFocus className="mt-2 w-full rounded-md border bg-background p-2 font-normal" value={editor.title} onChange={(event) => onChange({ ...editor, title: event.target.value })} placeholder="例如：通过政务服务网在线下载" /></label>
        <label className="block text-sm font-medium">具体说明<textarea className="mt-2 min-h-28 w-full rounded-md border bg-background p-2 font-normal" value={editor.steps} onChange={(event) => onChange({ ...editor, steps: event.target.value })} placeholder="说明办理步骤、携带要求或注意事项" /></label>
        <label className="block text-sm font-medium">相关链接<input type="url" className="mt-2 w-full rounded-md border bg-background p-2 font-normal" value={editor.entryUrl} onChange={(event) => onChange({ ...editor, entryUrl: event.target.value })} placeholder="https://...（可留空）" /></label>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <DialogFooter><Button type="button" variant="outline" onClick={onCancel} disabled={saving}>取消</Button><Button type="submit" disabled={saving || !editor.title.trim() || !editor.requirementId}><Check className="mr-1 size-3" />{saving ? "正在保存…" : "确认提交"}</Button></DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : []
}

function splitValues(value: string): string[] {
  return value.split(/\r?\n|；/).map((item) => item.trim()).filter(Boolean)
}

function aggregateVerificationStatus(statuses: string[]): string | null {
  if (statuses.length === 0) return null
  if (statuses.includes("pending")) return "pending"
  if (statuses.includes("unavailable")) return "unavailable"
  return "verified"
}

function unverifiedReviewSections(version: DraftMatterVersion): string[] {
  const unfinished: string[] = []
  if (!version.delegation_policy || version.delegation_policy.verification_status !== "verified") unfinished.push("是否允许代办与代办材料")
  if (version.source_verification_status !== "verified") unfinished.push("官方网页与来源")
  if (version.location_verification_status !== "verified") unfinished.push("办理地点与联系电话")
  if (version.materials.length === 0 || version.materials.some((material) => material.verification_status !== "verified")) unfinished.push("材料要求")
  if (version.acquisition_methods.length === 0 || version.acquisition_methods.some((method) => method.verification_status !== "verified")) unfinished.push("材料获取方式与线上渠道")
  return unfinished
}

function isAcquisitionMethodType(value: string): AcquisitionEditor["methodType"] {
  return ["online_download", "online_apply", "in_person", "self_prepare", "department_fetch", "on_site"].includes(value)
    ? value as AcquisitionEditor["methodType"]
    : "self_prepare"
}

function acquisitionMethodTypeText(value: string): string {
  const labels: Record<string, string> = { online_download: "线上下载", online_apply: "线上申办", in_person: "窗口领取/办理", self_prepare: "自行准备", department_fetch: "部门共享获取", on_site: "现场提交/核验" }
  return labels[value] ?? value
}

function isLocationStatus(value: string | null): LocationEditor["verificationStatus"] {
  return value === "verified" || value === "unavailable" ? value : "pending"
}

function dateTimeLocalValue(value: string | null): string {
  return value ? new Date(value).toISOString().slice(0, 16) : ""
}
