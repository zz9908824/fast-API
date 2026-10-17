import { Link, createFileRoute } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { ArrowLeft, ArrowRight, MapPin, Search } from "lucide-react"
import { useState } from "react"

import { Footer } from "@/components/Common/Footer"
import AppSidebar from "@/components/Sidebar/AppSidebar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import { categoriesForMatter, categoryById } from "@/lib/matter-catalog"
import { searchMatters } from "@/lib/matters-api"

export const Route = createFileRoute("/services/categories/$categoryId")({ component: ServiceCategory })

function ServiceCategory() {
  const { categoryId } = Route.useParams()
  const [keyword, setKeyword] = useState("")
  const category = categoryById(categoryId)
  const { data, isLoading, isError } = useQuery({
    queryKey: ["public-matters", "category", categoryId, keyword.trim()],
    queryFn: () => searchMatters(keyword.trim()),
  })
  const matters = (data?.items ?? []).filter((matter) => categoriesForMatter(matter).some((item) => item.id === categoryId))

  return <SidebarProvider><AppSidebar /><SidebarInset>
    <header className="sticky top-0 z-10 flex h-16 shrink-0 items-center gap-2 border-b bg-background px-4"><SidebarTrigger className="-ml-1 text-muted-foreground" /></header>
    <main className="flex-1 p-6 md:p-8"><div className="mx-auto flex max-w-6xl flex-col gap-6">
      <Button asChild className="w-fit" variant="ghost"><Link to="/services"><ArrowLeft className="mr-2 size-4" />返回事项查询</Link></Button>
      {category ? <><section><Badge variant="outline">服务分类</Badge><h1 className="mt-3 text-3xl font-bold">{category.label}</h1><p className="mt-2 text-muted-foreground">当前仅展示归入“{category.label}”的已发布事项。</p></section><div className="relative max-w-2xl"><Search className="absolute left-3 top-3 size-4 text-muted-foreground" /><Input className="pl-9" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder={`在${category.label}事项中搜索`} /></div>
        {isLoading && <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">正在查询事项…</div>}
        {isError && <div className="rounded-lg border border-destructive/40 p-12 text-center text-destructive">事项数据暂时无法加载，请确认后端服务已启动。</div>}
        {!isLoading && !isError && matters.length === 0 && <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">该分类暂未收录匹配的已发布事项。</div>}
        {!isLoading && !isError && matters.length > 0 && <div className="grid gap-4 md:grid-cols-2">{matters.map((matter) => <article className="rounded-xl border bg-card p-5 shadow-sm" key={matter.id}><div className="mb-3 flex items-start justify-between gap-3"><h2 className="text-lg font-semibold">{matter.name}</h2><Badge variant={matter.supported ? "default" : "secondary"}>{matter.supported ? "支持预审" : "仅提供指南"}</Badge></div><p className="mb-4 text-sm text-muted-foreground">{matter.description ?? "查看事项办理材料与线下服务信息"}</p><p className="mb-2 flex items-center gap-1 text-sm"><MapPin className="size-4" />{matter.region} · {matter.location}</p><p className="mb-5 text-xs text-muted-foreground">材料 {matter.material_count} 项 · 信息更新：{matter.checked_at ?? "待核验"}</p><Button asChild className="w-full"><Link to="/services/$matterId" params={{ matterId: matter.id }}>查看事项详情 <ArrowRight className="ml-2 size-4" /></Link></Button></article>)}</div>}
      </> : <div className="rounded-xl border border-dashed p-12 text-center"><h1 className="text-xl font-semibold">未找到该服务分类</h1><p className="mt-2 text-muted-foreground">请返回事项查询页后重新选择分类。</p></div>}
    </div></main><Footer />
  </SidebarInset></SidebarProvider>
}
