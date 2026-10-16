import { Briefcase, ClipboardCheck, ClipboardList, Home, Search, ShieldCheck, Users } from "lucide-react"

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
  { icon: Briefcase, title: "记录管理", path: "/items" },
]

export function AppSidebar() {
  const { user: currentUser } = useAuth()

  const items = currentUser?.is_superuser
    ? [...baseItems, { icon: ShieldCheck, title: "办件复核", path: "/staff/tasks" }, { icon: Users, title: "用户管理", path: "/admin" }, { icon: Briefcase, title: "事项配置", path: "/admin/matters" }, { icon: ClipboardCheck, title: "事项状态复核", path: "/admin/matter-reviews" }]
    : baseItems

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-4 py-6 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:items-center">
        <Logo variant="responsive" />
      </SidebarHeader>
      <SidebarContent>
        <Main items={items} />
      </SidebarContent>
      <SidebarFooter>
        <SidebarAppearance />
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar
