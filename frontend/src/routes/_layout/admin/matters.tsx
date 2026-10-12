import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { FileText, MapPin, RefreshCw, ShieldCheck } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { getFinishedMatterVersions } from "@/lib/admin-matters-api"

export const Route = createFileRoute("/_layout/admin/matters")({ component: MatterAdmin })

function MatterAdmin() {
  const { data: matters = [], isLoading, isError, error, isFetching, refetch } = useQuery({
    queryKey: ["finished-matter-versions"],
    queryFn: getFinishedMatterVersions,
  })

  return <div className="space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div><h1 className="text-2xl font-bold">事项配置</h1><p className="mt-1 text-muted-foreground">展示已完成核验并发布的事项版本；如需变更，请创建新的草稿版本并重新复核。</p></div>
      <Button variant="outline" disabled={isFetching} onClick={() => refetch()}><RefreshCw className={`mr-2 size-4 ${isFetching ? "animate-spin" : ""}`} />{isFetching ? "正在刷新…" : "刷新事项"}</Button>
    </header>
    {isLoading && <p className="text-muted-foreground">正在加载已发布事项…</p>}
    {isError && <p className="text-destructive">{error instanceof Error ? error.message : "已发布事项加载失败，请确认管理员登录状态和后端服务。"}</p>}
    {!isLoading && !isError && matters.length === 0 && <div className="rounded-xl border border-dashed p-10 text-center text-muted-foreground">当前没有状态为 finished 的已发布事项。</div>}
    {!isLoading && !isError && matters.length > 0 && <div className="grid gap-4 md:grid-cols-2">{matters.map((matter) => <article className="rounded-xl border p-5" key={matter.version_id}>
      <div className="flex items-start justify-between gap-3"><div><h2 className="font-semibold">{matter.name}</h2><p className="mt-1 text-sm text-muted-foreground">{matter.region_name} · 第 {matter.version_no} 版</p></div><Badge>已发布 finished</Badge></div>
      <p className="mt-3 text-sm text-muted-foreground">{matter.description ?? "未填写事项说明"}</p>
      <div className="mt-4 space-y-1 text-sm text-muted-foreground"><p>事项编码：{matter.official_code ?? matter.code}</p><p>办理地点：{matter.location_name ?? "未配置"}</p><p>发布日期：{formatDate(matter.published_at)}</p></div>
      <div className="mt-5 grid grid-cols-3 gap-2 text-center text-xs"><MatterInfo icon={<FileText />} text={`材料要求 ${matter.material_count} 项`} /><MatterInfo icon={<ShieldCheck />} text={`获取方式 ${matter.acquisition_method_count} 项`} /><MatterInfo icon={<MapPin />} text={matter.location_name ? "已配置地点" : "未配置地点"} /></div>
    </article>)}</div>}
  </div>
}

function MatterInfo({ icon, text }: { icon: React.ReactNode; text: string }) {
  return <div className="flex flex-col items-center gap-2 rounded-lg border p-3"><span className="text-primary">{icon}</span>{text}</div>
}

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "未记录"
}
