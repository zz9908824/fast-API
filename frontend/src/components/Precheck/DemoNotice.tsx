import { Info } from "lucide-react"

export function DemoNotice() {
  return (
    <div className="flex gap-3 rounded-lg border border-amber-300/60 bg-amber-50 p-4 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-100">
      <Info className="mt-0.5 size-4 shrink-0" />
      <p>当前页面使用合成演示数据，仅用于展示材料预审流程，不构成政务办理、受理或审批结论。</p>
    </div>
  )
}
