import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { Loader2, ShieldCheck, UserRound } from "lucide-react"
import type { ReactNode } from "react"

import { Badge } from "@/components/ui/badge"
import {
  getOperationRecords,
  type ApplicationOperationRecord,
  type AuditRecord,
  type CaseReviewRecord,
} from "@/lib/operation-records-api"

export const Route = createFileRoute("/_layout/items")({
  component: OperationRecordsPage,
  head: () => ({ meta: [{ title: "记录管理" }] }),
})

function formatTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleString("zh-CN", { hour12: false })
}

function Empty({ text }: { text: string }) {
  return <div className="px-5 py-8 text-center text-sm text-muted-foreground">{text}</div>
}

function ApplicationRecords({ records }: { records: ApplicationOperationRecord[] }) {
  if (!records.length) return <Empty text="当前用户暂无办件记录" />
  return <div className="divide-y">
    {records.map((record) => (
      <div key={record.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
        <div>
          <p className="font-medium">{record.region_name ? `${record.region_name} · ` : ""}{record.matter_name}</p>
          <p className="mt-1 text-sm text-muted-foreground">办件编号：{record.application_no} · 最近更新：{formatTime(record.updated_at)}</p>
        </div>
        <Badge variant="secondary">{record.status}</Badge>
      </div>
    ))}
  </div>
}

function CaseReviewRecords({ records }: { records: CaseReviewRecord[] }) {
  if (!records.length) return <Empty text="当前管理员暂无办件复核记录" />
  return <div className="divide-y">
    {records.map((record) => (
      <div key={record.id} className="px-5 py-4">
        <p className="font-medium">{record.action} · {record.matter_name}</p>
        <p className="mt-1 text-sm text-muted-foreground">办件编号：{record.application_no} · {formatTime(record.created_at)}</p>
        {record.comment && <p className="mt-2 text-sm">复核意见：{record.comment}</p>}
      </div>
    ))}
  </div>
}

function AuditRecords({ records, emptyText }: { records: AuditRecord[]; emptyText: string }) {
  if (!records.length) return <Empty text={emptyText} />
  return <div className="divide-y">
    {records.map((record) => (
      <div key={record.id} className="px-5 py-4">
        <p className="font-medium">{record.action}{record.target_name ? `：${record.target_name}` : ""}</p>
        <p className="mt-1 text-sm text-muted-foreground">{formatTime(record.created_at)}</p>
      </div>
    ))}
  </div>
}

function RecordSection({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return <section className="overflow-hidden rounded-xl border bg-card shadow-sm">
    <header className="border-b px-5 py-4">
      <h2 className="font-semibold">{title}</h2>
      <p className="mt-1 text-sm text-muted-foreground">{description}</p>
    </header>
    {children}
  </section>
}

function OperationRecordsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["operation-records"],
    queryFn: getOperationRecords,
  })
  const isAdmin = data?.role === "administrator"

  return <div className="mx-auto flex max-w-6xl flex-col gap-6">
    <div className="flex items-start gap-3">
      <div className="rounded-lg bg-primary/10 p-2 text-primary">{isAdmin ? <ShieldCheck className="size-6" /> : <UserRound className="size-6" />}</div>
      <div>
        <h1 className="text-2xl font-bold tracking-tight">记录管理</h1>
        <p className="mt-1 text-muted-foreground">{isAdmin ? "查看当前管理员的办件复核、事项状态复核和用户管理操作记录。" : "查看当前用户本人提交的办件记录。"}</p>
      </div>
    </div>

    {isLoading && <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground"><Loader2 className="size-5 animate-spin" />正在加载记录…</div>}
    {error && <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">{error.message}</div>}
    {data && <>
      <RecordSection title="我的办件记录" description="仅显示当前登录用户创建的办件。">
        <ApplicationRecords records={data.application_records} />
      </RecordSection>
      {isAdmin && <div className="grid gap-6 xl:grid-cols-3">
        <RecordSection title="办件复核记录" description="当前管理员提交的办件复核结果。"><CaseReviewRecords records={data.case_review_records ?? []} /></RecordSection>
        <RecordSection title="事项状态复核记录" description="当前管理员对事项信息进行编辑、确认、发布等操作的记录。"><AuditRecords records={data.matter_review_records ?? []} emptyText="当前管理员暂无事项状态复核记录" /></RecordSection>
        <RecordSection title="用户管理记录" description="当前管理员新增、编辑或删除用户的操作记录。"><AuditRecords records={data.user_management_records ?? []} emptyText="当前管理员暂无用户管理记录" /></RecordSection>
      </div>}
    </>}
  </div>
}
