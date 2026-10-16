export function Footer() {
  return (
    <footer className="border-t px-6 py-5 text-xs text-muted-foreground">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2">
        <p>© {new Date().getFullYear()} 哈哈快办</p>
        <p>线上充分准备，线下从容办理</p>
      </div>
    </footer>
  )
}
