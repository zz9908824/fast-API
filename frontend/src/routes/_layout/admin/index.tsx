import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { Suspense } from "react"

import { type UserPublic, UsersService } from "@/client"
import AddUser from "@/components/Admin/AddUser"
import { columns, type UserTableData } from "@/components/Admin/columns"
import { DataTable } from "@/components/Common/DataTable"
import PendingUsers from "@/components/Pending/PendingUsers"
import useAuth from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/admin/")({
  component: AdminUsers,
  head: () => ({ meta: [{ title: "用户管理 - 全栈 FastAPI 模板" }] }),
})

function getUsersQueryOptions() {
  return {
    queryFn: async () =>
      (await UsersService.readUsers({ query: { skip: 0, limit: 100 } })).data,
    queryKey: ["users"],
  }
}

function UsersTableContent() {
  const { user: currentUser } = useAuth()
  const { data: users } = useSuspenseQuery(getUsersQueryOptions())
  const tableData: UserTableData[] = users.data.map((user: UserPublic) => ({
    ...user,
    isCurrentUser: currentUser?.id === user.id,
  }))
  return <DataTable columns={columns} data={tableData} />
}

function AdminUsers() {
  return <div className="flex flex-col gap-6"><div className="flex items-center justify-between"><div><h1 className="text-2xl font-bold tracking-tight">用户管理</h1><p className="text-muted-foreground">管理用户账户与权限</p></div><AddUser /></div><Suspense fallback={<PendingUsers />}><UsersTableContent /></Suspense></div>
}
