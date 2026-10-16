import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { FileUp, MapPin, Users } from "lucide-react"
import { useEffect, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  getApplication, getChecklist, getParticipants, getQuestionnaire, submitQuestionnaire,
  createPreparationPackage, downloadPreparationPackage, getLatestPreparationPackage, openApplicationDocument, startMaterialReview, uploadApplicationMaterial, type MaterialReview,
} from "@/lib/applications-api"

export const Route = createFileRoute("/_layout/applications/$applicationId")({ component: ApplicationWorkspace })

function applicationStatusLabel(status: string) {
  return ({
    draft: "草稿",
    preparing: "准备中",
    checking: "材料检查中",
    needs_action: "待补传材料",
    review_pending: "人工复核中",
    prepared: "准备包已生成（待线下办理）",
    closed: "已结束",
  } as Record<string, string>)[status] ?? status
}

function ApplicationWorkspace() {
  const { applicationId } = Route.useParams()
  const client = useQueryClient()
  const [preparedFor, setPreparedFor] = useState<"self" | "other">("self")
  const [applicantName, setApplicantName] = useState("")
  const [submissionPlan, setSubmissionPlan] = useState<"applicant" | "agent" | "unknown">("applicant")
  const [agentRelationship, setAgentRelationship] = useState("")
  const [agentName, setAgentName] = useState("")
  const [questionnaireSaveNotice, setQuestionnaireSaveNotice] = useState<string | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [packageError, setPackageError] = useState<string | null>(null)
  const [qrUrl, setQrUrl] = useState<string | null>(null)
  const [checkingMaterials, setCheckingMaterials] = useState<Record<string, "local" | "cloud">>({})
  const [itemReviewResults, setItemReviewResults] = useState<Record<string, MaterialReview["model_result_json"]>>({})
  const appQuery = useQuery({ queryKey: ["application", applicationId], queryFn: () => getApplication(applicationId) })
  const peopleQuery = useQuery({ queryKey: ["application-participants", applicationId], queryFn: () => getParticipants(applicationId) })
  const questionnaireQuery = useQuery({ queryKey: ["application-questionnaire", applicationId], queryFn: () => getQuestionnaire(applicationId) })
  const checklistQuery = useQuery({ queryKey: ["application-checklist", applicationId], queryFn: () => getChecklist(applicationId) })
  const packageQuery = useQuery({ queryKey: ["preparation-package", applicationId], queryFn: () => getLatestPreparationPackage(applicationId) })
  const refresh = () => Promise.all([
    client.invalidateQueries({ queryKey: ["application", applicationId] }),
    client.invalidateQueries({ queryKey: ["application-participants", applicationId] }),
    client.invalidateQueries({ queryKey: ["application-questionnaire", applicationId] }),
    client.invalidateQueries({ queryKey: ["application-checklist", applicationId] }),
    client.invalidateQueries({ queryKey: ["applications"] }),
    client.invalidateQueries({ queryKey: ["preparation-package", applicationId] }),
  ])
  const applicant = peopleQuery.data?.find((person) => person.role_code === "applicant")
  const agent = peopleQuery.data?.find((person) => person.role_code === "agent")
  useEffect(() => {
    if (!questionnaireQuery.data) return
    const answers = questionnaireQuery.data.answers
    setPreparedFor(answers.prepared_for === "other" ? "other" : "self")
    setSubmissionPlan(answers.submission_plan === "agent" ? "agent" : answers.submission_plan === "unknown" ? "unknown" : "applicant")
    setAgentRelationship(typeof answers.agent_relationship === "string" ? answers.agent_relationship : "")
    setApplicantName(applicant?.display_name ?? "")
    setAgentName(agent?.display_name ?? "")
  }, [questionnaireQuery.data, applicant?.display_name, agent?.display_name])
  const submit = useMutation({
    mutationFn: () => submitQuestionnaire(applicationId, {
      preparedFor, applicantName: applicantName.trim(), submissionPlan,
      agentRelationship, agentName: agentName.trim(), expectedRevision: appQuery.data!.content_revision,
    }),
    onSuccess: async (result) => {
      const notice = result.delegation_status === "delegated"
        ? "已保存：办件状态为他人代办。"
        : result.delegation_status === "not_delegated"
          ? "已保存：办件状态为本人办理。"
          : result.delegation_status === "pending_confirmation"
            ? "已保存：已记录代办意向，待工作人员确认该事项是否允许代办。"
            : "已保存：办件状态待确认。"
      setQuestionnaireSaveNotice(notice)
      await refresh()
    },
  })
  const uploadMaterial = useMutation({
    mutationFn: ({ id, kind, files }: { id: string; kind: "requirement" | "extra"; files: File[] }) =>
      uploadApplicationMaterial(applicationId, id, kind, files, appQuery.data!.content_revision),
    onSuccess: refresh,
  })
  const materialReview = useMutation({
    mutationFn: ({ provider, id, kind }: { provider: "local" | "cloud"; id: string; kind: "requirement" | "extra" }) =>
      startMaterialReview(applicationId, provider, appQuery.data!.content_revision, { materialId: id, itemKind: kind }),
    onMutate: ({ id, provider }) => {
      setCheckingMaterials((current) => ({ ...current, [id]: provider }))
    },
    onSuccess: async (result, variables) => {
      setItemReviewResults((current) => ({ ...current, [variables.id]: result.result }))
      await refresh()
    },
    onSettled: (_result, _error, variables) => {
      setCheckingMaterials((current) => {
        const { [variables.id]: _removed, ...remaining } = current
        return remaining
      })
    },
  })
  const generatePackage = useMutation({ mutationFn: () => createPreparationPackage(applicationId), onSuccess: async () => { setPackageError(null); await refresh() } })
  if (appQuery.isLoading) return <div className="py-16 text-center text-muted-foreground">正在加载材料准备记录…</div>
  if (appQuery.error || !appQuery.data) return <div className="rounded-lg border border-destructive/30 p-5 text-destructive">{appQuery.error?.message ?? "材料准备记录不存在或无权访问"}</div>
  const app = appQuery.data
  const checklist = checklistQuery.data?.items ?? []
  const delegationPending = app.scenario_answers.delegation_status === "pending_confirmation"
  const handlingMode = app.is_delegated
    ? "他人代办"
    : app.scenario_answers.submission_plan === "applicant"
      ? "本人办理"
      : null
  const delegationPolicy = questionnaireQuery.data?.delegation_policy
  const preparationPackage = packageQuery.data
  return <div className="mx-auto max-w-5xl space-y-6">
    <header className="rounded-xl border bg-card p-5"><p className="text-sm text-muted-foreground">材料准备记录：{app.application_no}</p><div className="mt-1 flex flex-wrap items-center justify-between gap-3"><h1 className="text-2xl font-bold">{app.matter.matter_name}</h1><div className="flex gap-2"><Badge variant={app.status === "draft" ? "secondary" : app.status === "prepared" ? "outline" : "default"}>{applicationStatusLabel(app.status)}</Badge>{handlingMode && <Badge variant="outline">{handlingMode}</Badge>}</div></div><p className="mt-3 text-sm text-muted-foreground">这是一份线上材料准备记录，不代表正式受理、审批或办结；最终请携带材料到线下指定地点办理。</p></header>

    <section className="rounded-xl border bg-card p-5"><div className="flex items-start gap-3"><Users className="mt-1 size-5 text-primary" /><div className="min-w-0 flex-1"><h2 className="font-semibold">办理情形与人员</h2><p className="mt-1 text-sm text-muted-foreground">登录账号用于管理这份记录；申请人与代办人单独保存。帮助他人整理材料不等于正式代办。</p><div className="mt-5 space-y-5 text-sm">
      <Question title="1．这次为谁准备材料？"><Choice value="self" current={preparedFor} onChange={() => setPreparedFor("self")}>我自己</Choice><Choice value="other" current={preparedFor} onChange={() => setPreparedFor("other")}>其他人</Choice></Question>
      <Question title="2．申请人姓名"><Input value={applicantName} onChange={(event) => setApplicantName(event.target.value)} placeholder={preparedFor === "self" ? "填写本人姓名以确认申请人" : "填写申请人姓名"} className="max-w-sm" /><p className="w-full text-muted-foreground">申请人是这项业务实际为其办理的人。</p></Question>
      {questionnaireQuery.data?.show_submission_plan && <Question title="3．计划由谁到窗口提交申请材料？"><Choice value="applicant" current={submissionPlan} onChange={() => setSubmissionPlan("applicant")}>申请人本人</Choice><Choice value="agent" current={submissionPlan} onChange={() => setSubmissionPlan("agent")}>代办人</Choice><Choice value="unknown" current={submissionPlan} onChange={() => setSubmissionPlan("unknown")}>尚不确定</Choice></Question>}
      {questionnaireQuery.data?.show_submission_plan && submissionPlan === "agent" && <><Question title="4．代办人姓名"><Input value={agentName} onChange={(event) => setAgentName(event.target.value)} placeholder="填写代办人姓名" className="max-w-sm" /></Question>{delegationPolicy?.is_verified && delegationPolicy.relationship_required && <Question title="补充：代办人与申请人的关系"><select value={agentRelationship} onChange={(event) => setAgentRelationship(event.target.value)} className="h-9 rounded-md border bg-background px-3"><option value="">请选择关系</option>{delegationPolicy.allowed_relationships.map((item) => <option key={item} value={item}>{item}</option>)}</select></Question>}<p className="text-muted-foreground">选择代办人仅表示当前意向；是否允许代办、关系或监护情形、本人是否仍须到场，须按已核实的事项要求进一步确认。</p></>}
      {delegationPolicy?.is_verified && delegationPolicy.applicant_must_attend && <p className="rounded-md border border-amber-300 bg-amber-50 p-3 text-amber-800">该事项规则要求申请人本人仍须到场；代办人不能替代本人到场。</p>}
      <Button onClick={() => { setQuestionnaireSaveNotice(null); submit.mutate() }} disabled={!applicantName.trim() || (questionnaireQuery.data?.show_submission_plan && submissionPlan === "agent" && (!agentName.trim() || (delegationPolicy?.is_verified && delegationPolicy.relationship_required && !agentRelationship))) || submit.isPending}>{submit.isPending ? "保存中…" : "保存"}</Button>
      {questionnaireSaveNotice && <p className="rounded-md border border-primary/30 bg-primary/5 p-3 text-sm text-primary">{questionnaireSaveNotice}</p>}
      {delegationPending && <p className="rounded-md border border-amber-300 bg-amber-50 p-3 text-amber-800">已保存“拟由代办人办理”的意向，但当前事项尚未配置或核实允许代办的条件，代办材料清单仍待人工确认。</p>}
      {submit.error && <p className="text-sm text-destructive">{submit.error.message}</p>}
    </div></div></div></section>

    <section className="rounded-xl border bg-card p-5">
      <div className="flex items-start gap-3"><FileUp className="mt-1 size-5 text-primary" /><div><h2 className="font-semibold">材料清单</h2><p className="mt-1 text-sm text-muted-foreground">每项材料可独立上传和审核。上传成功即视为已准备；模型未通过的单项材料才进入人工复核，人工通过后会锁定该材料。</p></div></div>
      <div className="mt-4 space-y-3">
        {checklist.map((item) => {
          const passed = item.review_decision === "pass"
          const modelPassed = item.review_decision === "model_pass"
          const reupload = item.review_decision === "reupload"
          const isChecking = checkingMaterials[item.requirement_id]
          const canReview = !passed && !modelPassed && item.uploaded_file_count > 0 && (!reupload || item.reupload_file_saved)
          const result = itemReviewResults[item.requirement_id] ?? item.review_result
          return <div key={item.requirement_id} className="rounded-lg border p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div><p className="font-medium">{item.name} <span className="text-sm font-normal text-muted-foreground">{item.requirement_level === "required" ? "（必要）" : "（可选）"}</span></p><p className="mt-1 text-sm text-muted-foreground">{passed ? "人工复核已通过，该材料已锁定。" : modelPassed ? "重传文件已通过模型检查；尚未进入人工锁定状态。" : reupload ? item.reupload_file_saved ? "重传文件已保存，请点击模型检查。" : `待重传文件：${item.review_note || "请按工作人员反馈重新上传。"}` : item.item_kind === "extra" ? "因本次选择委托他人办理而增加" : "上传文件后可单独发起模型审核。"}</p>{item.uploaded_file_count > 0 && <p className="mt-1 text-sm text-primary">已准备，已上传 {item.uploaded_file_count} 个文件</p>}</div>
              <div className="flex flex-wrap items-center gap-2"><Badge variant={passed || modelPassed || item.uploaded_file_count > 0 ? "default" : reupload ? "destructive" : "secondary"}>{passed ? "人工已通过" : modelPassed ? "模型检查通过" : reupload ? item.reupload_file_saved ? "重传文件已保存" : "待重传文件" : item.uploaded_file_count > 0 ? "已准备" : "未准备"}</Badge>{!passed && <label className="inline-flex h-9 cursor-pointer items-center justify-center rounded-md border border-input bg-background px-3 text-sm font-medium shadow-xs hover:bg-accent hover:text-accent-foreground"><span>{reupload ? "重新上传" : "上传文件"}</span><input className="sr-only" type="file" multiple accept=".pdf,.docx,.txt,.jpg,.jpeg,.png,.webp" disabled={uploadMaterial.isPending} onChange={(event) => { const files = Array.from(event.target.files ?? []); event.currentTarget.value = ""; if (files.length) uploadMaterial.mutate({ id: item.requirement_id, kind: item.item_kind, files }) }} /></label>}{canReview && <><Button size="sm" disabled={Boolean(isChecking)} onClick={() => materialReview.mutate({ provider: "local", id: item.requirement_id, kind: item.item_kind })}>{isChecking === "local" ? "本地模型检查中…" : "本地模型检查"}</Button><Button size="sm" variant="outline" disabled={Boolean(isChecking)} onClick={() => materialReview.mutate({ provider: "cloud", id: item.requirement_id, kind: item.item_kind })}>{isChecking === "cloud" ? "云端模型检查中…" : "云端模型检查"}</Button></>}</div>
            </div>
            {item.files.length > 0 && <div className="mt-3 rounded-md border bg-muted/20 p-3 text-sm"><p className="font-medium">已上传材料</p><div className="mt-2 flex flex-wrap gap-2">{item.files.map((file) => <Button key={file.id} size="sm" variant="outline" onClick={() => { setPreviewError(null); openApplicationDocument(applicationId, file.id).catch((error: unknown) => setPreviewError(error instanceof Error ? error.message : "无法预览上传的材料")) }}>预览：{file.original_filename}</Button>)}</div></div>}
            {item.review_note && <div className="mt-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950"><p className="font-medium">工作人员反馈</p><p className="mt-1">{item.review_note}</p></div>}
            {result && <div className="mt-3 rounded-md border border-primary/25 bg-primary/5 p-3 text-sm"><p className="font-medium">审核结果：{result.decision === "pass" ? "模型检查通过（仅供材料准备参考）" : "已进入人工复核阶段"}</p>{result.summary && <p className="mt-1 text-muted-foreground">{result.summary}</p>}{result.items?.map((resultItem, index) => <div className="mt-2 rounded border bg-background p-2" key={`${resultItem.material_name}-${index}`}><p className="font-medium">{resultItem.result === "pass" ? "无明显问题" : resultItem.result === "issue" ? "需补充或修正" : "待人工确认"}</p><p className="mt-1 text-muted-foreground">{resultItem.reason}</p>{resultItem.suggested_action && <p className="mt-1 text-muted-foreground">建议：{resultItem.suggested_action}</p>}</div>)}</div>}
          </div>
        })}
        {checklist.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">当前事项尚未配置材料清单。</p>}
      </div>
      {uploadMaterial.isPending && <p className="mt-3 text-sm text-muted-foreground">正在上传材料…</p>}{uploadMaterial.error instanceof Error && <p className="mt-3 text-sm text-destructive">{uploadMaterial.error.message}</p>}{materialReview.error instanceof Error && <p className="mt-3 text-sm text-destructive">{materialReview.error.message}</p>}{previewError && <p className="mt-3 text-sm text-destructive">{previewError}</p>}
    </section>
    <section id="preparation-package" className="rounded-xl border bg-card p-5"><div className="flex gap-3"><MapPin className="mt-1 size-5 text-primary" /><div className="flex-1"><h2 className="font-semibold">线下办理提示与办理准备包</h2><p className="mt-1 text-sm text-muted-foreground">准备包汇总当前事项、人员、办理信息、携带材料和预审摘要；正式受理仍以线下窗口核验为准。</p>{preparationPackage && <div className="mt-4 rounded-lg border bg-muted/30 p-4 text-sm"><p className="font-medium">办理准备包 #{preparationPackage.package_no} {preparationPackage.is_current ? "（当前版本）" : "（已过期，材料或信息已有更新）"}</p><p className="mt-1 text-muted-foreground">结果链接指向本页，需登录后才能查看或下载；二维码不包含个人材料。</p><div className="mt-3 flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={() => downloadPreparationPackage(preparationPackage.id, "pdf").catch((error: unknown) => setPackageError(error instanceof Error ? error.message : "下载失败"))}>下载办前准备单 PDF</Button><Button size="sm" variant="outline" onClick={() => downloadPreparationPackage(preparationPackage.id, "zip").catch((error: unknown) => setPackageError(error instanceof Error ? error.message : "下载失败"))}>下载电子材料 ZIP</Button><Button size="sm" variant="outline" onClick={() => downloadPreparationPackage(preparationPackage.id, "qr").then((url) => setQrUrl(url)).catch((error: unknown) => setPackageError(error instanceof Error ? error.message : "生成二维码失败"))}>显示二维码</Button></div>{qrUrl && <img className="mt-3 size-40 rounded border bg-white p-2" src={qrUrl} alt="办理准备包结果页面二维码" />}</div>}<div className="mt-4"><Button disabled={generatePackage.isPending} onClick={() => generatePackage.mutate()}>{generatePackage.isPending ? "正在生成准备包…" : preparationPackage ? "重新生成当前准备包" : "生成办理准备包"}</Button></div>{generatePackage.error instanceof Error && <p className="mt-3 text-sm text-destructive">{generatePackage.error.message}</p>}{packageError && <p className="mt-3 text-sm text-destructive">{packageError}</p>}</div></div></section>
  </div>
}

function Question({ title, children }: { title: string; children: React.ReactNode }) { return <div><p className="mb-2 font-medium">{title}</p><div className="flex flex-wrap items-center gap-3">{children}</div></div> }
function Choice({ value, current, onChange, children }: { value: string; current: string; onChange: () => void; children: React.ReactNode }) { return <label className="flex cursor-pointer items-center gap-2"><input type="radio" checked={value === current} onChange={onChange} />{children}</label> }
