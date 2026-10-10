import { Link, createFileRoute } from "@tanstack/react-router"
import { ClipboardCheck } from "lucide-react"

import { DemoNotice } from "@/components/Precheck/DemoNotice"
import { StatusBadge } from "@/components/Precheck/StatusBadge"
import { Button } from "@/components/ui/button"
import { reviewTasks } from "@/lib/precheck-demo"

export const Route = createFileRoute("/_layout/staff/tasks")({ component: StaffTasks })

function StaffTasks() { return <div className="space-y-6"><DemoNotice /><div><h1 className="text-2xl font-bold">复核任务队列</h1><p className="mt-1 text-muted-foreground">仅显示已分配或具备授权范围的演示任务。</p></div><div className="overflow-hidden rounded-xl border"><table className="w-full text-left text-sm"><thead className="bg-muted/60 text-muted-foreground"><tr><th className="p-4">事项与问题</th><th className="p-4">状态</th><th className="p-4">提交时间</th><th className="p-4">优先级</th><th className="p-4" /></tr></thead><tbody>{reviewTasks.map((task) => <tr className="border-t" key={task.id}><td className="p-4"><p className="font-medium">{task.issue}</p><p className="mt-1 text-xs text-muted-foreground">{task.matter}</p></td><td className="p-4"><StatusBadge status={task.status} /></td><td className="p-4">{task.createdAt}</td><td className="p-4">{task.priority}</td><td className="p-4"><Button asChild size="sm" variant="outline"><Link to="/staff/tasks/$taskId" params={{ taskId: task.id }}>进入工作台</Link></Button></td></tr>)}</tbody></table></div><div className="flex items-center gap-2 text-sm text-muted-foreground"><ClipboardCheck className="size-4" />领取任务必须由后端原子处理；本页面仅展示交互设计。</div></div> }
