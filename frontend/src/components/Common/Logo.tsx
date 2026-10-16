import { Link } from "@tanstack/react-router"

import { useTheme } from "@/components/theme-provider"
import { cn } from "@/lib/utils"
import icon from "/assets/images/fastapi-icon.svg"
import iconLight from "/assets/images/fastapi-icon-light.svg"

interface LogoProps {
  variant?: "full" | "icon" | "responsive"
  className?: string
  asLink?: boolean
}

export function Logo({
  variant = "full",
  className,
  asLink = true,
}: LogoProps) {
  const { resolvedTheme } = useTheme()
  const iconLogo = resolvedTheme === "dark" ? iconLight : icon
  const wordmark = <span className="font-sans text-[1.15rem] font-extrabold tracking-[-0.055em] text-[#009688]">哈哈快办</span>
  const iconMark = <img src={iconLogo} alt="哈哈快办" className="size-6" />
  const content =
    variant === "responsive" ? (
      <>
        <span className={cn(
            "flex items-center gap-2 group-data-[collapsible=icon]:hidden",
            className,
          )}>{iconMark}{wordmark}</span>
        <span className={cn(
            "hidden group-data-[collapsible=icon]:block",
            className,
          )}>{iconMark}</span>
      </>
    ) : (
      <span className={cn(variant === "full" ? "flex items-center gap-2" : "inline-flex", className)}>{variant === "full" ? <>{iconMark}{wordmark}</> : iconMark}</span>
    )

  if (!asLink) {
    return content
  }

  return <Link to="/">{content}</Link>
}
