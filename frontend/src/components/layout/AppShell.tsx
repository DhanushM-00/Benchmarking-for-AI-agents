import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import {
  Activity,
  Boxes,
  ChevronRight,
  FlaskConical,
  LayoutDashboard,
  Menu,
  Play,
  Scale,
  Settings2,
  Trophy,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useBackendHealth, useDataSource } from '@/hooks/useBackendHealth'
import { Badge, Button } from '@/components/ui/Primitives'

interface NavEntry {
  to: string
  label: string
  icon: ReactNode
  badge?: string
}

const NAV_GROUPS: { label: string; items: NavEntry[] }[] = [
  {
    label: 'Overview',
    items: [{ to: '/', label: 'Dashboard', icon: <LayoutDashboard /> }],
  },
  {
    label: 'Benchmarking',
    items: [
      { to: '/run', label: 'New benchmark run', icon: <Play /> },
      { to: '/runs', label: 'Runs', icon: <Activity /> },
      { to: '/leaderboard', label: 'Leaderboard', icon: <Trophy /> },
    ],
  },
  {
    label: 'Library',
    items: [
      { to: '/tasks', label: 'Tasks & benchmarks', icon: <FlaskConical />, badge: '100' },
      { to: '/agents', label: 'Agents', icon: <Boxes />, badge: '3' },
    ],
  },
  {
    label: 'System',
    items: [
      { to: '/fairness', label: 'Fairness engine', icon: <Scale /> },
      { to: '/settings', label: 'Settings', icon: <Settings2 /> },
    ],
  },
]

const PAGE_META: Record<string, { title: string; crumb: string }> = {
  '/': { title: 'Dashboard', crumb: 'Overview' },
  '/run': { title: 'New benchmark run', crumb: 'Benchmarking' },
  '/runs': { title: 'Benchmark runs', crumb: 'Benchmarking' },
  '/runs/:id': { title: 'Run detail', crumb: 'Benchmarking' },
  '/leaderboard': { title: 'Leaderboard', crumb: 'Benchmarking' },
  '/tasks': { title: 'Tasks & benchmarks', crumb: 'Library' },
  '/agents': { title: 'Agents', crumb: 'Library' },
  '/fairness': { title: 'Fair Agent Testing Engine', crumb: 'System' },
  '/settings': { title: 'Settings', crumb: 'System' },
}

function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const location = useLocation()

  useEffect(() => {
    onClose()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname])

  return (
    <>
      {open && <div className="sidebar-scrim" onClick={onClose} />}
      <aside className={cn('sidebar', open && 'open')}>
        <div className="brand">
          <div className="brand-mark">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2v20" />
              <path d="M4 7h16" />
              <path d="M4 17h16" />
              <path d="m7 7-3 5 3 5" />
              <path d="m17 7 3 5-3 5" />
            </svg>
          </div>
          <div style={{ minWidth: 0 }}>
            <div className="brand-name">Bifrost</div>
            <div className="brand-sub">Agent Benchmarking</div>
          </div>
          <button
            className="btn btn-ghost btn-icon btn-sm brand-close"
            style={{ marginLeft: 'auto' }}
            onClick={onClose}
            aria-label="Close menu"
          >
            <X />
          </button>
        </div>

        <nav className="nav">
          {NAV_GROUPS.map((group) => (
            <div className="nav-group" key={group.label}>
              <div className="nav-label">{group.label}</div>
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) => cn('nav-item', isActive && 'active')}
                >
                  {item.icon}
                  <span>{item.label}</span>
                  {item.badge && <span className="nav-count">{item.badge}</span>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="callout teal" style={{ padding: '10px 12px', fontSize: 11.5 }}>
            <Scale size={14} style={{ marginTop: 1 }} />
            <div>
              <strong style={{ fontWeight: 600 }}>Fair Engine active.</strong> Parity enforced on every
              run — identical dataset, prompt, budget and scorer.
            </div>
          </div>
        </div>
      </aside>
    </>
  )
}

export function AppShell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const meta = PAGE_META[location.pathname] ??
    (location.pathname.startsWith('/runs/')
      ? { title: 'Run detail', crumb: 'Benchmarking' }
      : { title: 'Bifrost', crumb: 'Overview' })

  // Real connectivity, measured — never inferred from the demo-mode flag.
  const health = useBackendHealth({ intervalMs: 15_000 })
  const dataSource = useDataSource()

  const status = useMemo(() => {
    if (health.state === 'checking') {
      return { tone: 'neutral' as const, label: 'CHECKING', tip: 'Probing the Bifrost backend…' }
    }
    if (health.state === 'disconnected') {
      return {
        tone: 'rose' as const,
        label: 'BACKEND OFFLINE',
        tip: health.error ?? 'Cannot reach the Bifrost backend',
      }
    }
    if (dataSource === 'demo') {
      return {
        tone: 'amber' as const,
        label: 'DEMO DATA',
        tip: 'Backend reachable — the dashboard is serving bundled fixture data',
      }
    }
    return {
      tone: 'teal' as const,
      label: 'LIVE DATA',
      tip: `Connected to the Bifrost backend${health.latencyMs != null ? ` (${health.latencyMs}ms)` : ''}`,
    }
  }, [health.state, health.error, health.latencyMs, dataSource])

  return (
    <div className="app">
      <Sidebar open={open} onClose={() => setOpen(false)} />
      <div className="main">
        <header className="topbar">
          <button className="btn btn-ghost btn-icon menu-btn" onClick={() => setOpen(true)} aria-label="Open menu">
            <Menu />
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
            <span className="topbar-crumb">{meta.crumb}</span>
            <ChevronRight size={13} className="muted" />
            <span className="topbar-title truncate">{meta.title}</span>
          </div>
          <div className="topbar-spacer" />
          <Badge tone={status.tone} className="tip" data-tip={status.tip} dot>
            {status.label}
          </Badge>
          <Badge tone="neutral" className="tip" data-tip="FastAPI backend: /api/v1">
            API
          </Badge>
          <Link to="/run">
            <Button size="sm" variant="primary" icon={<Play />}>
              Run benchmark
            </Button>
          </Link>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  )
}
