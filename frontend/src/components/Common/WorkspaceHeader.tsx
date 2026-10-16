import { Link, useRouterState } from "@tanstack/react-router"
import { BookOpen, Menu } from "lucide-react"

import { Appearance } from "@/components/Common/Appearance"
import { Button } from "@/components/ui/button"
import { SidebarTrigger } from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"

const titles: Array<[string, string]> = [
  ["/admin/matter-reviews", "事项状态复核"], ["/admin/matters", "事项配置"],
  ["/staff/tasks", "办件复核"], ["/applications", "我的办件"],
  ["/services", "事项查询"], ["/items", "记录管理"], ["/settings", "账户设置"], ["/admin", "用户管理"], ["/", "首页"],
]

export function WorkspaceHeader() {
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const { user } = useAuth()
  const title = titles.find(([path]) => path === "/" ? pathname === "/" : pathname.startsWith(path))?.[1] ?? "哈哈快办"
  return <header className="workspace-header">
    <div className="flex min-w-0 items-center gap-3"><SidebarTrigger className="workspace-menu"><Menu className="size-4" /></SidebarTrigger><div className="min-w-0"><p className="workspace-crumb">政务材料准备</p><h1 className="truncate text-sm font-semibold">{title}</h1></div></div>
    <div className="flex items-center gap-2"><Button asChild variant="ghost" size="sm" className="hidden text-muted-foreground sm:inline-flex"><Link to="/services"><BookOpen className="mr-1.5 size-4" />办事指南</Link></Button><span className="hidden rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground md:inline">{user?.is_superuser ? "管理员" : "居民用户"}</span><Appearance /></div>
  </header>
}
