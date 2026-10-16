import { Link } from "@tanstack/react-router"
import { ArrowRight, Check, FileText, MapPin, Search } from "lucide-react"

import { Appearance } from "@/components/Common/Appearance"
import { Logo } from "@/components/Common/Logo"

interface AuthLayoutProps {
  children: React.ReactNode
}

const steps = [
  { icon: Search, title: "查清单", description: "要带什么，提前了解" },
  { icon: FileText, title: "备材料", description: "逐项准备，心中有数" },
  { icon: MapPin, title: "去办理", description: "确认地点，从容出发" },
]

export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="auth-shell">
      <section className="auth-story" aria-labelledby="auth-story-title">
        <div className="auth-story-grid" aria-hidden="true" />
        <div className="relative z-10">
          <Logo asLink={false} />
        </div>
        <div className="auth-story-body">
          <div className="auth-kicker"><span />让办事准备更简单</div>
          <h2 id="auth-story-title">材料提前备好，<br />办事少些奔波。</h2>
          <p className="auth-story-description">
            从看懂办事指南，到备齐每一份材料，<br className="hidden xl:block" />
            哈哈快办陪你把准备工作做在前面。
          </p>
          <div className="auth-document" aria-hidden="true">
            <div className="auth-document-top">
              <span className="auth-document-icon"><FileText size={22} /></span>
              <div><strong>我的办事准备清单</strong><span>每一份准备，都更有条理</span></div>
              <span className="auth-document-dots">•••</span>
            </div>
            {["了解事项办理要求", "整理申请所需材料", "确认办理地点与时间"].map((text, index) => (
              <div className="auth-document-row" key={text}>
                <span className="auth-document-check"><Check size={14} strokeWidth={3} /></span>
                <span>{text}</span><span className="auth-document-index">0{index + 1}</span>
              </div>
            ))}
            <div className="auth-document-bottom"><span className="auth-document-dot" />从容准备，安心出发<ArrowRight size={15} /></div>
          </div>
          <div className="auth-steps">
            {steps.map(({ icon: Icon, title, description }) => (
              <div className="auth-step" key={title}><span className="auth-step-icon"><Icon size={18} /></span><strong>{title}</strong><span>{description}</span></div>
            ))}
          </div>
        </div>
        <div className="auth-story-footer"><span>哈哈快办 · 政务材料准备助手</span><span>准备充分 / 办事从容</span></div>
      </section>
      <section className="auth-main" aria-label="账户服务">
        <header className="auth-header">
          <div className="lg:hidden"><Logo asLink={false} /></div>
          <Link to="/services" className="auth-browse">先逛逛办事指南<ArrowRight size={15} /></Link>
          <Appearance />
        </header>
        <div className="auth-form-area"><div className="auth-form-card">{children}</div></div>
        <footer className="auth-footer"><span>© {new Date().getFullYear()} 哈哈快办</span><span>线上准备 · 线下办理</span></footer>
      </section>
    </div>
  )
}
