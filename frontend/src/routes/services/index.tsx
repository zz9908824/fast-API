import { Link, createFileRoute } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { ArrowRight, Home, MapPin, Search } from "lucide-react"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Footer } from "@/components/Common/Footer"
import AppSidebar from "@/components/Sidebar/AppSidebar"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import { searchMatters } from "@/lib/matters-api"

export const Route = createFileRoute("/services/")({ component: Services })

function Services() {
  const [keyword, setKeyword] = useState("")
  const { data, isLoading, isError } = useQuery({
    queryKey: ["public-matters", keyword.trim()],
    queryFn: () => searchMatters(keyword.trim()),
  })
  const results = data?.items ?? []

  return <SidebarProvider>
    <AppSidebar />
    <SidebarInset>
      <header className="sticky top-0 z-10 flex h-16 shrink-0 items-center gap-2 border-b bg-background px-4"><SidebarTrigger className="-ml-1 text-muted-foreground" /></header>
      <main className="flex-1 p-6 md:p-8"><div className="mx-auto flex max-w-6xl flex-col gap-8">
      <section className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-3">
          <Badge variant="outline">公开事项查询</Badge>
          <h1 className="text-3xl font-bold tracking-tight">查询办事材料与办理指南</h1>
          <p className="max-w-2xl text-muted-foreground">查询事项所需材料、材料获取方式和线下办理地点；保存办件、上传材料和申请复核时再登录。</p>
        </div>
        <Button asChild variant="outline">
          <Link to="/"><Home className="mr-2 size-4" />返回主页</Link>
        </Button>
      </section>
      <div className="relative max-w-xl">
        <Search className="absolute left-3 top-3 size-4 text-muted-foreground" />
        <Input className="pl-9" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="输入事项名称或服务区域" />
      </div>
      <section className="grid gap-4 md:grid-cols-2">
        {results.map((matter) => (
          <article key={matter.id} className="rounded-xl border bg-card p-5 shadow-sm">
            <div className="mb-3 flex items-start justify-between gap-3">
              <h2 className="text-lg font-semibold">{matter.name}</h2>
              <Badge variant={matter.supported ? "default" : "secondary"}>{matter.supported ? "支持预审" : "仅提供指南"}</Badge>
            </div>
            <p className="mb-4 text-sm text-muted-foreground">{matter.description}</p>
            <p className="mb-2 flex items-center gap-1 text-sm"><MapPin className="size-4" />{matter.region} · {matter.location}</p>
            <p className="mb-5 text-xs text-muted-foreground">材料 {matter.material_count} 项 · 信息更新：{matter.checked_at ?? "待核验"}</p>
            <Button asChild className="w-full"><Link to="/services/$matterId" params={{ matterId: matter.id }}>查看事项详情 <ArrowRight className="ml-2 size-4" /></Link></Button>
          </article>
        ))}
      </section>
      {isLoading && <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">正在查询事项…</div>}
      {isError && <div className="rounded-lg border border-destructive/40 p-12 text-center text-destructive">事项数据暂时无法加载，请确认后端服务已启动。</div>}
      {!isLoading && !isError && results.length === 0 && <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">未找到匹配的已发布事项，请调整关键词或服务区域。</div>}
      </div></main>
      <Footer />
    </SidebarInset>
  </SidebarProvider>
}
