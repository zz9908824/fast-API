import { Link, createFileRoute } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import {
  Accessibility, ArrowRight, Baby, BadgeCheck, BookOpen, BriefcaseBusiness, BusFront, Car,
  Cross, Globe2, GraduationCap, HeartHandshake, Home, House, Landmark, MapPin,
  Scale, Search, ShieldCheck, UsersRound, type LucideIcon,
} from "lucide-react"
import { useState } from "react"

import { Footer } from "@/components/Common/Footer"
import AppSidebar from "@/components/Sidebar/AppSidebar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import { MATTER_CATALOG_SECTIONS, categoriesForMatter, type MatterCatalogCategory } from "@/lib/matter-catalog"
import { searchMatters } from "@/lib/matters-api"

export const Route = createFileRoute("/services/")({ component: Services })

const CATALOG_ICONS: Record<MatterCatalogCategory["icon"], LucideIcon> = {
  shield: ShieldCheck, house: House, badge: BadgeCheck, graduation: GraduationCap,
  bus: BusFront, heart: HeartHandshake, baby: Baby, book: BookOpen,
  briefcase: BriefcaseBusiness, users: UsersRound, accessibility: Accessibility,
  scale: Scale, car: Car, globe: Globe2, landmark: Landmark, cross: Cross,
}

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
      <main className="flex-1 p-6 md:p-8"><div className="mx-auto flex max-w-7xl flex-col gap-8">
        <section className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-3"><Badge variant="outline">公开事项查询</Badge><h1 className="text-3xl font-bold tracking-tight">查询办事材料与办理指南</h1><p className="max-w-2xl text-muted-foreground">按服务分类查找事项，查看材料清单、材料获取方式和线下办理地点；保存办件、上传材料和申请复核时再登录。</p></div>
          <Button asChild variant="outline"><Link to="/"><Home className="mr-2 size-4" />返回主页</Link></Button>
        </section>

        <section className="space-y-8" aria-label="事项服务分类">
          {MATTER_CATALOG_SECTIONS.map((section) => <div key={section.id} className="space-y-4">
            <div><h2 className="text-2xl font-semibold tracking-tight">{section.title}</h2><p className="mt-1 text-sm text-muted-foreground">点击分类，进入仅展示该分类事项的页面。</p></div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {section.categories.map((category) => {
                const Icon = CATALOG_ICONS[category.icon]
                const matched = results.filter((matter) => categoriesForMatter(matter).some((item) => item.id === category.id))
                return <Link to="/services/categories/$categoryId" params={{ categoryId: category.id }} key={category.id} className="rounded-xl border bg-card p-4 text-left transition-colors hover:border-primary/50 hover:bg-muted/40">
                  <div className="flex items-center gap-3"><span className="rounded-lg bg-primary/10 p-2 text-primary"><Icon className="size-5" /></span><span className="font-semibold">{category.label}</span><span className="ml-auto text-xs text-muted-foreground">{matched.length} 项</span></div>
                  <div className="mt-3 min-h-11 space-y-1 text-sm text-muted-foreground">{matched.slice(0, 2).map((matter) => <p className="truncate" key={matter.id}>{matter.name}</p>)}{matched.length === 0 && <p>暂未配置对应事项</p>}</div>
                </Link>
              })}
            </div>
          </div>)}
        </section>

        <section className="space-y-4">
          <div><h2 className="text-2xl font-semibold">所有已发布事项</h2><p className="mt-1 text-sm text-muted-foreground">可通过事项名称、服务区域或材料关键词查询。</p></div>
          <div className="relative max-w-2xl"><Search className="absolute left-3 top-3 size-4 text-muted-foreground" /><Input className="pl-9" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="输入事项名称、服务区域或材料关键词" /></div>
          {isLoading && <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">正在查询事项…</div>}
          {isError && <div className="rounded-lg border border-destructive/40 p-12 text-center text-destructive">事项数据暂时无法加载，请确认后端服务已启动。</div>}
          {!isLoading && !isError && results.length === 0 && <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">未找到匹配的已发布事项，请调整关键词或服务区域。</div>}
          {!isLoading && !isError && results.length > 0 && <div className="grid gap-4 md:grid-cols-2">{results.map((matter) => <MatterCard key={matter.id} matter={matter} />)}</div>}
        </section>
      </div></main>
      <Footer />
    </SidebarInset>
  </SidebarProvider>
}

function MatterCard({ matter }: { matter: Awaited<ReturnType<typeof searchMatters>>["items"][number] }) {
  const labels = categoriesForMatter(matter).slice(0, 3)
  return <article className="rounded-xl border bg-card p-5 shadow-sm"><div className="mb-3 flex items-start justify-between gap-3"><h3 className="text-lg font-semibold">{matter.name}</h3><Badge variant={matter.supported ? "default" : "secondary"}>{matter.supported ? "支持预审" : "仅提供指南"}</Badge></div>{labels.length > 0 && <div className="mb-3 flex flex-wrap gap-1">{labels.map((category) => <Badge key={category.id} variant="outline" className="font-normal">{category.label}</Badge>)}</div>}<p className="mb-4 text-sm text-muted-foreground">{matter.description ?? "查看事项办理材料与线下服务信息"}</p><p className="mb-2 flex items-center gap-1 text-sm"><MapPin className="size-4" />{matter.region} · {matter.location}</p><p className="mb-5 text-xs text-muted-foreground">材料 {matter.material_count} 项 · 信息更新：{matter.checked_at ?? "待核验"}</p><Button asChild className="w-full"><Link to="/services/$matterId" params={{ matterId: matter.id }}>查看事项详情 <ArrowRight className="ml-2 size-4" /></Link></Button></article>
}
