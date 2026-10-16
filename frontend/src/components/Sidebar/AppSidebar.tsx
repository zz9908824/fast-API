import { Briefcase, ClipboardCheck, ClipboardList, FileCog, Home, Search, ShieldCheck, Users } from "lucide-react"

import { SidebarAppearance } from "@/components/Common/Appearance"
import { Logo } from "@/components/Common/Logo"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
} from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
import { type Item, Main } from "./Main"
import { User } from "./User"

const baseItems: Item[] = [
  { icon: Home, title: "首页", path: "/" },
  { icon: Search, title: "事项查询", path: "/services" },
  { icon: ClipboardList, title: "我的办件", path: "/applications" },
  { icon: FileCog, title: "记录管理", path: "/items" },
]

export function AppSidebar() {
  const { user: currentUser } = useAuth()

  const managementItems: Item[] = currentUser?.is_superuser
    ? [{ icon: ShieldCheck, title: "办件复核", path: "/staff/tasks" }, { icon: Users, title: "用户管理", path: "/admin" }, { icon: Briefcase, title: "事项配置", path: "/admin/matters" }, { icon: ClipboardCheck, title: "事项状态复核", path: "/admin/matter-reviews" }]
    : []

  return (
    <Sidebar collapsible="icon" className="workspace-sidebar">
      <SidebarHeader className="px-4 py-5 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:items-center">
        <Logo variant="responsive" />
      </SidebarHeader>
      <SidebarContent>
        <Main label="办事服务" items={baseItems} />
        {managementItems.length > 0 && <Main label="工作管理" items={managementItems} />}
      </SidebarContent>
      <SidebarFooter>
        <SidebarAppearance />
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar
