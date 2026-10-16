import { Badge } from "@/components/ui/badge"

const styles: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  "已上传": "default",
  "当前检查未发现问题": "default",
  "待补正": "destructive",
  "明确缺失": "destructive",
  "字段冲突": "destructive",
  "待领取": "secondary",
  "处理中": "outline",
  "用户已取消": "destructive",
  "待准备": "secondary",
  "现场出示": "outline",
}

export function StatusBadge({ status }: { status: string }) {
  return <Badge variant={styles[status] ?? "secondary"}>{status}</Badge>
}
