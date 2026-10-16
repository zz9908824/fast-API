import { Link } from "@tanstack/react-router"
import { FileCheck2 } from "lucide-react"

import { cn } from "@/lib/utils"

interface LogoProps {
  variant?: "full" | "icon" | "responsive"
  className?: string
  asLink?: boolean
}

export function Logo({ variant = "full", className, asLink = true }: LogoProps) {
  const content = (
    <span className={cn("inline-flex items-center gap-3", className)}>
      <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
        <FileCheck2 className="size-6" aria-hidden="true" />
      </span>
      {variant !== "icon" && <span className={cn("text-xl font-bold tracking-tight", variant === "responsive" && "group-data-[collapsible=icon]:hidden")}>哈哈快办</span>}
      {variant === "icon" && <span className="sr-only">哈哈快办</span>}
    </span>
  )
  return asLink ? <Link to="/" aria-label="哈哈快办首页">{content}</Link> : content
}
