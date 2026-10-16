import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, createFileRoute } from "@tanstack/react-router"
import { ArrowRight, ClipboardList, Pencil, Plus } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cancelApplication, getApplications, updateApplicationDisplayName } from "@/lib/applications-api"

export const Route = createFileRoute("/_layout/applications/")({ component: Applications })

function applicationStatusLabel(status: string) {
  return ({
    draft: "待确认情形",
    preparing: "准备中",
    checking: "材料检查中",
    needs_action: "待补传材料",
    review_pending: "人工复核中",
    prepared: "准备包已生成（待线下办理）",
    closed: "已结束",
  } as Record<string, string>)[status] ?? status
}

function Applications() {
  const client = useQueryClient()
  const { data, isLoading, error } = useQuery({ queryKey: ["applications"], queryFn: getApplications })
  const cancelMutation = useMutation({
    mutationFn: cancelApplication,
    onSuccess: () => client.invalidateQueries({ queryKey: ["applications"] }),
  })
  const renameMutation = useMutation({
    mutationFn: ({ id, name, revision }: { id: string; name: string; revision: number }) => updateApplicationDisplayName(id, name, revision),
    onSuccess: () => client.invalidateQueries({ queryKey: ["applications"] }),
  })
  // Cancelled records are retained in the database for history, but are no
  // longer active material-preparation work and should not occupy this page.
  const records = (data?.items ?? []).filter((record) => record.status !== "cancelled")
  return <div className="mx-auto max-w-5xl space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h1 className="text-2xl font-bold">我的材料准备</h1><p className="mt-1 text-muted-foreground">这里保存材料准备、检查和复核进度；正式受理和审批仍在线下办理。</p></div><Button asChild><Link to="/services"><Plus className="mr-2 size-4" />查询事项</Link></Button></div>
    {isLoading && <div className="rounded-xl border p-8 text-center text-muted-foreground">正在加载材料准备记录…</div>}
    {error && <div className="rounded-xl border border-destructive/30 p-5 text-destructive">{error.message}</div>}
    {!isLoading && !error && records.length === 0 && <div className="rounded-xl border border-dashed p-10 text-center text-muted-foreground"><ClipboardList className="mx-auto mb-3 size-7" />暂未创建材料准备记录。请先查询事项，再点击“开始准备材料”。</div>}
    <div className="space-y-4">{records.map((record) => <article key={record.id} className="rounded-xl border bg-card p-5 shadow-sm"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-sm text-muted-foreground">{record.region_name ?? ""} · 材料准备记录 {record.application_no}</p><div className="mt-1 flex items-center gap-2"><h2 className="text-lg font-semibold">{record.matter_name}</h2><Button size="icon" variant="ghost" aria-label="编辑办件事项名称" disabled={renameMutation.isPending} onClick={() => { const name = window.prompt("修改本办件显示的事项名称（不会影响公共事项库）", record.matter_name); if (name?.trim()) renameMutation.mutate({ id: record.id, name: name.trim(), revision: record.content_revision }) }}><Pencil className="size-4" /></Button></div><p className="mt-2 text-sm text-muted-foreground">最近更新：{new Date(record.updated_at).toLocaleString("zh-CN", { hour12: false })}</p></div><div className="flex gap-2"><Badge variant={record.status === "draft" ? "secondary" : record.status === "prepared" ? "outline" : "default"}>{applicationStatusLabel(record.status)}</Badge>{record.is_delegated && <Badge variant="outline">代办</Badge>}</div></div><div className="mt-5 flex gap-2"><Button asChild><Link to="/applications/$applicationId" params={{ applicationId: record.id }}>继续准备 <ArrowRight className="ml-2 size-4" /></Link></Button>{record.status !== "closed" && <Button variant="outline" disabled={cancelMutation.isPending} onClick={() => { if (window.confirm("确定取消这份材料准备记录吗？取消后将从当前列表移除，但仍会保留历史记录。")) cancelMutation.mutate(record.id) }}>取消办件</Button>}</div>{(cancelMutation.error || renameMutation.error) && <p className="mt-3 text-sm text-destructive">{cancelMutation.error?.message ?? renameMutation.error?.message}</p>}</article>)}</div>
  </div>
}
