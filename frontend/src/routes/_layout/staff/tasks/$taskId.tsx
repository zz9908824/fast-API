import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, createFileRoute } from "@tanstack/react-router"
import { FileText, Loader2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { completeCaseReviewTask, getCaseReviewTask, openCaseReviewDocument, type CaseReviewItemDecision } from "@/lib/case-review-api"

export const Route = createFileRoute("/_layout/staff/tasks/$taskId")({ component: TaskWorkbench })

type DraftDecision = { decision: "pass" | "reupload"; note: string }

function TaskWorkbench() {
  const { taskId } = Route.useParams()
  const client = useQueryClient()
  const [generalComment, setGeneralComment] = useState("")
  const [decisions, setDecisions] = useState<Record<string, DraftDecision>>({})
  const [openFileError, setOpenFileError] = useState<string | null>(null)
  const taskQuery = useQuery({ queryKey: ["case-review-task", taskId], queryFn: () => getCaseReviewTask(taskId) })
  const task = taskQuery.data
  const reviewItems: Array<{ material_name: string; result: string; reason: string; suggested_action?: string | null }> = useMemo(() => {
    const items = (task?.model_result_json?.items ?? []).filter((item) => item.result !== "pass")
    return items.length ? items : [{ material_name: "整体材料", result: "uncertain", reason: task?.request_note ?? "模型未提供逐项结论，请结合上传文件人工判断。" }]
  }, [task?.model_result_json?.items, task?.request_note])
  useEffect(() => {
    if (!task) return
    setDecisions(Object.fromEntries(reviewItems.map((item) => [item.material_name, { decision: "pass", note: "" }])))
  }, [task, reviewItems])
  const complete = useMutation({
    mutationFn: (itemDecisions: CaseReviewItemDecision[]) => completeCaseReviewTask(taskId, itemDecisions, generalComment.trim()),
    onSuccess: () => Promise.all([client.invalidateQueries({ queryKey: ["case-review-tasks"] }), client.invalidateQueries({ queryKey: ["case-review-task", taskId] })]),
  })
  if (taskQuery.isLoading) return <div className="flex items-center gap-2 py-16 text-muted-foreground"><Loader2 className="size-5 animate-spin" />正在加载复核任务…</div>
  if (taskQuery.error instanceof Error || !task) return <div className="rounded-lg border border-destructive/30 p-5 text-destructive">{taskQuery.error instanceof Error ? taskQuery.error.message : "复核任务不存在"}</div>
  const isActive = task.status === "in_progress" && task.application_status !== "cancelled"
  const readyToSubmit = reviewItems.length > 0 && reviewItems.every((item) => {
    const draft = decisions[item.material_name]
    return draft && (draft.decision === "pass" || draft.note.trim().length > 0)
  })
  const updateDecision = (materialName: string, change: Partial<DraftDecision>) => {
    setDecisions((current) => ({ ...current, [materialName]: { ...(current[materialName] ?? { decision: "pass", note: "" }), ...change } }))
  }
  const submit = () => complete.mutate(reviewItems.map((item) => ({
    material_name: item.material_name,
    decision: decisions[item.material_name]?.decision ?? "pass",
    note: decisions[item.material_name]?.note.trim() ?? "",
  })))
  return <div className="mx-auto max-w-6xl space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-sm text-muted-foreground">办件编号：{task.application_no}</p><h1 className="text-2xl font-bold">办件复核工作台</h1><p className="mt-1 text-muted-foreground">{task.matter_name}</p><p className="mt-1 text-xs text-muted-foreground">领取管理员编号：{task.reviewer_user_id ?? "未领取"}</p></div><Button asChild variant="outline"><Link to="/staff/tasks">返回复核队列</Link></Button></div>
    {task.application_status === "cancelled" && <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">用户已取消该办件，不能再提交复核结论。</div>}
    <section className="rounded-xl border bg-card p-5"><div className="flex items-center gap-2"><FileText className="size-4" /><h2 className="font-semibold">用户上传的文件</h2></div><p className="mt-1 text-sm text-muted-foreground">文件仅对已领取该办件的管理员开放；点击“查看文件”可在新窗口打开。</p><div className="mt-4 space-y-2">{task.documents.map((file) => <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3 text-sm" key={file.id}><div><p className="font-medium">{file.material_name}</p><p className="mt-1 text-muted-foreground">{file.original_filename} · {Math.max(1, Math.round(file.byte_size / 1024))} KB</p></div><Button size="sm" variant="outline" onClick={() => { setOpenFileError(null); openCaseReviewDocument(taskId, file.id).catch((error: Error) => setOpenFileError(error.message)) }}>查看文件</Button></div>)}{task.documents.length === 0 && <p className="text-sm text-muted-foreground">没有可用于本次检查的上传文件记录。</p>}</div>{openFileError && <p className="mt-3 text-sm text-destructive">{openFileError}</p>}</section>
    <section className="rounded-xl border bg-card p-5"><h2 className="font-semibold">模型标记的待复核事项</h2><p className="mt-1 text-sm text-muted-foreground">请逐项查看文件和模型结论。每项材料只能在“通过”和“要求重传”之间二选一；通过时可选填备注，要求重传时必须填写会反馈给用户的具体原因。</p><p className="mt-3 rounded-md bg-muted p-3 text-sm text-muted-foreground">模型摘要：{task.model_result_json?.summary ?? task.request_note ?? "暂无模型摘要"}</p><div className="mt-4 space-y-4">{reviewItems.map((item, index) => { const draft = decisions[item.material_name] ?? { decision: "pass", note: "" }; return <div className="rounded-lg border p-4" key={`${item.material_name}-${index}`}><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-medium">{index + 1}. {item.material_name}</h3><p className="mt-1 text-sm text-muted-foreground">模型说明：{item.reason}</p>{item.suggested_action && <p className="mt-1 text-sm text-muted-foreground">模型建议：{item.suggested_action}</p>}</div><fieldset className="flex items-center gap-4" disabled={!isActive || complete.isPending}><label className="flex cursor-pointer items-center gap-2 text-sm"><input type="radio" name={`decision-${index}`} checked={draft.decision === "pass"} onChange={() => updateDecision(item.material_name, { decision: "pass" })} />通过</label><label className="flex cursor-pointer items-center gap-2 text-sm text-destructive"><input type="radio" name={`decision-${index}`} checked={draft.decision === "reupload"} onChange={() => updateDecision(item.material_name, { decision: "reupload" })} />要求重传</label></fieldset></div><textarea className="mt-3 min-h-24 w-full rounded-md border bg-background p-3 text-sm" value={draft.note} onChange={(event) => updateDecision(item.material_name, { note: event.target.value })} disabled={!isActive || complete.isPending} placeholder={draft.decision === "reupload" ? "必须填写重传原因，例如：证件照片模糊，请重新上传完整、清晰的原件照片。" : "可选：填写通过备注，例如：材料清晰完整，请线下携带原件办理。"} />{draft.decision === "reupload" && !draft.note.trim() && <p className="mt-2 text-sm text-amber-700">选择“要求重传”后必须填写备注。</p>}</div> })}</div></section>
    <section className="rounded-xl border bg-card p-5"><h2 className="font-semibold">提交复核结果</h2><p className="mt-1 text-sm text-muted-foreground">所有待复核事项均作出决定后才能提交。“要求重传”的备注会保存并反馈到用户对应的材料准备记录。</p><textarea className="mt-4 min-h-24 w-full rounded-md border bg-background p-3 text-sm" value={generalComment} onChange={(event) => setGeneralComment(event.target.value)} disabled={!isActive || complete.isPending} placeholder="可选：填写本次整体复核说明。" /><div className="mt-4"><Button disabled={!isActive || !readyToSubmit || complete.isPending} onClick={submit}>{complete.isPending ? "提交中…" : "提交复核结果"}</Button></div>{!readyToSubmit && isActive && <p className="mt-3 text-sm text-amber-700">请处理列表中的每一项；选择“要求重传”时请填写备注。</p>}{complete.error instanceof Error && <p className="mt-3 text-sm text-destructive">{complete.error.message}</p>}{complete.isSuccess && <p className="mt-3 text-sm text-primary">复核结果已提交，已保存管理员编号、逐项结论和反馈备注。</p>}</section>
  </div>
}
