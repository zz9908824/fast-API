import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, Outlet, createFileRoute, useMatchRoute, useNavigate } from "@tanstack/react-router"
import { ClipboardCheck, Loader2, Trash2 } from "lucide-react"

import { StatusBadge } from "@/components/Precheck/StatusBadge"
import { Button } from "@/components/ui/button"
import { claimCaseReviewTask, deleteCancelledCaseReviewTask, getCaseReviewTasks } from "@/lib/case-review-api"

export const Route = createFileRoute("/_layout/staff/tasks")({ component: StaffTasks })

function StaffTasks() {
  const client = useQueryClient()
  const navigate = useNavigate()
  const matchRoute = useMatchRoute()
  const activeTask = matchRoute({ to: "/staff/tasks/$taskId", fuzzy: false })
  const refresh = () => client.invalidateQueries({ queryKey: ["case-review-tasks"] })
  const tasksQuery = useQuery({ queryKey: ["case-review-tasks"], queryFn: getCaseReviewTasks })
  const claim = useMutation({ mutationFn: claimCaseReviewTask, onSuccess: (_data, taskId) => { refresh(); navigate({ to: "/staff/tasks/$taskId", params: { taskId } }) } })
  const remove = useMutation({ mutationFn: deleteCancelledCaseReviewTask, onSuccess: refresh })
  if (activeTask) return <Outlet />
  const tasks = tasksQuery.data?.items ?? []
  // A service matter can have several residents' preparation records.  They
  // are displayed together for staff triage, but each record remains its own
  // claimable task so uploaded files and reviewer responsibility never mix.
  const taskGroups = tasks.reduce<Array<{ matterName: string; tasks: typeof tasks }>>((groups, task) => {
    const group = groups.find((item) => item.matterName === task.matter_name)
    if (group) group.tasks.push(task)
    else groups.push({ matterName: task.matter_name, tasks: [task] })
    return groups
  }, [])
  return <div className="space-y-6"><div><h1 className="text-2xl font-bold">办件复核</h1><p className="mt-1 text-muted-foreground">显示材料模型审核后需要人工确认的办件；待领取任务由工作人员领取后处理。</p></div>
    {tasksQuery.isLoading && <div className="flex items-center gap-2 py-12 text-muted-foreground"><Loader2 className="size-4 animate-spin" />正在加载复核队列…</div>}
    {tasksQuery.error instanceof Error && <p className="rounded-lg border border-destructive/30 p-4 text-sm text-destructive">{tasksQuery.error.message}</p>}
    {!tasksQuery.isLoading && !tasksQuery.error && <div className="space-y-4">{taskGroups.map((group) => <section className="overflow-hidden rounded-xl border bg-card" key={group.matterName}><header className="flex flex-wrap items-center justify-between gap-3 border-b bg-muted/40 p-4"><div><h2 className="font-semibold">{group.matterName}</h2><p className="mt-1 text-sm text-muted-foreground">该事项共有 {group.tasks.length} 个需要处理的办件复核任务。</p></div><StatusBadge status={`待复核 ${group.tasks.length} 件`} /></header><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-muted-foreground"><tr><th className="p-4">办件编号与问题</th><th className="p-4">状态</th><th className="p-4">提交时间</th><th className="p-4" /></tr></thead><tbody>{group.tasks.map((task) => <tr className={task.user_cancelled ? "border-t bg-muted/30" : "border-t"} key={task.id}><td className="p-4"><p className="font-medium text-xs">{task.application_no}</p><p className="mt-1 max-w-xl text-xs text-muted-foreground">{task.user_cancelled ? "用户已取消该办件，等待管理员清理复核任务。" : task.model_result_json?.summary ?? task.request_note ?? "材料检查存在待确认项"}</p></td><td className="p-4"><StatusBadge status={task.user_cancelled ? "用户已取消" : task.status === "pending" ? "待领取" : "处理中"} /></td><td className="p-4 whitespace-nowrap">{new Date(task.created_at).toLocaleString("zh-CN")}</td><td className="p-4 whitespace-nowrap">{task.user_cancelled ? <Button size="sm" variant="outline" disabled={remove.isPending} onClick={() => remove.mutate(task.id)}><Trash2 className="mr-1 size-3" />删除任务</Button> : task.status === "pending" ? <Button size="sm" disabled={claim.isPending} onClick={() => claim.mutate(task.id)}>{claim.isPending ? "领取中…" : "领取复核"}</Button> : <Button asChild size="sm" variant="outline"><Link to="/staff/tasks/$taskId" params={{ taskId: task.id }}>进入工作台</Link></Button>}</td></tr>)}</tbody></table></div></section>)}{taskGroups.length === 0 && <div className="rounded-xl border p-10 text-center text-muted-foreground">当前没有待领取或由您处理的办件复核任务。</div>}</div>}
    {(claim.error instanceof Error || remove.error instanceof Error) && <p className="text-sm text-destructive">{claim.error instanceof Error ? claim.error.message : remove.error instanceof Error ? remove.error.message : ""}</p>}<div className="flex items-center gap-2 text-sm text-muted-foreground"><ClipboardCheck className="size-4" />领取由后端原子更新，避免同一办件被多名工作人员同时领取。</div></div>
}
