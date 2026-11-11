import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export function Card({
  children,
  className,
  title,
  subtitle,
  action,
  bodyClassName,
  flush = false,
}: {
  children?: ReactNode
  className?: string
  title?: ReactNode
  subtitle?: ReactNode
  action?: ReactNode
  bodyClassName?: string
  flush?: boolean
}) {
  return (
    <section className={cn('card', className)}>
      {(title || action) && (
        <header className="card-head">
          <div>
            <div className="card-title">{title}</div>
            {subtitle && <div className="card-sub mt-1">{subtitle}</div>}
          </div>
          {action}
        </header>
      )}
      {children !== undefined && (
        <div className={cn('card-body', flush && 'flush', bodyClassName)}>{children}</div>
      )}
    </section>
  )
}

export function Stat({
  label,
  value,
  unit,
  foot,
  accent = 'var(--accent)',
  icon,
}: {
  label: string
  value: ReactNode
  unit?: string
  foot?: ReactNode
  accent?: string
  icon?: ReactNode
}) {
  return (
    <div className="stat" style={{ ['--stat-accent' as string]: accent }}>
      <div className="stat-label">
        {icon}
        {label}
      </div>
      <div className="stat-value">
        {value}
        {unit && <span className="unit">{unit}</span>}
      </div>
      {foot && <div className="stat-foot">{foot}</div>}
    </div>
  )
}

export function SectionTitle({
  children,
  right,
  className,
}: {
  children: ReactNode
  right?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('row mb-3', className)} style={{ justifyContent: 'space-between' }}>
      <h3 style={{ fontSize: 14, fontWeight: 600 }}>{children}</h3>
      {right}
    </div>
  )
}

export function AgentDot({ colorIndex, color }: { colorIndex: number; color?: string }) {
  const c = color ?? ['#5b8cff', '#2dd4a7', '#f5a524', '#a78bfa', '#f472b6'][colorIndex % 5]
  return <span className="agent-dot" style={{ background: c, ['--dot-ring' as string]: `${c}22` }} />
}

export function AgentChip({
  name,
  colorIndex,
  color,
  muted = false,
}: {
  name: string
  colorIndex: number
  color?: string
  muted?: boolean
}) {
  return (
    <span className={cn('agent-chip', muted && 'muted')}>
      <AgentDot colorIndex={colorIndex} color={color} />
      {name}
    </span>
  )
}
