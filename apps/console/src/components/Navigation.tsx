import Link from "next/link";

export function Navigation() {
  return (
    <nav className="flex items-center justify-between px-6 py-3 border-b border-k-hairline bg-k-surface">
      <div className="flex items-center gap-6">
        <h1 className="font-mono font-bold text-k-ink uppercase text-sm">KAVACH</h1>
        <div className="flex gap-4">
          <Link href="/" className="text-sm font-medium hover:text-k-ink text-k-muted transition-colors">Incidents</Link>
          <Link href="/debt" className="text-sm font-medium hover:text-k-ink text-k-muted transition-colors">Debt</Link>
        </div>
      </div>
      <div className="flex items-center gap-4">
        {/* Mode Switch (Phase 5) */}
        <div className="flex items-center bg-k-canvas rounded-md p-1 border border-k-hairline">
          <button className="px-3 py-1 text-xs font-medium rounded-sm bg-k-surface shadow-sm">SIMULATION</button>
          <button className="px-3 py-1 text-xs font-medium rounded-sm text-k-muted hover:text-k-ink">SHADOW</button>
          <button className="px-3 py-1 text-xs font-medium rounded-sm text-k-muted hover:text-k-ink">AUTONOMOUS</button>
        </div>
      </div>
    </nav>
  );
}
